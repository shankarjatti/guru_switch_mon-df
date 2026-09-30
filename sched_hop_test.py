#!/usr/bin/env python3
"""Stage B2: hopping scheduled on the radio clock, with guard intervals.

Slot k starts at radio time S_k = S_0 + k * slot. The band change for slot k
(gains + RF on all four channels) is a timed command stamped S_k, sent by the
host during the previous slot's dwell. The radio executes it at S_k exactly,
so host jitter cannot move a slot. The DDC is pinned to 0 Hz at startup and
never commanded again.

Samples are labelled by radio time (stream start + n / fs). Around every
switch a guard is discarded on BOTH sides:
    [S_k - guard_pre , S_k + guard_post)   -> discarded
    [S_k + guard_post, S_k+1 - guard_pre)  -> the dwell ("on") window

Safety rules on the host:
  * a change is only sent if at least min_slack of radio time is left before
    S_k, otherwise the slot is skipped and counted -- never a late command
  * the band change is sched_band_change (staggered + second timed pass),
    measured to give exactly guru's phases
  * lo_locked is read inside the post-guard of every slot and must be True;
    nothing is read from the radio while a timed change is still waiting

The tone is parked on one band at a time; the test runs once per band.
Measured from the samples, for every tone visit:
  * steady over the whole dwell window (tone coherence > 0.9 on all channels,
    phase within 1 deg of the window's own mean)
  * how long before S_k+1 the old band's samples are first disturbed
    (needs to be later than -guard_pre)
  * how long after S_k the new band's samples are steady for good
    (needs to be earlier than +guard_post)
  * when the tone appears on the new band, relative to S_k
  * visit-to-visit phase repeatability
  * the scheduled phases equal a guru-tune reference taken in the same run

    python3 sched_hop_test.py --on 0.010 --off 0.010 --cycles 200
"""
import argparse
import json
import os
import time

import numpy as np
import uhd

from tune_speed_test import setup, BANDS, NCH, LO_MASTER, SAMP_RATE
from timed_tune_test import dsp_zero_tune, gains_for
from tune_method_phase_test import sched_band_change, m_guru
from dwell_test import (Reader, tx_freq, wrap, BLOCK, PHASE_TOL, COH_MIN,
                        GURU_TABLE)

BT = BLOCK / SAMP_RATE


class DevClock:
    """Host view of the radio clock, refreshed on every read."""

    def __init__(self, u):
        self.u = u
        self.offset = 0.0
        self.now()

    def now(self):
        a = time.perf_counter()
        d = self.u.get_time_now().get_real_secs()
        b = time.perf_counter()
        self.offset = d - (a + b) / 2.0
        return d

    def sleep_until(self, dev_t):
        while True:
            r = dev_t - (time.perf_counter() + self.offset)
            if r <= 0:
                return
            time.sleep(r - 0.0005 if r > 0.001 else 0.0001)


def run_schedule(u, clk, gains, S0, nslots, slot, band_seq, min_slack, lock_check):
    """Per slot k: verify slot k's lock at S_k + lock_check, then send slot k+1.

    Nothing is read from the radio while a timed change is waiting: a read is
    queued behind the change and only returns once it has executed. Slot k's
    commands (T .. T + SECOND_PASS) have run by S_k + lock_check, so both the
    lock read and the clock read there return at once.
    """
    log = [{"k": k, "freq": BANDS[band_seq[k]][0], "S": S0 + k * slot}
           for k in range(nslots)]

    def send(k):
        r = log[k]
        d = clk.now()
        r["slack_before"] = r["S"] - d
        if r["slack_before"] < min_slack:
            r.update(sent=False, skipped=True)
            return
        h0 = time.perf_counter()
        sched_band_change(u, r["freq"], gains[r["freq"]], r["S"])
        h1 = time.perf_counter()
        r.update(sent=True, skipped=False, send_s=h1 - h0,
                 slack_after=r["S"] - (h1 + clk.offset))
        r["late"] = r["slack_after"] <= 0

    send(0)
    for k in range(nslots):
        r = log[k]
        clk.sleep_until(r["S"] + lock_check)
        if r.get("sent"):
            r["locked"] = u.get_rx_sensor("lo_locked", LO_MASTER).to_bool()
            r["lock_read_rel"] = time.perf_counter() + clk.offset - r["S"]
        if k + 1 < nslots:
            send(k + 1)
    return log


def steady_mask(C, P, cols, ref):
    c, pw = C[:, cols], P[:, cols]
    coh = np.abs(c) / np.sqrt(pw[0][None] * pw[1:])
    dev = wrap(np.degrees(np.angle(c)) - ref[:, None])
    return np.all(np.abs(dev) < PHASE_TOL, axis=0) & np.all(coh > COH_MIN, axis=0), dev, coh


def analyse_park(t, P, C, log, park, slot, gpre, gpost):
    visits = []
    by_k = {r["k"]: r for r in log}
    for r in log:
        k = r["k"]
        if r["freq"] != park or (k - 1) not in by_k or (k + 1) not in by_k:
            continue
        S, Sn = r["S"], r["S"] + slot
        w0, w1 = S + gpost, Sn - gpre
        win = (t >= w0 - 1e-9) & (t + BT <= w1 + 1e-9)
        v = {"k": k, "S": S, "window_ms": (w1 - w0) * 1e3,
             "window_blocks": int(win.sum())}
        if not win.any():
            v.update(ok=False, why="no samples in window")
            visits.append(v)
            continue
        ref = np.degrees(np.angle(np.sum(C[:, win], axis=1)))
        good_w, dev_w, coh_w = steady_mask(C, P, win, ref)
        v["ok"] = bool(good_w.all())
        v["phase_deg"] = ref.tolist()
        v["window_max_dev_deg"] = float(np.max(np.abs(dev_w)))
        v["window_min_coh"] = float(np.min(coh_w))
        # new band: steady for good from when, relative to S
        span = (t >= S - 0.002) & (t + BT <= w1 + 1e-9)
        g, _, _ = steady_mask(C, P, span, ref)
        ts = t[span]
        bad = np.where(~g)[0]
        v["steady_from_ms"] = float((ts[bad[-1] + 1] - S) * 1e3) if bad.size and bad[-1] + 1 < ts.size \
            else (float((ts[0] - S) * 1e3) if not bad.size else float("inf"))
        # old band: first disturbed block relative to the NEXT switch Sn
        span2 = (t >= w0 - 1e-9) & (t <= Sn + 0.003)
        g2, _, _ = steady_mask(C, P, span2, ref)
        ts2 = t[span2]
        badn = np.where(~g2)[0]
        v["disturbed_from_ms"] = float((ts2[badn[0]] - Sn) * 1e3) if badn.size else None
        # power step into this band, ch0, relative to S
        sp = (t >= S - 0.002) & (t <= S + 0.008)
        p0 = 10 * np.log10(P[0, sp])
        lo, hi = np.median(p0[:4]), np.median(p0[-4:])
        cross = np.where(p0 > (lo + hi) / 2)[0]
        v["power_step_ms"] = float((t[sp][cross[0]] - S) * 1e3) if cross.size and hi - lo > 10 else None
        v["power_step_db"] = float(hi - lo)
        visits.append(v)
    return visits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", default="addr=192.168.10.2")
    ap.add_argument("--on", type=float, default=0.010, help="dwell per slot, s")
    ap.add_argument("--off", type=float, default=0.010, help="switch time per slot, s")
    ap.add_argument("--guard-pre", type=float, default=0.00025,
                    help="part of OFF discarded before each switch, s")
    ap.add_argument("--lock-check", type=float, default=0.007,
                    help="read lo_locked this long after each switch, then send the next, s")
    ap.add_argument("--min-slack", type=float, default=0.008,
                    help="skip the slot if less radio time than this is left, s")
    ap.add_argument("--cycles", type=int, default=200)
    ap.add_argument("--park", default="2.4e9,5.2e9,5.8e9")
    ap.add_argument("--race-reads", action="store_true",
                    help="another thread reads rx freq/rate every ~5 ms, like gr-uhd's tag code")
    a = ap.parse_args()
    slot = a.on + a.off
    gpre = a.guard_pre
    gpost = a.off - gpre
    if slot % BT > 1e-9 and BT - slot % BT > 1e-9:
        raise SystemExit("slot must be a whole number of %.2f ms blocks" % (BT * 1e3))
    parks = [float(x) for x in a.park.split(",")]

    u = setup(a.addr)
    gains = {f: gains_for(u, g) for f, g in BANDS}
    for ch in range(NCH):
        u.set_rx_gain(gains[BANDS[2][0]][ch], ch)
    dsp_zero_tune(u, BANDS[2][0])
    time.sleep(0.3)
    rd = Reader(u)
    rd.start()
    time.sleep(1.0)
    clk = DevClock(u)
    race = {"run": True, "n": 0}
    if a.race_reads:
        import threading, random
        def _racer():
            while race["run"]:
                for c in range(NCH):
                    u.get_rx_freq(c)
                u.get_rx_rate(0)
                race["n"] += 1
                time.sleep(random.uniform(0.001, 0.008))
        threading.Thread(target=_racer, daemon=True).start()

    logs = {}
    txr = {}
    refwin = {}
    try:
        for park in parks:
            txr[park] = tx_freq(park)
            time.sleep(0.5)
            m_guru(u, park, gains[park])
            time.sleep(0.1)
            d = clk.now()
            refwin[park] = (d, d + 0.1)
            time.sleep(0.15)
            nslots = a.cycles * len(BANDS)
            seq = [k % len(BANDS) for k in range(nslots)]
            # first slot on a block boundary of the sample stream, 50 ms ahead
            now = clk.now()
            nb = np.ceil((now + 0.05 - rd.start_dev) / BT)
            S0 = rd.start_dev + nb * BT
            logs[park] = run_schedule(u, clk, gains, S0, nslots, slot, seq,
                                      a.min_slack, a.lock_check)
            clk.sleep_until(S0 + nslots * slot + 0.05)
    finally:
        race["run"] = False
        rd.run_flag = False
        rd.join(5.0)
        if a.race_reads:
            print("racing reads made: %d" % race["n"])

    t, P, C = rd.arrays()
    stream_s = rd.end_dev - rd.start_dev
    rate = rd.samples / stream_s
    real_err = {k: v for k, v in rd.errors.items() if k != "timeout"}

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out, exist_ok=True)
    base = os.path.join(out, "sched_%gon_%goff_%s" % (a.on * 1e3, a.off * 1e3, stamp))
    np.savez_compressed(base + "_blocks.npz", t=t, P=P, C=C)

    L, fails = [], []
    L.append("stream: %d samples/channel over %.3f s of radio time (%.0f/s), errors %s, gaps %d"
             % (rd.samples, stream_s, rate, real_err or "none", rd.gaps))
    if real_err or rd.gaps or not (0.995 * SAMP_RATE < rate < 1.0005 * SAMP_RATE):
        fails.append("stream")
    if abs(rd.first_ts - rd.start_dev) > 1e-6:
        fails.append("first packet time does not match the commanded start")
    allr = [r for p in parks for r in logs[p]]
    skipped = [r for r in allr if r["skipped"]]
    late = [r for r in allr if r.get("late")]
    unlocked = [r for r in allr if r["sent"] and not r["locked"]]
    sends = np.array([r["send_s"] for r in allr if r["sent"]]) * 1e3
    slk = np.array([r["slack_after"] for r in allr if r["sent"]]) * 1e3
    L.append("schedule: %d slots of %.2f ms (%.2f on / %.2f off, guard %.2f before + %.2f after each switch)"
             % (len(allr), slot * 1e3, a.on * 1e3, a.off * 1e3, gpre * 1e3, gpost * 1e3))
    L.append("  host send time p50 %.2f max %.2f ms; radio time left after sending: min %.2f ms"
             % (np.median(sends), sends.max(), slk.min()))
    L.append("  skipped slots %d, late commands %d, lock confirmed %d/%d"
             % (len(skipped), len(late), len(allr) - len(skipped) - len(unlocked), len(allr) - len(skipped)))
    if skipped:
        fails.append("%d slot(s) skipped" % len(skipped))
    if late:
        fails.append("%d LATE command(s)" % len(late))
    if unlocked:
        fails.append("%d slot(s) without lock" % len(unlocked))

    report = {"args": vars(a), "tx": {str(k): v for k, v in txr.items()},
              "stream": {"rate": rate, "errors": rd.errors, "gaps": rd.gaps,
                         "start_dev": rd.start_dev, "first_pkt_ts": rd.first_ts,
                         "pkt_ts_scale": rd.scale},
              "schedule": logs, "bands": {}}
    for park in parks:
        vs = analyse_park(t, P, C, logs[park], park, slot, gpre, gpost)
        ok = [v for v in vs if v["ok"]]
        ph = np.array([v["phase_deg"] for v in ok]) if ok else np.zeros((0, 3))
        mean = np.degrees(np.angle(np.sum(np.exp(1j * np.radians(ph)), axis=0))) if ok else np.full(3, np.nan)
        rep = np.max(np.abs(wrap(ph - mean[None])), axis=0) if ok else np.full(3, np.nan)
        sf = [v["steady_from_ms"] for v in vs if "steady_from_ms" in v]
        df = [v["disturbed_from_ms"] for v in vs if v.get("disturbed_from_ms") is not None]
        nodist = sum(1 for v in vs if "disturbed_from_ms" in v and v["disturbed_from_ms"] is None)
        pstep = [v["power_step_ms"] for v in vs if v.get("power_step_ms") is not None]
        report["bands"][str(park)] = {"visits": vs, "mean": mean.tolist(), "repeat": rep.tolist()}
        L.append("")
        L.append("tone on %.1f GHz (HackRF: %s): %d visits, steady over the whole %.2f ms window: %d/%d"
                 % (park / 1e9, txr[park].strip(), len(vs), a.on * 1e3, len(ok), len(vs)))
        if sf:
            L.append("  new band steady for good from %.2f .. %.2f ms after the switch  (guard after = %.2f ms, spare %.2f ms)"
                     % (min(sf), max(sf), gpost * 1e3, gpost * 1e3 - max(sf)))
        if df:
            L.append("  old band first disturbed %.3f .. %.3f ms relative to the next switch  (guard before = %.2f ms, spare %.3f ms)"
                     % (min(df), max(df), gpre * 1e3, gpre * 1e3 + min(df)))
        if nodist:
            L.append("  (%d visit(s) showed no disturbance within 3 ms after the next switch)" % nodist)
        if pstep:
            L.append("  tone appears on the new band %.3f .. %.3f ms after the switch (block = %.2f ms)"
                     % (min(pstep), max(pstep), BT * 1e3))
        L.append("  phase ch1/ch2/ch3 - ch0 (mean):        %8.2f %8.2f %8.2f deg" % tuple(mean))
        L.append("  visit-to-visit repeatability (max):    %8.3f %8.3f %8.3f deg" % tuple(rep))
        rw = (t >= refwin[park][0]) & (t + BT <= refwin[park][1])
        gref = np.degrees(np.angle(np.sum(C[:, rw], axis=1)))
        gdiff = wrap(mean - gref)
        report["bands"][str(park)]["guru_ref"] = gref.tolist()
        L.append("  guru-tune reference, same run:          %8.2f %8.2f %8.2f deg  (%d blocks)" % (*gref, int(rw.sum())))
        L.append("  scheduled minus guru reference:          %8.2f %8.2f %8.2f deg" % tuple(gdiff))
        if not ok or np.nanmax(np.abs(gdiff)) >= PHASE_TOL:
            fails.append("%.1f GHz: phase differs from guru's tune" % (park / 1e9))
        L.append("  difference from guru.grc table (info): %8.2f %8.2f %8.2f deg"
                 % tuple(wrap(m - g) for m, g in zip(mean, GURU_TABLE[park])))
        if len(ok) < len(vs):
            fails.append("%.1f GHz: %d visit(s) not steady" % (park / 1e9, len(vs) - len(ok)))
        if sf and max(sf) > gpost * 1e3:
            fails.append("%.1f GHz: settles after the guard" % (park / 1e9))
        if df and min(df) < -gpre * 1e3:
            fails.append("%.1f GHz: disturbed before the guard" % (park / 1e9))
        if ok and np.nanmax(rep) >= PHASE_TOL:
            fails.append("%.1f GHz: repeatability %.2f deg" % (park / 1e9, np.nanmax(rep)))

    verdict = ("SCHEDULED HOPPING %g ms ON / %g ms OFF (50%% duty on every slot): ACHIEVED"
               % (a.on * 1e3, a.off * 1e3)) if not fails else \
              ("SCHEDULED HOPPING %g ms ON / %g ms OFF: NOT ACHIEVED -- %s"
               % (a.on * 1e3, a.off * 1e3, "; ".join(fails)))
    L += ["", verdict]
    report["verdict"] = verdict
    print("\n".join(L))
    with open(base + ".json", "w") as fh:
        json.dump(report, fh, indent=1,
                  default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("\nraw data: %s.json  +  %s_blocks.npz" % (base, base))


if __name__ == "__main__":
    main()
