#!/usr/bin/env python3
"""Stage B1: does a TIMED-ONLY band change switch the LO at the scheduled time?

guru today tunes untimed first (the LO moves the moment the host sends it) and
then repeats the tune as a timed command. Scheduling hops on the radio clock
needs the opposite: the host sends the whole band change -- gains and RF tune
on all four channels -- stamped with a future radio time T, and the radio
executes it at T no matter when the host got round to sending it.

The DDC is never part of it: its frequency is 0 Hz on every band (read back
from UHD), so it is set once, untimed, at startup and never touched again.

Per hop this records, against T:
  * how long the host spends issuing the commands, and the slack left before T
    (a command issued after T is late -- the case that breaks this radio)
  * the lock bit right after the calls: still high means nothing moved early
  * when the lock bit drops and when it is back (3 reads in a row)

    python3 timed_tune_test.py --leads 0.02,0.01,0.005 --cycles 30
"""
import argparse
import json
import os
import time

import numpy as np
import uhd

from tune_speed_test import setup, BANDS, NCH, LO_MASTER, GAIN_TRIM, Reader


def dsp_zero_tune(u, freq):
    """Untimed tune with the DDC pinned at 0 Hz. Startup only."""
    req = uhd.types.TuneRequest(freq)
    req.rf_freq = freq
    req.rf_freq_policy = uhd.types.TuneRequestPolicy.manual
    req.dsp_freq = 0.0
    req.dsp_freq_policy = uhd.types.TuneRequestPolicy.manual
    return [u.set_rx_freq(req, ch) for ch in range(NCH)]


def gains_for(u, gain):
    out = []
    for ch in range(NCH):
        rng = u.get_rx_gain_range(ch)
        out.append(max(rng.start(), min(rng.stop(), gain + GAIN_TRIM[ch])))
    return out


def timed_band_change(u, freq, gains, T):
    """Gains + RF on all channels, all stamped with radio time T. DDC untouched."""
    u.set_command_time(uhd.types.TimeSpec(T))
    for ch in range(NCH):
        u.set_rx_gain(gains[ch], ch)
    req = uhd.types.TuneRequest(freq)
    req.rf_freq = freq
    req.rf_freq_policy = uhd.types.TuneRequestPolicy.manual
    req.dsp_freq_policy = uhd.types.TuneRequestPolicy.none
    res = [u.set_rx_freq(req, ch) for ch in range(NCH)]
    u.clear_command_time()
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", default="addr=192.168.10.2")
    ap.add_argument("--leads", default="0.02,0.01,0.005",
                    help="how far ahead of T the host starts sending, s")
    ap.add_argument("--cycles", type=int, default=30)
    ap.add_argument("--dwell", type=float, default=0.01)
    ap.add_argument("--watch", type=float, default=0.03,
                    help="watch the lock bit this long after T, s")
    a = ap.parse_args()
    leads = [float(x) for x in a.leads.split(",")]

    u = setup(a.addr)
    gains = {f: gains_for(u, g) for f, g in BANDS}
    for ch in range(NCH):
        u.set_rx_gain(gains[BANDS[0][0]][ch], ch)
    r = dsp_zero_tune(u, BANDS[0][0])
    print("startup: DDC pinned, dsp = %s Hz" % [x.actual_dsp_freq for x in r])
    time.sleep(0.3)
    rd = Reader(u)
    rd.start()
    time.sleep(1.0)

    hops = []
    try:
        for lead in leads:
            cur = 0
            for _ in range(a.cycles * len(BANDS)):
                nxt = (cur + 1) % len(BANDS)
                f = BANDS[nxt][0]
                h_a = time.perf_counter()
                now = u.get_time_now().get_real_secs()
                h_b = time.perf_counter()
                T = now + lead
                T_host = (h_a + h_b) / 2.0 + lead
                res = timed_band_change(u, f, gains[f], T)
                tc = time.perf_counter()
                first = u.get_rx_sensor("lo_locked", LO_MASTER).to_bool()
                t_first = time.perf_counter()
                reads = [(t_first - T_host, first)]
                drop = lock = None
                good = 0
                while time.perf_counter() < T_host + a.watch:
                    x = time.perf_counter()
                    v = u.get_rx_sensor("lo_locked", LO_MASTER).to_bool()
                    m = (x + time.perf_counter()) / 2.0
                    reads.append((m - T_host, v))
                    if not v:
                        if drop is None:
                            drop = m
                        good = 0
                    elif drop is not None:
                        if good == 0:
                            lock = m
                        good += 1
                hops.append({
                    "lead": lead, "from": BANDS[cur][0], "to": f,
                    "calls_s": tc - h_b, "slack_s": T_host - tc,
                    "locked_right_after_calls": first,
                    "first_read_before_T": t_first < T_host,
                    "drop_after_T_s": None if drop is None else drop - T_host,
                    "lock_after_T_s": None if (lock is None or good < 3) else lock - T_host,
                    "rf_off_hz": [x.actual_rf_freq - f for x in res],
                    "dsp_hz": [x.actual_dsp_freq for x in res],
                    "reads": [(round(t, 6), v) for t, v in reads],
                })
                cur = nxt
                time.sleep(a.dwell)
    finally:
        rd.run_flag = False
        rd.join(3.0)

    secs = rd.t_end - rd.t_start
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "timed_tune_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
    with open(path, "w") as fh:
        json.dump({"args": vars(a), "stream": {"rate": rd.samples / secs, "errors": rd.errors},
                   "hops": hops}, fh, indent=1)

    ms = lambda v: 1e3 * v
    print("\nstream during test: %.0f samples/s per channel, errors %s"
          % (rd.samples / secs, rd.errors or "none"))
    for lead in leads:
        hs = [h for h in hops if h["lead"] == lead]
        calls = np.array([ms(h["calls_s"]) for h in hs])
        slack = np.array([ms(h["slack_s"]) for h in hs])
        early = [h for h in hs if h["first_read_before_T"] and not h["locked_right_after_calls"]]
        dr = [ms(h["drop_after_T_s"]) for h in hs if h["drop_after_T_s"] is not None]
        lk = [ms(h["lock_after_T_s"]) for h in hs if h["lock_after_T_s"] is not None]
        off = sum(1 for h in hs for x in h["rf_off_hz"] if abs(x) > 1.0)
        dsp = sum(1 for h in hs for x in h["dsp_hz"] if x != 0.0)
        print("\n=== lead %.1f ms: %d hops ===" % (ms(lead), len(hs)))
        print("  host send time:      p50 %.2f  max %.2f ms" % (np.median(calls), calls.max()))
        print("  slack before T:      min %.2f ms   (negative = LATE command)   late hops: %d"
              % (slack.min(), int((slack <= 0).sum())))
        print("  LO moved BEFORE T:   %d/%d hops (lock bit already low right after sending)" % (len(early), len(hs)))
        print("  lock drop after T:   %d/%d hops  %s" % (len(dr), len(hs),
              "" if not dr else "min %.3f  mean %.3f  max %.3f ms" % (min(dr), np.mean(dr), max(dr))))
        print("  relocked after T:    %d/%d hops  %s" % (len(lk), len(hs),
              "" if not lk else "min %.3f  mean %.3f  max %.3f ms" % (min(lk), np.mean(lk), max(lk))))
        print("  RF off target > 1 Hz: %d   DDC touched (dsp != 0): %d" % (off, dsp))
    print("\nraw data: %s" % path)


if __name__ == "__main__":
    main()
