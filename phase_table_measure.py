#!/usr/bin/env python3
"""Measure the per-band phase offsets the flowgraph actually sees.

The table that goes into phase_correct_hopping has to be measured through the
SAME radio configuration guru.py runs, or it corrects the wrong thing. The
part that matters most is gain_trim: the four RF paths are not equally
sensitive here, so guru trims them per channel, and on this hardware a change
in RX gain moves that channel's phase. Measuring with an untrimmed source and
correcting a trimmed one puts a fixed error into every band.

So this drives doa.twinrx_hopping_source -- the block guru uses -- with guru's
own bands, gains and trim, and reads the offsets out of the same tone the
flowgraph measures.

Each band is sampled once per cycle, after its settle window, and the cycles
are averaged circularly (mean of unit vectors) so 359 and 1 average to 0
rather than 180.

A sample is kept only when every channel sees the tone above --min-snr. A
channel receiving nothing still produces a perfectly steady phase, and
averaging that in would give a confident, wrong number.

    source ~/gnuradio-3.8/setup_env.sh
    ./phase_table_measure.py --cycles 10

Writes a table in degrees, ready to paste into the block, and one in radians
in the format phase_correct_hopping's Calibration file option reads.
"""
import argparse
import math
import sys
import threading
import time

import numpy as np
from gnuradio import gr, blocks

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from twinrx_hop_test import analyse   # reuse the tone analysis, don't re-derive

import doa

# guru.grc's settings. Kept here explicitly so a mismatch is visible rather
# than inherited silently.
BANDS = [(2400000000, 46.0, 0.0), (5200000000, 60.0, 0.0), (5800000000, 69.0, 0.0)]
GAIN_TRIM = (0.0, -13.3, 1.5, -1.7)
LO_EXPORT = "B"
SAMP_RATE = 1000000
TONE_OFFSET = 200e3


class Ring(gr.sync_block):
    """Newest N samples per channel, in a pre-allocated ring.

    twinrx_hop_test's Snapshot concatenates on every work call, which is O(N)
    each time. That is fine at its 65k default and ruinous at the depth needed
    to pull a weak tone out of the noise: at 2M samples it copies about 4 GB/s,
    which back-pressures the radio hard enough to stall the stream. This writes
    in place instead, so the cost per call is the size of the call.
    """

    def __init__(self, nchan, depth):
        gr.sync_block.__init__(self, name="ring",
                               in_sig=[np.complex64] * nchan, out_sig=None)
        self.nchan, self.depth = nchan, int(depth)
        self.buf = [np.zeros(self.depth, np.complex64) for _ in range(nchan)]
        self.pos = 0
        self.filled = 0
        self.lock_ = threading.Lock()

    def work(self, input_items, output_items):
        n = len(input_items[0])
        with self.lock_:
            take = min(n, self.depth)
            src_off = n - take
            end = self.pos + take
            for i in range(self.nchan):
                chunk = input_items[i][src_off:]
                if end <= self.depth:
                    self.buf[i][self.pos:end] = chunk
                else:
                    first = self.depth - self.pos
                    self.buf[i][self.pos:] = chunk[:first]
                    self.buf[i][:end - self.depth] = chunk[first:]
            self.pos = end % self.depth
            self.filled = min(self.depth, self.filled + take)
        return n

    def reset(self):
        with self.lock_:
            self.pos = 0
            self.filled = 0

    def grab(self):
        """Oldest-to-newest, or None until the ring has filled once."""
        with self.lock_:
            if self.filled < self.depth:
                return None
            return [np.concatenate([b[self.pos:], b[:self.pos]])
                    for b in self.buf]


class TB(gr.top_block):
    def __init__(self, bands, dwell, settle, depth, tx_control, apply_tbl=None):
        gr.top_block.__init__(self)
        self.corr = None
        self.src = doa.twinrx_hopping_source(
            samp_rate=SAMP_RATE, sources=4, addresses="type=x300",
            lo_export_direction=LO_EXPORT, cpu_format="fc32",
            bands=[(f, g, dwell) for f, g, _ in bands],
            settle=settle, hop_enable=True, tx_control=tx_control,
            blank_during_settle=False, lo_lock_fallback=False,
            gain_trim=GAIN_TRIM, start_delay=2.0)
        self.snap = Ring(4, depth)
        if apply_tbl:
            # The same block the flowgraph will use, fed the measured table.
            # Measuring through it rather than around it means what comes out
            # here is what the flowgraph will show -- including any mistake in
            # the block itself, which a paper check would miss.
            self.corr = doa.phase_correct_hopping(
                num_channels=4,
                bands=[(f, degs, dwell) for f, degs in apply_tbl],
                follow_source=True)
            for ch in range(4):
                self.connect((self.src, ch), (self.corr, ch), (self.snap, ch))
        else:
            for ch in range(4):
                self.connect((self.src, ch), (self.snap, ch))


def circ_mean_deg(vals):
    r = np.deg2rad(np.asarray(vals, float))
    return float(np.rad2deg(np.angle(np.mean(np.exp(1j * r)))))


def circ_spread_deg(vals):
    r = np.deg2rad(np.asarray(vals, float))
    m = np.angle(np.mean(np.exp(1j * r)))
    d = np.rad2deg(np.angle(np.exp(1j * (r - m))))
    return float(d.max() - d.min())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=10)
    ap.add_argument("--dwell", type=float, default=3.0)
    ap.add_argument("--settle", type=float, default=1.0)
    ap.add_argument("--depth", type=int, default=65536)
    ap.add_argument("--min-snr", dest="min_snr", type=float, default=20.0)
    # How far either side of the nominal tone to look. The default in
    # analyse() is 20 kHz, and the HackRF puts the tone 19.6 kHz high at
    # 5.8 GHz -- right on that edge, so a little drift and the search locks
    # onto noise instead of the tone. Its spec is +/-20 ppm, which is 116 kHz
    # up there; 60 kHz covers what this unit actually does with margin, while
    # staying well inside the 300 kHz the receiver passes.
    ap.add_argument("--search", type=float, default=60e3)
    # Re-measure with the table applied. The printed offsets become residuals:
    # a correct table drives them to zero, and a table entered backwards
    # doubles them instead of hiding the error.
    ap.add_argument("--apply", dest="apply_file", default=None,
                    help="degrees table to correct with, then report residuals")
    ap.add_argument("--tx-control", dest="tx_control", default="127.0.0.1:5123")
    ap.add_argument("--out-deg", dest="out_deg", default="phase_table_deg.txt")
    ap.add_argument("--out-rad", dest="out_rad", default="phase_table_rad.cfg")
    a = ap.parse_args()

    print("measuring through doa.twinrx_hopping_source, guru's own settings")
    print("  gain_trim %s   lo_export %s" % (str(GAIN_TRIM), LO_EXPORT))
    for f, g, _ in BANDS:
        print("  %8.4f GHz  gain %.1f dB" % (f / 1e9, g))
    print()

    apply_tbl = None
    if a.apply_file:
        apply_tbl = []
        for line in open(a.apply_file):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            v = [float(x) for x in line.replace(",", " ").split()]
            if len(v) >= 4:
                apply_tbl.append((v[0], v[1:4]))
        if not apply_tbl:
            print("no usable rows in %s" % a.apply_file)
            return 1
        print("APPLYING %s -- the offsets below are RESIDUALS, and should be "
              "near zero\n" % a.apply_file)

    tb = TB(BANDS, a.dwell, a.settle, a.depth, a.tx_control, apply_tbl)
    tb.start()

    per_band = {f: {1: [], 2: [], 3: []} for f, _, _ in BANDS}
    rejected = 0
    try:
        # One reading per band per cycle, taken after the settle window.
        deadline_cycles = a.cycles * len(BANDS)
        seen = 0
        last_index = None
        need = a.depth / float(SAMP_RATE)      # seconds the ring takes to fill
        while seen < deadline_cycles:
            time.sleep(0.05)
            idx = tb.src.get_band_index()
            if idx < 0 or idx == last_index or not tb.src.is_settled():
                continue

            # A capture must lie entirely inside one band's settled dwell.
            # Getting this wrong does not look like an error -- it silently
            # files one band's samples under another's name, which is how the
            # previous run produced 2.4 GHz numbers labelled 5.2 GHz.
            if tb.corr is not None:
                tb.corr.set_band_freq(BANDS[idx][0])
                time.sleep(0.2)          # let the new constants take effect
            tb.snap.reset()
            t0 = time.time()
            chans = None
            while time.time() - t0 < need + 1.0:
                time.sleep(0.05)
                if tb.src.get_band_index() != idx or not tb.src.is_settled():
                    break                      # band moved: throw the capture
                chans = tb.snap.grab()
                if chans is not None:
                    break
            # Re-check after the grab as well: the band may have moved between
            # the last check and the read.
            if chans is not None and (tb.src.get_band_index() != idx
                                      or not tb.src.is_settled()):
                chans = None
            last_index = idx
            if chans is None:
                print("  %8.4f GHz  capture discarded -- band changed during it"
                      % (BANDS[idx][0] / 1e9))
                continue
            freq = BANDS[idx][0]
            phases, snrs, peak = analyse(chans, SAMP_RATE, TONE_OFFSET,
                                        search=a.search)
            seen += 1
            if min(snrs) < a.min_snr:
                rejected += 1
                print("  %8.4f GHz  REJECTED, min SNR %.1f dB < %.1f"
                      % (freq / 1e9, min(snrs), a.min_snr))
                continue
            for ch in (1, 2, 3):
                per_band[freq][ch].append(phases[ch])
            print("  %8.4f GHz  ch1 %+8.2f  ch2 %+8.2f  ch3 %+8.2f   "
                  "minSNR %5.1f dB  peak %+7.1f kHz"
                  % (freq / 1e9, phases[1], phases[2], phases[3],
                     min(snrs), peak))
    finally:
        try:
            tb.src.stop_hopping()
        except Exception as e:
            # Reported, not swallowed: a hop thread left running through
            # teardown is what wedges the X310's control plane.
            print('could not stop the hop thread: %s' % e)
        tb.stop()
        tb.wait()

    print("\n" + "=" * 74)
    print("AVERAGE OF %d CYCLE(S) PER BAND   (%d sample(s) rejected on SNR)"
          % (a.cycles, rejected))
    print("=" * 74)
    print("%10s %12s %12s %12s   %s" % ("freq_GHz", "ch1-ch0", "ch2-ch0",
                                        "ch3-ch0", "spread (worst)"))
    print("-" * 74)
    table = []
    ok = True
    for f, _, _ in BANDS:
        rows = per_band[f]
        n = len(rows[1])
        if n < 2:
            print("%10.4f   too few valid samples (%d) -- not written" % (f / 1e9, n))
            ok = False
            continue
        means = [circ_mean_deg(rows[ch]) for ch in (1, 2, 3)]
        worst = max(circ_spread_deg(rows[ch]) for ch in (1, 2, 3))
        table.append((f, means))
        print("%10.4f %12.2f %12.2f %12.2f   %6.2f deg  (n=%d)"
              % (f / 1e9, means[0], means[1], means[2], worst, n))

    if not table:
        print("\nNothing measured. No files written.")
        return 1

    if a.apply_file:
        print("\nResiduals above. A correct table leaves them near zero;\n"
              "whatever is left is what to subtract from the table and repeat.")
        return 0

    with open(a.out_deg, "w") as fh:
        fh.write("# Measured (chN - ch0) in DEGREES, through guru's own radio\n")
        fh.write("# configuration: gain_trim %s, lo_export %s.\n"
                 % (str(GAIN_TRIM), LO_EXPORT))
        fh.write("# Paste a row into phase_correct_hopping's 'offsets' field.\n")
        fh.write("# Valid for THIS power session: the LO dividers relock to a\n")
        fh.write("# new phase every power cycle.\n")
        fh.write("# freq_hz, ch1_deg, ch2_deg, ch3_deg\n")
        for f, m in table:
            fh.write("%.0f, %.4f, %.4f, %.4f\n" % (f, m[0], m[1], m[2]))

    with open(a.out_rad, "w") as fh:
        fh.write("# Same table in RADIANS, for phase_correct_hopping's\n")
        fh.write("# 'Calibration file' option.\n")
        fh.write("# freq_hz, ch1_rad, ch2_rad, ch3_rad\n")
        for f, m in table:
            fh.write("%.0f, %.9f, %.9f, %.9f\n"
                     % (f, math.radians(m[0]), math.radians(m[1]),
                        math.radians(m[2])))

    print("\ndegrees -> %s" % a.out_deg)
    print("radians -> %s" % a.out_rad)
    print("\nPaste into the block, per band:")
    for f, m in table:
        print("  %.4f GHz  ->  %.2f, %.2f, %.2f" % (f / 1e9, m[0], m[1], m[2]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
