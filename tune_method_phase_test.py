#!/usr/bin/env python3
"""Stage B1b: which timed tuning method gives the SAME channel phases as guru?

guru's tune (untimed pass, then the same tune timed) is the reference: its
phases are what the calibration table is measured against. A radio-clock
scheduler needs a tune that is entirely timed. A timed tune that lands on the
right frequency but leaves the shared LO in another phase state would silently
invalidate the calibration, so each candidate is compared with the reference,
on every band, arriving from each of the other bands, several times.

Methods:
  guru      untimed pass, then timed pass 2 ms later (the reference itself)
  single    everything stamped T, once
  stagger   gains at T, channel c's tune at T + c * step (radio clock), once
  stagger2  as stagger, then the same tunes again at T + 3 ms (timed double tune)

Trial: park the HackRF on band f; tune to another band p with guru's method;
tune into f with the method under test; wait; capture; phase of chN vs ch0.

    python3 tune_method_phase_test.py --reps 5
"""
import argparse
import json
import os
import time

import numpy as np
import uhd

from tune_speed_test import setup, BANDS, NCH
from timed_tune_test import gains_for
from dwell_test import guru_tune, tx_freq, wrap

STEP = 0.0004


def set_gains(u, g):
    for ch in range(NCH):
        u.set_rx_gain(g[ch], ch)


def rf_req(freq):
    r = uhd.types.TuneRequest(freq)
    r.rf_freq = freq
    r.rf_freq_policy = uhd.types.TuneRequestPolicy.manual
    r.dsp_freq_policy = uhd.types.TuneRequestPolicy.none
    return r


def m_guru(u, f, g):
    set_gains(u, g)
    guru_tune(u, f, 0.002)


def m_single(u, f, g):
    T = u.get_time_now().get_real_secs() + 0.01
    u.set_command_time(uhd.types.TimeSpec(T))
    set_gains(u, g)
    for ch in range(NCH):
        u.set_rx_freq(rf_req(f), ch)
    u.clear_command_time()


def _stagger(u, f, g, T):
    u.set_command_time(uhd.types.TimeSpec(T))
    set_gains(u, g)
    for ch in range(NCH):
        u.set_command_time(uhd.types.TimeSpec(T + ch * STEP))
        u.set_rx_freq(rf_req(f), ch)
    u.clear_command_time()


def m_stagger(u, f, g):
    _stagger(u, f, g, u.get_time_now().get_real_secs() + 0.01)


SECOND_PASS = 0.003


def sched_band_change(u, f, g, T):
    """The whole band change on the radio clock, phase-equal to guru's tune.

    Gains at T, channel c's RF tune at T + c * STEP, then the same RF tunes
    again at T + SECOND_PASS. Measured: 30/30 trials within 0.1 deg of guru's
    untimed+timed tune; one pass alone leaves the shared LO in another phase
    state depending on the previous band. The DDC is not touched.
    """
    _stagger(u, f, g, T)
    u.set_command_time(uhd.types.TimeSpec(T + SECOND_PASS))
    for ch in range(NCH):
        u.set_rx_freq(rf_req(f), ch)
    u.clear_command_time()


def m_stagger2(u, f, g):
    sched_band_change(u, f, g, u.get_time_now().get_real_secs() + 0.01)


METHODS = {"guru": m_guru, "single": m_single, "stagger": m_stagger,
           "stagger2": m_stagger2}


def capture_phase(u, rx, n=32768):
    buf = np.zeros((NCH, n), dtype=np.complex64)
    md = uhd.types.RXMetadata()
    cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_done)
    cmd.num_samps = n
    cmd.stream_now = False
    cmd.time_spec = u.get_time_now() + uhd.types.TimeSpec(0.03)
    rx.issue_stream_cmd(cmd)
    got = 0
    while got < n:
        k = rx.recv(buf[:, got:], md, 1.0)
        if k == 0:
            break
        got += k
    x = buf[:, :got]
    c = np.mean(x[1:] * np.conj(x[0])[None], axis=1)
    p = np.mean(np.abs(x) ** 2, axis=1)
    coh = np.abs(c) / np.sqrt(p[0] * p[1:])
    return np.degrees(np.angle(c)), coh, got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addr", default="addr=192.168.10.2")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--methods", default="guru,single,stagger,stagger2")
    a = ap.parse_args()
    methods = a.methods.split(",")

    u = setup(a.addr)
    gains = {f: gains_for(u, g) for f, g in BANDS}
    args = uhd.usrp.StreamArgs("fc32", "sc16")
    args.channels = list(range(NCH))
    rx = u.get_rx_stream(args)

    trials = []
    ref = {}
    for f, _ in BANDS:
        tx_freq(f)
        time.sleep(0.5)
        # reference: guru's tune straight into f, 3 captures averaged
        m_guru(u, f, gains[f])
        time.sleep(0.05)
        caps = [capture_phase(u, rx)[0] for _ in range(3)]
        ref[f] = np.degrees(np.angle(np.mean(np.exp(1j * np.radians(caps)), axis=0)))
        others = [b[0] for b in BANDS if b[0] != f]
        for rep in range(a.reps):
            for p in others:
                for m in methods:
                    m_guru(u, p, gains[p])
                    time.sleep(0.03)
                    METHODS[m](u, f, gains[f])
                    time.sleep(0.03)
                    ph, coh, got = capture_phase(u, rx)
                    trials.append({"to": f, "from": p, "method": m, "rep": rep,
                                   "phase": ph.tolist(), "coh": coh.tolist(),
                                   "diff": wrap(ph - ref[f]).tolist(), "samples": got})

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "tune_method_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
    with open(path, "w") as fh:
        json.dump({"args": vars(a), "step": STEP,
                   "ref": {str(k): v.tolist() for k, v in ref.items()},
                   "trials": trials}, fh, indent=1)

    print("reference (guru tune) phases ch1/ch2/ch3 - ch0:")
    for f in ref:
        print("  %.1f GHz: %8.2f %8.2f %8.2f deg" % (f / 1e9, *ref[f]))
    for m in methods:
        tm = [t for t in trials if t["method"] == m]
        d = np.abs(np.array([t["diff"] for t in tm]))
        low = sum(1 for t in tm if min(t["coh"]) < 0.9)
        ok = int(np.sum(np.all(d < 1.0, axis=1)))
        print("\n=== %s: %d trials, within 1 deg of guru on all channels: %d/%d, low coherence: %d"
              % (m, len(tm), ok, len(tm), low))
        for f, _ in BANDS:
            for p in [b[0] for b in BANDS if b[0] != f]:
                dd = np.array([t["diff"] for t in tm if t["to"] == f and t["from"] == p])
                print("  %.1f -> %.1f GHz: diff ch1 %s | ch2 %s | ch3 %s" % (
                    p / 1e9, f / 1e9,
                    *[" ".join("%7.1f" % v for v in dd[:, c]) for c in range(3)]))
    print("\nraw data: %s" % path)


if __name__ == "__main__":
    main()
