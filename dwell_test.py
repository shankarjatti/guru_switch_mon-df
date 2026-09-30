#!/usr/bin/env python3
"""Stage 2: does a given dwell really work on the USRP-2945?

The receiver hops 2.4 -> 5.2 -> 5.8 GHz with guru's radio setup and guru's tune
sequence (gain + trim, untimed pass, timed RF-only pass, DDC kept out), with a
fixed settle and the dwell under test. The HackRF tone is parked on ONE band at
a time -- a real signal does not follow the receiver either -- and the test is
repeated with the tone on each band.

Every sample is received. Each 0.25 ms block of the 4 channels is reduced to
channel powers and the cross products chN*conj(ch0), stamped with the radio's
own sample time. Each hop's start is stamped with the radio's time too, so the
windows are measured on the device clock, not assumed from host sleeps.

A dwell is reported ACHIEVED only if all of these hold:
  1. every hop, every band: lo_locked at the end of settle
  2. stream: no overflow, no time gap, ~1 Msps
  3. every tone visit: measured dwell window >= requested
  4. every tone visit: tone on all channels (coherence > 0.9) and phase within
     PHASE_TOL of the window's own mean over the WHOLE window (settle finished)
  5. per band: each visit's phase within PHASE_TOL of the mean of all visits

    python3 dwell_test.py --dwell 0.05 --cycles 60
"""
import argparse
import json
import os
import socket
import threading
import time

import numpy as np
import uhd

from tune_speed_test import setup, set_gain, BANDS, NCH, LO_MASTER, SAMP_RATE

BLOCK = 250                     # samples per analysis block = 0.25 ms
PHASE_TOL = 1.0                 # degrees
COH_MIN = 0.9
TX_CONTROL = ("127.0.0.1", 5123)
# guru.grc's table (chN - ch0, degrees). Reported for information only.
GURU_TABLE = {2.4e9: (173.34, -90.18, -173.78),
              5.2e9: (103.36, 52.41, 14.61),
              5.8e9: (83.53, 142.79, 156.39)}


def wrap(d):
    return (d + 180.0) % 360.0 - 180.0


def guru_tune(u, freq, margin):
    """Exactly the sequence in twinrx_usrp_source.set_center_freq, minus the sleep."""
    res0 = u.set_rx_freq(uhd.types.TuneRequest(freq), 0)
    req = uhd.types.TuneRequest(freq)
    req.rf_freq = freq
    req.rf_freq_policy = uhd.types.TuneRequestPolicy.manual
    req.dsp_freq = res0.actual_dsp_freq
    req.dsp_freq_policy = uhd.types.TuneRequestPolicy.manual
    for ch in (1, 2, 3):
        u.set_rx_freq(req, ch)
    now = u.get_time_now()
    u.set_command_time(now + uhd.types.TimeSpec(margin))
    treq = uhd.types.TuneRequest(freq)
    treq.rf_freq = freq
    treq.rf_freq_policy = uhd.types.TuneRequestPolicy.manual
    treq.dsp_freq_policy = uhd.types.TuneRequestPolicy.none
    for ch in range(NCH):
        u.set_rx_freq(treq, ch)
    u.clear_command_time()
    return now.get_real_secs() + margin


def tx_freq(freq):
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sk.settimeout(2.0)
    sk.sendto(("freq %d" % int(freq)).encode(), TX_CONTROL)
    reply = sk.recv(64).decode(errors="replace")
    sk.close()
    return reply


class Reader(threading.Thread):
    def __init__(self, u):
        super().__init__(daemon=True)
        args = uhd.usrp.StreamArgs("fc32", "sc16")
        args.channels = list(range(NCH))
        self.rx = u.get_rx_stream(args)
        self.u = u
        self.run_flag = True
        self.samples = 0
        self.errors = {}
        self.gaps = 0
        self.t, self.P, self.C = [], [], []

    def _flush(self, pend, i0):
        X = np.concatenate(pend, axis=1)
        nb = X.shape[1] // BLOCK
        if nb:
            Y = X[:, :nb * BLOCK].reshape(NCH, nb, BLOCK)
            self.P.append(np.mean(np.abs(Y) ** 2, axis=2))
            self.C.append(np.mean(Y[1:] * np.conj(Y[0])[None], axis=2))
            self.t.append(self.start_dev + (i0 + np.arange(nb) * BLOCK) / SAMP_RATE)
        rest = X[:, nb * BLOCK:]
        return [rest], i0 + nb * BLOCK, rest.shape[1]

    def run(self):
        """Sample n is taken at start_dev + n / SAMP_RATE.

        The start is a timed stream command on the radio clock, the same clock
        the hops are stamped with. The packet time_spec on this UHD 3.15 / X310
        advances at a multiple of real time (measured: 2x), so it is used only
        to detect lost samples: its step per packet must stay scale * got / fs,
        with scale measured here, not assumed.
        """
        n = self.rx.get_max_num_samps()
        buf = np.zeros((NCH, n), dtype=np.complex64)
        md = uhd.types.RXMetadata()
        cmd = uhd.types.StreamCMD(uhd.types.StreamMode.start_cont)
        cmd.stream_now = False
        self.start_dev = self.u.get_time_now().get_real_secs() + 0.2
        cmd.time_spec = uhd.types.TimeSpec(self.start_dev)
        self.rx.issue_stream_cmd(cmd)
        pend, pend_n = [], 0
        self.idx = 0                 # samples received so far
        blk_idx = 0                  # sample index of pend[0]
        prev_ts, prev_got = None, None
        self.scale = None
        self.first_ts = None
        steps = []
        while self.run_flag:
            got = self.rx.recv(buf, md, 0.5)
            if md.error_code != uhd.types.RXMetadataErrorCode.none:
                k = str(md.error_code).split(".")[-1]
                self.errors[k] = self.errors.get(k, 0) + 1
                continue
            if not got:
                continue
            ts = md.time_spec.get_real_secs()
            if self.first_ts is None:
                self.first_ts = ts
            if prev_ts is not None:
                step = (ts - prev_ts) / (prev_got / SAMP_RATE)
                if self.scale is None:
                    steps.append(step)
                    if len(steps) == 200:
                        self.scale = float(np.median(steps))
                elif abs(step - self.scale) > 0.01 * self.scale:
                    self.gaps += 1
            prev_ts, prev_got = ts, got
            pend.append(buf[:, :got].copy())
            pend_n += got
            self.idx += got
            if pend_n >= 20 * BLOCK:
                pend, blk_idx, pend_n = self._flush(pend, blk_idx)
        if pend:
            self._flush(pend, blk_idx)
        self.rx.issue_stream_cmd(uhd.types.StreamCMD(uhd.types.StreamMode.stop_cont))
        self.samples = self.idx
        self.end_dev = self.u.get_time_now().get_real_secs()

    def arrays(self):
        return (np.concatenate(self.t), np.concatenate(self.P, axis=1),
                np.concatenate(self.C, axis=1))


def sleep_until(t):
    while True:
        r = t - time.perf_counter()
        if r <= 0:
            return
        time.sleep(r - 0.0005 if r > 0.001 else 0.0001)


def run_hops(u, park, cycles, off, settle_after, dwell, margin, lock_wait=0.02):
    """One slot per band: OFF (commands + settle), then ON (dwell).

    The dwell starts at the LATEST of
      * hop start + off                     (the planned duty cycle)
      * commands finished + settle_after    (PLL lock time, host jitter excluded)
      * lo_locked confirmed on the LO master
    so no dwell ever starts on an unconfirmed lock. When that pushes the start
    past hop start + off, the slot is longer than planned and it is counted.
    """
    hops = []
    cur = 2                      # start so the first hop goes to 2.4 GHz
    for _ in range(cycles * len(BANDS)):
        nxt = (cur + 1) % len(BANDS)
        f, g = BANDS[nxt]
        h0 = time.perf_counter()
        a = time.perf_counter()
        d0 = u.get_time_now().get_real_secs()
        d0 -= (time.perf_counter() - a) / 2.0      # device time at h0, approx
        set_gain(u, g)
        due = guru_tune(u, f, margin)
        tc = time.perf_counter()
        target = max(h0 + off, tc + settle_after)
        sleep_until(target - 0.0003)
        reads = 0
        locked = False
        while True:
            locked = u.get_rx_sensor("lo_locked", LO_MASTER).to_bool()
            reads += 1
            if locked or time.perf_counter() > target + lock_wait:
                break
        sleep_until(target)
        on_h = time.perf_counter()
        sleep_until(on_h + dwell)
        hops.append({"park": park, "freq": f, "t0_dev": d0, "due_dev": due,
                     "on_dev": d0 + (on_h - h0),
                     "calls_s": tc - h0, "off_s": on_h - h0,
                     "locked": locked, "lock_reads": reads,
                     "off_stretched": on_h - h0 > off + 0.0002})
        cur = nxt
    return hops


def analyse(t, P, C, hops):
    bt = BLOCK / SAMP_RATE
    visits = []
    for i, h in enumerate(hops[:-1]):
        if h["freq"] != h["park"]:
            continue
        T0, Tend = h["t0_dev"], hops[i + 1]["t0_dev"]
        sel = (t >= T0) & (t + bt <= Tend)
        on = h["on_dev"]
        win = sel & (t >= on)
        v = {"freq": h["freq"], "t0_dev": T0,
             "off_ms": (on - T0) * 1e3,
             "window_ms": (Tend - on) * 1e3,
             "window_blocks": int(win.sum())}
        if win.sum() == 0:
            v["ok"] = False
            v["why"] = "no samples in dwell window"
            visits.append(v)
            continue
        c, pw = C[:, sel], P[:, sel]
        coh = np.abs(c) / np.sqrt(pw[0][None] * pw[1:])
        ref = np.degrees(np.angle(np.sum(C[:, win], axis=1)))
        dev = wrap(np.degrees(np.angle(c)) - ref[:, None])
        good = np.all(np.abs(dev) < PHASE_TOL, axis=0) & np.all(coh > COH_MIN, axis=0)
        ts = t[sel] - T0
        in_win = t[sel] >= on
        # first block from which every later block of the slot is good
        bad = np.where(~good)[0]
        settled_from = 0.0 if bad.size == 0 else (
            ts[bad[-1] + 1] if bad[-1] + 1 < ts.size else float("inf"))
        v.update({
            "phase_deg": ref.tolist(),
            "window_max_dev_deg": float(np.max(np.abs(dev[:, in_win]))),
            "window_min_coh": float(np.min(coh[:, in_win])),
            "settled_ms": settled_from * 1e3,
            "power_db": (10 * np.log10(np.mean(P[:, win], axis=1))).tolist(),
        })
        v["ok"] = bool(np.all(good[in_win]))
        if not v["ok"]:
            v["why"] = "phase or tone not steady inside the dwell window"
        visits.append(v)
    return visits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", default="addr=192.168.10.2")
    ap.add_argument("--dwell", type=float, required=True, help="seconds")
    ap.add_argument("--off", type=float, default=0.010,
                    help="planned off time per slot (commands + settle), s")
    ap.add_argument("--settle-after", type=float, default=0.007,
                    help="minimum wait after the commands are sent, s")
    ap.add_argument("--margin", type=float, default=0.002)
    ap.add_argument("--cycles", type=int, default=60)
    ap.add_argument("--park", default="2.4e9,5.2e9,5.8e9",
                    help="bands to park the HackRF tone on, one run each")
    a = ap.parse_args()
    parks = [float(x) for x in a.park.split(",")]

    u = setup(a.addr)
    set_gain(u, BANDS[0][1])
    guru_tune(u, BANDS[0][0], 0.1)
    time.sleep(0.3)
    rd = Reader(u)
    rd.start()
    time.sleep(1.0)

    hops = []
    tx = {}
    try:
        for park in parks:
            tx[park] = tx_freq(park)
            time.sleep(0.5)                 # let the HackRF settle on the new band
            hops += run_hops(u, park, a.cycles, a.off, a.settle_after, a.dwell, a.margin)
            time.sleep(0.05)
    finally:
        rd.run_flag = False
        rd.join(5.0)

    t, P, C = rd.arrays()
    # samples received vs radio time elapsed since the commanded start; the
    # stream stops a little before end_dev, so this can only read low, never high
    stream_s = rd.end_dev - rd.start_dev
    rate = rd.samples / stream_s

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out, exist_ok=True)
    base = os.path.join(out, "dwell_%gms_%s" % (a.dwell * 1e3, stamp))
    np.savez_compressed(base + "_blocks.npz", t=t, P=P, C=C)

    report = {"args": vars(a), "tx_replies": {str(k): v for k, v in tx.items()},
              "stream": {"rate": rate, "seconds": stream_s, "errors": rd.errors,
                         "gaps": rd.gaps, "pkt_ts_scale": rd.scale,
                         "start_dev": rd.start_dev, "first_pkt_ts": rd.first_ts},
              "bands": {}}
    lines = []
    fails = []
    unlocked = [h for h in hops if not h["locked"]]
    real_err = {k: v for k, v in rd.errors.items() if k != "timeout"}
    lines.append("stream: %d samples/channel over %.3f s of radio time (%.0f/s), errors %s, gaps %d"
                 % (rd.samples, stream_s, rate, real_err or "none", rd.gaps))
    lines.append("        packet timestamp step scale %.4f; first packet ts %.6f vs commanded start %.6f"
                 % (rd.scale, rd.first_ts, rd.start_dev))
    lines.append("hops: %d total, lock confirmed before dwell on %d/%d, commands "
                 "%.2f..%.2f ms" % (len(hops), len(hops) - len(unlocked), len(hops),
                                    min(h["calls_s"] for h in hops) * 1e3,
                                    max(h["calls_s"] for h in hops) * 1e3))
    if unlocked:
        fails.append("%d hop(s) never confirmed lock (waited %d ms)" % (len(unlocked), 20))
    offs = np.array([h["off_s"] for h in hops]) * 1e3
    stretched = [h for h in hops if h["off_stretched"]]
    lines.append("off time (hop start -> dwell start): min %.2f  mean %.2f  max %.2f ms; "
                 "stretched past %.1f ms on %d/%d hops"
                 % (offs.min(), offs.mean(), offs.max(), a.off * 1e3, len(stretched), len(hops)))
    if real_err or rd.gaps:
        fails.append("stream errors/gaps")
    if rate < 0.995 * SAMP_RATE or rate > 1.0005 * SAMP_RATE:
        fails.append("stream rate %.0f" % rate)
    if abs(rd.first_ts - rd.start_dev) > 1e-6:
        fails.append("first packet time does not match the commanded start")

    for park in parks:
        hp = [h for h in hops if h["park"] == park]
        vs = analyse(t, P, C, hp)
        good = [v for v in vs if v["ok"]]
        ph = np.array([v["phase_deg"] for v in good]) if good else np.zeros((0, 3))
        mean = np.degrees(np.angle(np.sum(np.exp(1j * np.radians(ph)), axis=0))) if good else [np.nan] * 3
        rep = np.max(np.abs(wrap(ph - mean[None])), axis=0) if good else [np.nan] * 3
        win = [v["window_ms"] for v in vs]
        st = [v["settled_ms"] for v in good]
        b = {"visits": len(vs), "visits_ok": len(good),
             "window_ms_min": min(win) if win else None,
             "window_ms_max": max(win) if win else None,
             "settled_ms_max": max(st) if st else None,
             "phase_mean_deg": list(map(float, mean)),
             "repeat_max_dev_deg": list(map(float, rep)),
             "vs_guru_table_deg": [float(wrap(m - g)) for m, g in zip(mean, GURU_TABLE[park])],
             "visits_detail": vs}
        report["bands"][str(park)] = b
        lines.append("")
        lines.append("tone on %.1f GHz (HackRF replied %r): %d visits" % (park / 1e9, tx[park].strip(), len(vs)))
        lines.append("  dwell window measured on device clock: %.2f .. %.2f ms (asked %.2f)"
                     % (b["window_ms_min"], b["window_ms_max"], a.dwell * 1e3))
        offv = [v["off_ms"] for v in vs if "off_ms" in v]
        lines.append("  off (switching) measured on device clock:  %.2f .. %.2f ms (planned %.2f)"
                     % (min(offv), max(offv), a.off * 1e3))
        lines.append("  visits steady over the whole window: %d/%d   settled by %.2f ms after hop start (worst)"
                     % (len(good), len(vs), b["settled_ms_max"] if st else float("nan")))
        lines.append("  phase ch1/ch2/ch3 - ch0 (mean of visits): %8.2f %8.2f %8.2f deg" % tuple(mean))
        lines.append("  visit-to-visit repeatability (max dev):   %8.3f %8.3f %8.3f deg" % tuple(rep))
        lines.append("  difference from guru.grc table (info):    %8.2f %8.2f %8.2f deg" % tuple(b["vs_guru_table_deg"]))
        if len(good) < len(vs):
            fails.append("%.1f GHz: %d visit(s) not steady" % (park / 1e9, len(vs) - len(good)))
        if win and min(win) < a.dwell * 1e3 - 1e3 * BLOCK / SAMP_RATE:
            fails.append("%.1f GHz: dwell window shorter than asked (%.2f ms)" % (park / 1e9, min(win)))
        if good and max(rep) >= PHASE_TOL:
            fails.append("%.1f GHz: visit-to-visit phase moves %.2f deg" % (park / 1e9, max(rep)))

    verdict = ("DWELL %g ms: ACHIEVED" % (a.dwell * 1e3)) if not fails else \
              ("DWELL %g ms: NOT ACHIEVED -- %s" % (a.dwell * 1e3, "; ".join(fails)))
    duty = np.array([a.dwell / (a.dwell + o / 1e3) for o in offs])
    duty_line = ("DUTY CYCLE %.0f%% (%.0f ms on / %.0f ms off): held on %d/%d hops, "
                 "measured %.1f%% .. %.1f%%" % (100 * a.dwell / (a.dwell + a.off), a.dwell * 1e3,
                 a.off * 1e3, len(hops) - len(stretched), len(hops),
                 100 * duty.min(), 100 * duty.max()))
    lines.append("")
    lines.append(verdict)
    lines.append(duty_line)
    report["duty"] = duty_line
    report["verdict"] = verdict
    report["hops"] = hops
    with open(base + ".json", "w") as fh:
        json.dump(report, fh, indent=1)
    print("\n".join(lines))
    print("\nraw data: %s.json  +  %s_blocks.npz" % (base, base))


if __name__ == "__main__":
    main()
