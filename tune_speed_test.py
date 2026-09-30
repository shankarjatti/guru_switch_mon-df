#!/usr/bin/env python3
"""Stage 1a: how fast can the USRP-2945 really retune between guru's bands?

Same radio setup and the same tune sequence as twinrx_hopping_source /
twinrx_usrp_source (gain + trim, untimed pass, timed RF-only pass with the DDC
kept out), minus the fixed 80 ms sleep in _relock_lo. The 4-channel stream runs
the whole time, as it does in guru.

Per hop it records, on the host clock:
  * how long each group of calls takes (gain, untimed pass, timed pass)
  * when the timed command is due (device time now + margin, mapped to host)
  * every lo_locked reading on the LO master (ch2) until it has dropped and
    come back, so a reading from BEFORE the retune is never counted as lock

Nothing is inferred: if the lock bit is never seen to drop, that hop is
reported as "no drop seen" and gets no lock time.

    python3 tune_speed_test.py --margins 0.01,0.002,0.001 --cycles 30
"""
import argparse
import json
import os
import threading
import time

import numpy as np
import uhd

BANDS = [(2.4e9, 46.0), (5.2e9, 60.0), (5.8e9, 69.0)]
GAIN_TRIM = (0.0, -13.3, 1.5, -1.7)
LO_SRC = ["external", "external", "internal", "companion"]
LO_MASTER = 2
SAMP_RATE = 1e6
NCH = 4


def setup(addr):
    u = uhd.usrp.MultiUSRP("%s,recv_buff_size=33554432" % addr)
    u.set_clock_source("internal", 0)
    u.set_rx_subdev_spec(uhd.usrp.SubdevSpec("A:0 A:1 B:0 B:1"), 0)
    u.set_rx_rate(SAMP_RATE)
    for attempt in range(1, 4):
        try:
            u.set_time_unknown_pps(uhd.types.TimeSpec(0.0))
            break
        except RuntimeError as e:
            print("[setup] PPS time sync attempt %d failed: %s" % (attempt, str(e).splitlines()[0]))
            if attempt == 3:
                raise
    for ch in range(NCH):
        u.set_rx_antenna("RX1" if ch % 2 == 0 else "RX2", ch)
        u.set_rx_dc_offset(True, ch)
    for ch in range(NCH):
        try:
            u.set_rx_lo_export_enabled(False, "all", ch)
        except Exception as e:
            print("[setup] clearing LO export on ch%d: %s" % (ch, e))
    for ch in range(NCH):
        u.set_rx_lo_source(LO_SRC[ch], "all", ch)
    u.set_rx_lo_export_enabled(True, "all", LO_MASTER)
    return u


def set_gain(u, gain):
    for ch in range(NCH):
        rng = u.get_rx_gain_range(ch)
        u.set_rx_gain(max(rng.start(), min(rng.stop(), gain + GAIN_TRIM[ch])), ch)


def tune(u, freq, margin):
    """guru's tune sequence without the sleep. Returns timings and due time."""
    t = {}
    t["t0"] = time.perf_counter()
    res0 = u.set_rx_freq(uhd.types.TuneRequest(freq), 0)
    req = uhd.types.TuneRequest(freq)
    req.rf_freq = freq
    req.rf_freq_policy = uhd.types.TuneRequestPolicy.manual
    req.dsp_freq = res0.actual_dsp_freq
    req.dsp_freq_policy = uhd.types.TuneRequestPolicy.manual
    for ch in (1, 2, 3):
        u.set_rx_freq(req, ch)
    t["t_untimed"] = time.perf_counter()
    # Does the untimed pass alone already move the synthesiser?
    t["lock_after_untimed"] = u.get_rx_sensor("lo_locked", LO_MASTER).to_bool()
    t["t_untimed_read"] = time.perf_counter()

    h_a = time.perf_counter()
    now = u.get_time_now()
    h_b = time.perf_counter()
    due_host = (h_a + h_b) / 2.0 + margin
    u.set_command_time(now + uhd.types.TimeSpec(margin))
    treq = uhd.types.TuneRequest(freq)
    treq.rf_freq = freq
    treq.rf_freq_policy = uhd.types.TuneRequestPolicy.manual
    treq.dsp_freq_policy = uhd.types.TuneRequestPolicy.none
    results = [u.set_rx_freq(treq, ch) for ch in range(NCH)]
    u.clear_command_time()
    t["t_timed"] = time.perf_counter()
    t["due"] = due_host
    t["now_rtt"] = h_b - h_a
    t["actual_rf"] = [r.actual_rf_freq for r in results]
    return t


def watch_lock(u, due, limit, pre=None, post=0.0):
    """Poll lo_locked until it has dropped and returned (3 reads in a row).

    pre is (host_time, value) for a read taken earlier in the hop, so a drop
    that already happened during the untimed pass is not missed."""
    reads = []
    seen_false = None
    if pre is not None:
        reads.append((round(pre[0] - due, 6), pre[1]))
        if not pre[1]:
            seen_false = pre[0]
    lock_at = None
    good = 0
    while time.perf_counter() < due + limit:
        a = time.perf_counter()
        v = u.get_rx_sensor("lo_locked", LO_MASTER).to_bool()
        b = time.perf_counter()
        m = (a + b) / 2.0
        reads.append((round(m - due, 6), v))
        if not v:
            if seen_false is None:
                seen_false = m
            good = 0
        elif seen_false is not None:
            if good == 0:
                lock_at = m
            good += 1
            if good >= 3:
                break
    # Keep watching past the due time: the timed pass may relock the LO again.
    second_drop = None
    relock_at = None
    if good >= 3 and post > 0:
        while time.perf_counter() < max(due, lock_at) + post:
            a = time.perf_counter()
            v = u.get_rx_sensor("lo_locked", LO_MASTER).to_bool()
            m = (a + time.perf_counter()) / 2.0
            reads.append((round(m - due, 6), v))
            if not v and second_drop is None:
                second_drop = m
            if v and second_drop is not None and relock_at is None:
                relock_at = m
    return seen_false, (lock_at if good >= 3 else None), reads, second_drop, relock_at


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
        self.t_start = None

    def run(self):
        n = self.rx.get_max_num_samps()
        buf = np.zeros((NCH, n), dtype=np.complex64)
        md = uhd.types.RXMetadata()
        cmd = uhd.types.StreamCMD(uhd.types.StreamMode.start_cont)
        cmd.stream_now = False
        cmd.time_spec = self.u.get_time_now() + uhd.types.TimeSpec(0.2)
        self.rx.issue_stream_cmd(cmd)
        while self.run_flag:
            got = self.rx.recv(buf, md, 0.5)
            if md.error_code != uhd.types.RXMetadataErrorCode.none:
                k = str(md.error_code).split(".")[-1]
                self.errors[k] = self.errors.get(k, 0) + 1
                continue
            if got and self.t_start is None:
                self.t_start = time.perf_counter()
            self.samples += got
        self.rx.issue_stream_cmd(uhd.types.StreamCMD(uhd.types.StreamMode.stop_cont))
        self.t_end = time.perf_counter()


def pct(v, p):
    return float(np.percentile(v, p)) if v else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", default="addr=192.168.10.2")
    ap.add_argument("--margins", default="0.01,0.002,0.001")
    ap.add_argument("--cycles", type=int, default=30)
    ap.add_argument("--dwell", type=float, default=0.02,
                    help="pause after lock before the next hop, s")
    ap.add_argument("--limit", type=float, default=0.05,
                    help="give up on a hop this long after the command is due, s")
    ap.add_argument("--post", type=float, default=0.015,
                    help="keep watching this long after due/lock for a second relock, s")
    a = ap.parse_args()
    margins = [float(m) for m in a.margins.split(",")]

    u = setup(a.addr)
    set_gain(u, BANDS[0][1])
    tune(u, BANDS[0][0], 0.1)
    time.sleep(0.2)
    rd = Reader(u)
    rd.start()
    time.sleep(1.0)

    hops = []
    try:
        for margin in margins:
            cur = 0
            for _ in range(a.cycles * len(BANDS)):
                nxt = (cur + 1) % len(BANDS)
                f, g = BANDS[nxt]
                tg0 = time.perf_counter()
                set_gain(u, g)
                tg1 = time.perf_counter()
                t = tune(u, f, margin)
                drop, lock, reads, drop2, relock2 = watch_lock(
                    u, t["due"], a.limit,
                    pre=(t["t_untimed_read"], t["lock_after_untimed"]),
                    post=a.post)
                hops.append({
                    "margin": margin,
                    "from": BANDS[cur][0], "to": f,
                    "gain_s": tg1 - tg0,
                    "untimed_s": t["t_untimed"] - t["t0"],
                    "timed_s": t["t_timed"] - t["t_untimed_read"],
                    "unlocked_after_untimed": not t["lock_after_untimed"],
                    "now_rtt_s": t["now_rtt"],
                    "timed_calls_done_before_due": t["t_timed"] < t["due"],
                    "drop_after_due_s": None if drop is None else drop - t["due"],
                    "lock_after_due_s": None if lock is None else lock - t["due"],
                    "start_to_lock_s": None if lock is None else lock - tg0,
                    "second_drop_after_due_s": None if drop2 is None else drop2 - t["due"],
                    "second_relock_after_due_s": None if relock2 is None else relock2 - t["due"],
                    "actual_rf": t["actual_rf"],
                    "n_reads": len(reads),
                    "reads": reads,
                })
                cur = nxt
                time.sleep(a.dwell)
    finally:
        rd.run_flag = False
        rd.join(3.0)

    secs = (rd.t_end - rd.t_start) if rd.t_start else 0.0
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "tune_speed_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
    with open(path, "w") as fh:
        json.dump({"args": vars(a), "bands": BANDS, "gain_trim": GAIN_TRIM,
                   "stream": {"samples_per_ch": rd.samples, "seconds": secs,
                              "rate": rd.samples / secs if secs else 0,
                              "errors": rd.errors},
                   "hops": hops}, fh, indent=1)

    print("\nstream during test: %.0f samples/s per channel (expect %.0f), errors %s"
          % (rd.samples / secs if secs else 0, SAMP_RATE, rd.errors or "none"))
    ms = lambda v: v * 1e3
    for margin in margins:
        print("\n=== cmd_time_margin %.1f ms ===" % ms(margin))
        print("%-12s %3s %6s %6s %6s | %5s | %-24s | %-24s" % (
            "hop", "n", "gain", "untim", "timed", "drop", "lock after due  min/mean/max",
            "start->lock  min/mean/p95/max"))
        for i in range(len(BANDS)):
            fr, to = BANDS[i][0], BANDS[(i + 1) % len(BANDS)][0]
            hs = [h for h in hops if h["margin"] == margin and h["from"] == fr]
            lk = [ms(h["lock_after_due_s"]) for h in hs if h["lock_after_due_s"] is not None]
            tot = [ms(h["start_to_lock_s"]) for h in hs if h["start_to_lock_s"] is not None]
            late = sum(1 for h in hs if not h["timed_calls_done_before_due"])
            badrf = sum(1 for h in hs for r in h["actual_rf"] if abs(r - to) > 1.0)
            print("%.1f->%.1f GHz %3d %6.2f %6.2f %6.2f | %2d/%-2d | %6.3f %6.3f %6.3f     | %6.2f %6.2f %6.2f %6.2f"
                  % (fr / 1e9, to / 1e9, len(hs),
                     np.mean([ms(h["gain_s"]) for h in hs]),
                     np.mean([ms(h["untimed_s"]) for h in hs]),
                     np.mean([ms(h["timed_s"]) for h in hs]),
                     len(lk), len(hs),
                     min(lk) if lk else float("nan"), np.mean(lk) if lk else float("nan"),
                     max(lk) if lk else float("nan"),
                     min(tot) if tot else float("nan"), np.mean(tot) if tot else float("nan"),
                     pct(tot, 95), max(tot) if tot else float("nan")))
            d2 = [h for h in hs if h["second_drop_after_due_s"] is not None]
            print("    second relock after the timed pass: %d/%d hops%s" % (
                len(d2), len(hs), "" if not d2 else
                "  drop at %.3f..%.3f ms, relocked by %.3f ms after due" % (
                    min(ms(h["second_drop_after_due_s"]) for h in d2),
                    max(ms(h["second_drop_after_due_s"]) for h in d2),
                    max(ms(h["second_relock_after_due_s"] or float("nan")) for h in d2))))
            ua = sum(1 for h in hs if h["unlocked_after_untimed"])
            print("    lock bit already low right after the untimed pass: %d/%d hops" % (ua, len(hs)))
            if late or badrf:
                print("    !! %d hop(s) finished issuing the timed pass AFTER it was due; "
                      "%d channel tune(s) landed off frequency" % (late, badrf))
    print("\nraw data: %s" % path)


if __name__ == "__main__":
    main()
