#!/usr/bin/env python3
"""Does a phase offset survive restarting the software?

Within one run the inter-channel offsets repeat to a fraction of a degree.
Across restarts they have been seen to move by 2-3 degrees, which matters:
a calibration taken in one run is then wrong in the next.

This separates the two. It runs twinrx_hop_test.py several times as separate
processes -- each one opens and closes the X310 exactly as a real start does --
and compares:

    within-run spread    how much an offset moves while one process holds the
                         radio. This is the measurement noise floor.
    between-run spread   how much the per-run mean moves from one process to
                         the next. Anything above the noise floor is something
                         being re-initialised at startup.

No power cycle happens in between, so the RF paths, the LO distribution and
the temperature are the same throughout. Anything that moves is in the tune,
the DDC or the host.

    source ~/gnuradio-3.8/setup_env.sh
    ./phase_restart_test.py --runs 4 --freq 2.4e9 --gain 46

The transmitter must already be running; it is commanded to the test
frequency over UDP, the same way the flowgraph does it.
"""
import argparse
import os
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PAIRS = ("ch1-ch0", "ch2-ch0", "ch3-ch0")


def circ_mean_deg(deg):
    r = np.deg2rad(np.asarray(deg, dtype=float))
    return float(np.rad2deg(np.angle(np.mean(np.exp(1j * r)))))


def circ_spread_deg(deg):
    """Peak-to-peak about the circular mean, so 359 and 1 read as 2 apart."""
    r = np.deg2rad(np.asarray(deg, dtype=float))
    m = np.angle(np.mean(np.exp(1j * r)))
    d = np.rad2deg(np.angle(np.exp(1j * (r - m))))
    return float(d.max() - d.min())


def read_csv(path):
    """-> {pair: array of degrees}. Empty if the run produced nothing valid."""
    cols = {p: [] for p in PAIRS}
    try:
        with open(path) as fh:
            for line in fh:
                if line.startswith("unix_time") or line.startswith("#"):
                    continue
                f = line.strip().split(",")
                if len(f) < 6:
                    continue
                try:
                    vals = [float(f[3]), float(f[4]), float(f[5])]
                except ValueError:
                    continue
                for p, v in zip(PAIRS, vals):
                    cols[p].append(v)
    except OSError:
        pass
    return {p: np.array(v) for p, v in cols.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=4)
    ap.add_argument("--freq", default="2.4e9")
    ap.add_argument("--gain", default="46")
    ap.add_argument("--cycles", type=int, default=6)
    ap.add_argument("--dwell", type=float, default=2.0)
    ap.add_argument("--tx-control", dest="tx_control", default="127.0.0.1:5123")
    ap.add_argument("--outdir", default="/tmp/phase_restart")
    ap.add_argument("--settle-between", type=float, default=5.0,
                    help="pause between runs, so the device is fully released")
    a = ap.parse_args()

    os.makedirs(a.outdir, exist_ok=True)
    runs = []

    for k in range(a.runs):
        csv = os.path.join(a.outdir, "run%02d.csv" % k)
        log = os.path.join(a.outdir, "run%02d.log" % k)
        cmd = [sys.executable, os.path.join(HERE, "twinrx_hop_test.py"),
               "--freqs", a.freq, "--gain", a.gain,
               "--cycles", str(a.cycles), "--dwell", str(a.dwell),
               "--tx-control", a.tx_control, "--log", csv]
        print("\n=== run %d of %d ===" % (k + 1, a.runs), flush=True)
        print(" ".join(cmd), flush=True)
        with open(log, "w") as fh:
            rc = subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT)
        t_run = time.time()
        data = read_csv(csv)
        n = len(data[PAIRS[0]])
        if rc != 0 or n == 0:
            # Say so and keep the run out of the statistics. A run that failed
            # to see the tone would otherwise contribute a phase from noise.
            print("run %d produced no usable samples (exit %d). See %s"
                  % (k, rc, log), flush=True)
            runs.append(None)
            continue
        print("run %d: %d samples  " % (k, n)
              + "  ".join("%s %+7.2f deg (spread %.2f)"
                          % (p, circ_mean_deg(data[p]), circ_spread_deg(data[p]))
                          for p in PAIRS), flush=True)
        runs.append((t_run, data))
        if k < a.runs - 1:
            time.sleep(a.settle_between)

    good = [r for r in runs if r is not None]
    print("\n" + "=" * 74)
    print("RESTART REPEATABILITY at %s Hz, gain %s dB -- %d of %d runs usable"
          % (a.freq, a.gain, len(good), a.runs))
    print("=" * 74)
    if len(good) < 2:
        print("Not enough usable runs to compare. Nothing is concluded here.")
        return 1

    print("%-9s %12s %12s %12s   %s"
          % ("pair", "within-run", "between-run", "trend", "verdict"))
    print("%-9s %12s %12s %12s"
          % ("", "(noise)", "(restart)", "(first->last)"))
    print("-" * 74)
    t0 = good[0][0]
    minutes = (good[-1][0] - t0) / 60.0
    for p in PAIRS:
        within = max(circ_spread_deg(r[p]) for _, r in good)
        means = [circ_mean_deg(r[p]) for _, r in good]
        between = circ_spread_deg(means)
        # Unwrap about the first run so a trend reads as a trend.
        rel = [np.rad2deg(np.angle(np.exp(1j * np.deg2rad(m - means[0]))))
               for m in means]
        steps = np.diff(rel)
        monotonic = len(steps) >= 2 and (np.all(steps > 0) or np.all(steps < 0))
        trend = rel[-1] - rel[0]

        if between <= max(2.0 * within, 0.3):
            verdict = "survives restart"
        elif monotonic and abs(trend) >= 0.7 * between:
            verdict = "DRIFTING WITH TIME"
        else:
            verdict = "MOVES ON RESTART"
        print("%-9s %8.2f deg %8.2f deg %8.2f deg   %s"
              % (p, within, between, trend, verdict))
    print("-" * 74)
    for p in PAIRS:
        print("  %-9s per-run means: %s" % (
            p, "  ".join("%+7.2f" % circ_mean_deg(r[p]) for _, r in good)))
    print("\n%d runs spanning %.1f minutes." % (len(good), minutes))
    print("A monotonic first-to-last trend is drift with time or temperature,\n"
          "not something a restart re-randomises: the same sequence would\n"
          "appear without restarting at all. Only a between-run spread that is\n"
          "NOT monotonic points at startup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
