#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Per-band phase correction for a hopping receiver.
#
# This is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

"""Phase correction that follows a band schedule.

phase_correct_hier corrects one set of offsets, read from its file once in
__init__.  That is right for a receiver parked on one frequency and wrong for
one that hops, because the inter-channel offset is a property of the band.
Measured on this unit:

    pair       2.4 GHz    5.8 GHz    error if the 2.4 table is used at 5.8
    ch1-ch0    +158.4     +67.9                      90 deg
    ch2-ch0     -89.2    +144.1                     127 deg
    ch3-ch0    -175.4    +155.3                      29 deg

Corrections that wrong are worse than none: the readout looks corrected.

So this block holds a row per band and switches rows when the band changes.
It does not modify phase_correct_hier, and does the same arithmetic --
multiply channel N by exp(-j * offset), channel 0 straight through -- so the
two agree on any single band.

Offsets are given in DEGREES, which is what the readouts show; the conversion
to radians happens here.  They are the MEASURED offset (angle_chN - angle_ch0),
not a correction to apply: the block negates them, so a correct table drives
the residuals to zero.

Bands are matched by frequency.  A band with no row gets NO correction and
says so, rather than silently reusing the nearest row.

Two ways to drive it:

  follow_source=True (default)
      The band is set from outside with set_band_freq() or set_band_index(),
      normally by whatever already follows the radio.  It cannot drift out of
      step with the radio because it is not keeping its own time.

  follow_source=False
      The block runs its own schedule from the per-band dwell times.  Only for
      running it standalone -- two independent clocks beside one radio will
      eventually disagree, and a correction applied to the wrong band is the
      one failure that looks healthy.
"""

import math
import threading
import time

from gnuradio import blocks
from gnuradio import gr

from .hop_blocks import hop_tag_rotator


def _sig_io(num_elements, sig_type):
    return [sig_type] * num_elements


def read_cal_file(filename):
    """Read a calibration table.

    Accepts the format twinrx_hop_test.py --cal-out writes:

        # freq_hz, ch1_rad, ch2_rad, ch3_rad
        2400000000, 2.764, -1.557, -3.061

    Radians in the file, because that is what the measuring tool emits.
    Returns [(freq_hz, [rad, ...]), ...].

    Note this does not use filter() on the parsed values the way
    phase_correct_hier does: filter() drops anything falsy, so an offset of
    exactly 0.0 disappears and the row silently comes back one short.
    """
    table = []
    with open(filename, "r") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = [p.strip() for p in line.replace(",", " ").split()]
            try:
                vals = [float(p) for p in parts]
            except ValueError:
                continue
            if len(vals) < 2:
                continue
            table.append((vals[0], vals[1:]))
    return table


class phase_correct_hopping(gr.hier_block2):
    """Rotate each channel by its band's measured offset."""

    def __init__(self, num_channels=4, bands=((2.4e9, (0.0, 0.0, 0.0), 10.0),),
                 cal_file="", follow_source=True, settle=1.0,
                 start_delay=2.0, freq_tol=1e6, follow_tags=False):
        gr.hier_block2.__init__(
            self, "Phase Correct Hopping",
            gr.io_signaturev(num_channels, num_channels,
                             _sig_io(num_channels, gr.sizeof_gr_complex)),
            gr.io_signaturev(num_channels, num_channels,
                             _sig_io(num_channels, gr.sizeof_gr_complex)),
        )

        if num_channels < 2:
            raise ValueError("phase_correct_hopping: need at least 2 channels")

        self.num_channels = int(num_channels)
        self.follow_source = bool(follow_source)
        self.settle = float(settle)
        self.start_delay = float(start_delay)
        # How near a frequency has to be to count as the same band. Wide enough
        # for a retune landing a few hundred kHz off, far narrower than the gap
        # between any two bands worth calibrating separately.
        self.freq_tol = float(freq_tol)

        self._n_corr = self.num_channels - 1
        self._band_index = -1
        self._settled = False
        self._unknown_bands = 0
        self._run = False
        self._thread = None
        self._lock = threading.RLock()

        # ---- the table -------------------------------------------------
        # GRC gives degrees because that is what the readouts show. A file
        # gives radians because that is what the measuring tool writes. Both
        # end up as radians here.
        self.bands = []
        for b in bands:
            if not b:
                continue
            freq, degs, dwell = b[0], b[1], (b[2] if len(b) > 2 else 10.0)
            rads = [math.radians(float(d)) for d in degs][:self._n_corr]
            while len(rads) < self._n_corr:
                rads.append(0.0)
            self.bands.append((float(freq), rads, float(dwell)))

        if cal_file:
            # A file wins over typed values: it was measured, they were typed.
            loaded = read_cal_file(cal_file)
            if not loaded:
                raise ValueError(
                    "phase_correct_hopping: %s has no usable rows. Expected "
                    "'freq_hz, ch1_rad, ch2_rad, ...' per line." % cal_file)
            dwell_of = dict((f, d) for f, _, d in self.bands)
            self.bands = []
            for freq, rads in loaded:
                rads = list(rads)[:self._n_corr]
                while len(rads) < self._n_corr:
                    rads.append(0.0)
                self.bands.append((freq, rads, dwell_of.get(freq, 10.0)))
            print("[phasecal] loaded %d band(s) from %s"
                  % (len(self.bands), cal_file))

        if not self.bands:
            raise ValueError("phase_correct_hopping: no bands given")

        for freq, rads, _ in self.bands:
            print("[phasecal] %8.4f GHz  %s"
                  % (freq / 1e9,
                     "  ".join("ch%d %+8.2f deg" % (i + 1, math.degrees(r))
                               for i, r in enumerate(rads))))

        # ---- blocks ----------------------------------------------------
        # Channel 0 is the reference and passes straight through, so every
        # correction is relative to it and the reference cannot itself drift.
        # follow_tags: switch rows on the hop_on / hop_off marks that
        # twinrx_hopping_source (schedule="radio") puts on the exact samples,
        # and output zeros during every switch. Needed whenever a dwell is
        # shorter than the host can follow; see hop_blocks.hop_tag_rotator.
        self.follow_tags = bool(follow_tags)
        if self.follow_tags:
            self._tag_rot = hop_tag_rotator(
                self.num_channels, [(f, r) for f, r, _ in self.bands], self.freq_tol)
            for ch in range(self.num_channels):
                self.connect((self, ch), (self._tag_rot, ch), (self, ch))
            print("[phasecal] following the source's hop marks (sample-exact)")
            return

        self._passthrough = blocks.copy(gr.sizeof_gr_complex * 1)
        self._passthrough.set_enabled(True)
        self.connect((self, 0), self._passthrough, (self, 0))

        self._rotators = []
        for ch in range(1, self.num_channels):
            rot = blocks.multiply_const_vcc((1 + 0j,))
            self.connect((self, ch), rot, (self, ch))
            self._rotators.append(rot)

        # Start uncorrected. Nothing is applied until a band is selected, so a
        # block that is never told the band leaves the samples alone instead of
        # rotating them by whatever happened to be first in the table.
        self._apply([0.0] * self._n_corr)

        if not self.follow_source:
            self._start_schedule()

    # ------------------------------------------------------------------
    # applying
    # ------------------------------------------------------------------
    def _apply(self, rads):
        """Multiply channel N by exp(-j*offset): measured offset removed."""
        for rot, r in zip(self._rotators, rads):
            rot.set_k((complex(math.cos(-r), math.sin(-r)),))
        self._applied = list(rads)

    def _match(self, freq):
        """Index of the band this frequency belongs to, or -1."""
        best, best_d = -1, None
        for i, (f, _, _) in enumerate(self.bands):
            d = abs(f - freq)
            if d <= self.freq_tol and (best_d is None or d < best_d):
                best, best_d = i, d
        return best

    def get_table_deg(self):
        """[(freq_hz, [deg_ch1, deg_ch2, ...]), ...] currently applied."""
        with self._lock:
            return [(f, [math.degrees(r) for r in rads]) for f, rads, _ in self.bands]

    def set_table_deg(self, rows):
        """Replace the table at run time. Rows are (freq_hz, [deg, ...]) as
        measured (chN - ch0); bands not listed keep their row."""
        with self._lock:
            new = []
            for f, rads, dwell in self.bands:
                rep = [r for r in rows if abs(float(r[0]) - f) <= self.freq_tol]
                if rep:
                    rads = [math.radians(float(d)) for d in rep[0][1]][:self._n_corr]
                new.append((f, rads, dwell))
            self.bands = new
            if self.follow_tags:
                self._tag_rot.set_table([(f, r) for f, r, _ in self.bands])
            elif 0 <= self._band_index < len(self.bands):
                self._apply(self.bands[self._band_index][1])
        for f, rads, _ in self.bands:
            print("[phasecal] now %8.4f GHz  %s" % (f / 1e9, "  ".join(
                "ch%d %+8.2f deg" % (i + 1, math.degrees(r)) for i, r in enumerate(rads))))

    def set_band_index(self, index):
        """Select a row by position. Out of range leaves the samples alone."""
        if getattr(self, 'follow_tags', False):
            return    # the hop marks drive the rows, not the caller
        with self._lock:
            if index is None or index < 0 or index >= len(self.bands):
                self._uncorrected("index %s is outside the %d band(s) in the "
                                  "table" % (index, len(self.bands)))
                return False
            self._band_index = int(index)
            self._settled = False
            self._apply(self.bands[self._band_index][1])
            return True

    def set_band_freq(self, freq):
        """Select the row for this frequency.

        An unmatched frequency clears the correction rather than reusing the
        nearest row. A wrong rotation reads as a clean, stable, wrong phase,
        which is harder to catch than no rotation at all.
        """
        if getattr(self, 'follow_tags', False):
            return    # the hop marks drive the rows, not the caller
        with self._lock:
            i = self._match(float(freq))
            if i < 0:
                self._unknown_bands += 1
                self._uncorrected(
                    "%.4f GHz is not in the table -- calibrate it or remove it "
                    "from the schedule" % (float(freq) / 1e9))
                return False
            self._band_index = i
            self._settled = False
            self._apply(self.bands[i][1])
            # Say so. Without this the block is silent when it works and loud
            # only when it fails, so "no complaint" reads as "correcting" when
            # it may equally mean nothing ever asked it to.
            print("[phasecal] band %d  %.4f GHz  applying %s deg"
                  % (i, self.bands[i][0] / 1e9,
                     "  ".join("%+.2f" % math.degrees(r)
                               for r in self.bands[i][1])))
            return True

    def _uncorrected(self, why):
        self._band_index = -1
        self._settled = False
        self._apply([0.0] * self._n_corr)
        print("[phasecal] NO CORRECTION APPLIED: %s" % why)

    def mark_settled(self, settled=True):
        """Callers that gate their display can say when the band has settled."""
        self._settled = bool(settled)

    # ------------------------------------------------------------------
    # standalone schedule
    # ------------------------------------------------------------------
    def _start_schedule(self):
        print("[phasecal] running its own schedule -- this keeps time "
              "separately from the radio, so check they agree")
        self._run = True
        self._thread = threading.Thread(target=self._scheduler, daemon=True)
        self._thread.start()

    def _sleep(self, seconds):
        t0 = time.time()
        while self._run and time.time() - t0 < seconds:
            time.sleep(0.05)

    def _scheduler(self):
        self._sleep(self.start_delay)
        i = 0
        while self._run:
            idx = i % len(self.bands)
            self.set_band_index(idx)
            self._sleep(self.settle)
            self._settled = True
            self._sleep(self.bands[idx][2])
            i += 1

    def stop_schedule(self):
        self._run = False
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=2.0)

    # ------------------------------------------------------------------
    # accessors
    # ------------------------------------------------------------------
    def get_band_index(self):
        return self._band_index

    def is_settled(self):
        return bool(self._settled)

    def get_applied_deg(self):
        """What is being applied right now, in degrees, for checking."""
        return [math.degrees(r) for r in getattr(self, "_applied", [])]

    def get_table_deg(self):
        return [(f, [math.degrees(r) for r in rads]) for f, rads, _ in self.bands]

    def get_unknown_bands(self):
        """How many times a band with no row was asked for. Should stay 0."""
        return self._unknown_bands

    def set_band_offsets_deg(self, index, degs):
        """Replace one row at runtime, in degrees. For live recalibration."""
        with self._lock:
            if index < 0 or index >= len(self.bands):
                return False
            freq, _, dwell = self.bands[index]
            rads = [math.radians(float(d)) for d in degs][:self._n_corr]
            while len(rads) < self._n_corr:
                rads.append(0.0)
            self.bands[index] = (freq, rads, dwell)
            if self._band_index == index:
                self._apply(rads)
            return True
