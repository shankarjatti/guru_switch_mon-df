#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Re-measure the phase table while the receiver keeps hopping (lab tone).

The inter-channel offsets drift -- measured here: up to ~3 deg in 1.5 h at
5.8 GHz on ch2/ch3, the pairs that cross the board A <-> board B LO cable --
so a table measured once does not stay right. This runs one calibration pass
through the live chain:

  for each band: park the lab tone there, forget the meter's history of that
  band, collect `secs` of dwell windows, take the circular mean residual
  new table = current table + mean residual (the meter sees corrected data)

The new table is only applied if EVERY band passes:
  * at least min_windows windows, and every window had a tone on all channels
  * spread (std) of the per-window residual below max_std on every pair
  * no single window further than max_dev from the mean
Otherwise the old table stays and the reason is reported. On success the
table is written to `out_file` with a timestamp.
"""
import threading
import time

import numpy as np


class hop_calibrator(object):

    def __init__(self, source, correction, meter, bands, secs=4.0, min_windows=50,
                 max_std=0.3, max_dev=1.0, out_file="", restore_freq=None):
        # meter: one hop_phase_meter, or {band_freq: meter} with one per band
        self.src, self.corr, self.meter = source, correction, meter
        self.bands = [float(b) for b in bands]
        self.secs = float(secs)
        self.min_windows = int(min_windows)
        self.max_std = float(max_std)
        self.max_dev = float(max_dev)
        self.out_file = out_file
        self.restore_freq = restore_freq
        self.status = "not run"
        self.busy = False
        self.last = None

    def _meter(self, f):
        if isinstance(self.meter, dict):
            return [m for k, m in self.meter.items() if abs(float(k) - f) <= 1e6][0]
        return self.meter

    def start(self, restore_freq=None):
        if self.busy:
            return False
        if restore_freq is not None:
            self.restore_freq = restore_freq
        self.busy = True
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self):
        try:
            self._calibrate()
        except Exception as e:
            self.status = "FAILED: %s: %s" % (type(e).__name__, e)
            print("[cal] %s" % self.status)
        finally:
            self.busy = False
            if self.restore_freq:
                self.src.set_park_freq(self.restore_freq)
                if not isinstance(self.meter, dict):
                    self.meter.set_band_freq(self.restore_freq)

    def _wait_tone(self, f, need=5, timeout=4.0, settle=1.5, steady_hz=100.0):
        """True once `need` consecutive dwells of band f had the NEW tone.

        The HackRF sends from a buffer: after a retune its old baseband keeps
        coming for ~1.2 s (measured 2026-09-29), and with a 10 kHz tone that
        old signal can itself pass for a tone on the new band. So: wait
        `settle` s first, then require `need` dwells in a row with a tone whose
        frequency stays within `steady_hz` of the previous dwell's.
        """
        m = self._meter(f)
        time.sleep(settle)
        m.reset_band(f)
        t_end = time.time() + timeout
        run, last_t, last_hz = 0, None, None
        while time.time() < t_end:
            time.sleep(0.01)
            w = m.last_windows.get(float(f)) or next(
                (v for k, v in m.last_windows.items() if abs(k - f) <= 1e6), None)
            if w is None or w["t"] == last_t:
                continue
            last_t = w["t"]
            if w["tone"] and (last_hz is None or abs(w["tone_hz"] - last_hz) <= steady_hz):
                run += 1
            else:
                run = 1 if w["tone"] else 0
            last_hz = w["tone_hz"] if w["tone"] else None
            if run >= need:
                return True
        return False

    def _calibrate(self):
        current = dict((f, list(d)) for f, d in self.corr.get_table_deg())
        results, problems = {}, []
        for f in self.bands:
            self.status = "measuring %.1f GHz ..." % (f / 1e9)
            self.src.set_park_freq(f)
            # Start measuring only once the tone is really there: the HackRF
            # sends from a buffer (~1 s at 2 Msps), so after a retune it keeps
            # sending the old baseband for a while -- with a 10 kHz tone that
            # lands off the tone's frequency (measured 2026-09-29: ~1.2 s).
            # Ready = 5 dwells in a row with a tone; not within 3 s = rejected.
            ready = self._wait_tone(f)
            if not ready:
                results[f] = {"windows": 0, "tone": 0}
                problems.append("%.1f GHz: no steady lab tone within 5.5 s of moving it there"
                                % (f / 1e9))
                continue
            self._meter(f).reset_band(f)
            time.sleep(self.secs)
            s = self._meter(f).band_summary(f)
            results[f] = s
            tag = "%.1f GHz" % (f / 1e9)
            if s["windows"] < self.min_windows:
                problems.append("%s only %d windows" % (tag, s["windows"]))
            elif s["tone"] != s["windows"]:
                problems.append("%s: %d of %d windows had no tone" % (tag, s["windows"] - s["tone"], s["windows"]))
            elif max(s["std"]) >= self.max_std:
                problems.append("%s spread %.2f deg" % (tag, max(s["std"])))
            elif max(s["max_dev"]) >= self.max_dev:
                problems.append("%s one window %.2f deg off" % (tag, max(s["max_dev"])))
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        if problems:
            self.status = "REJECTED %s -- old table kept: %s" % (stamp, "; ".join(problems))
            print("[cal] %s" % self.status)
            return
        rows = []
        change = 0.0
        for f in self.bands:
            key = [k for k in current if abs(k - f) <= 1e6]
            base = current[key[0]] if key else [0.0] * len(results[f]["mean"])
            new = [c + r for c, r in zip(base, results[f]["mean"])]
            new = [((x + 180.0) % 360.0) - 180.0 for x in new]
            change = max(change, max(abs(r) for r in results[f]["mean"]))
            rows.append((f, new))
        self.corr.set_table_deg(rows)
        if self.out_file:
            with open(self.out_file, "w") as fh:
                fh.write("# Measured (chN - ch0) in DEGREES by guru_fast's CALIBRATE, %s.\n"
                         "# Radio-clock hopping, lab tone parked on each band in turn.\n"
                         "# Valid for THIS power session only.\n"
                         "# freq_hz, ch1_deg, ch2_deg, ch3_deg\n" % stamp)
                for f, d in rows:
                    fh.write("%d, %.4f, %.4f, %.4f\n" % (f, *d))
        self.last = {"time": stamp, "rows": rows, "results": results}
        worst = max(max(results[f]["max_dev"]) for f in self.bands)
        self.status = ("OK %s -- table updated (largest correction change %.2f deg, "
                       "worst single window %.2f deg)" % (stamp, change, worst))
        print("[cal] %s" % self.status)
