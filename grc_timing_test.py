#!/usr/bin/env python3
"""Stage B3a: can a GNU Radio flowgraph know the radio time of every sample?

guru's blocks can only switch on the exact sample if sample offset -> radio
time is known. gr-uhd attaches rx_time tags, but on this X310 the packet
timestamps step at 2x, so nothing about the tags is assumed here. Instead the
radio itself writes markers into the samples: with the HackRF tone on band A,
timed band changes A -> B at known radio times Tm make the tone vanish at a
definite sample. For each marker the sample where it vanished is compared with
the sample predicted from the tags.

Checked before and after a deliberate overflow (the sink stalls for 3 s):
  * rx_time on the first sample: is it the right anchor?
  * rx_time tags emitted later (retunes, overflow): what do their values mean?

    python3 grc_timing_test.py
"""
import json
import os
import time

import numpy as np
import pmt
from gnuradio import gr, uhd

from dwell_test import tx_freq

FS = 1e6
NCH = 4
A, B = 2.4e9, 5.2e9
GAIN = {A: 46.0, B: 60.0}
TRIM = (0.0, -13.3, 1.5, -1.7)
STEP, SECOND = 0.0004, 0.003
PB = 50                                  # power block, samples (50 us)


class Rec(gr.sync_block):
    def __init__(self):
        gr.sync_block.__init__(self, "rec", in_sig=[np.complex64] * NCH, out_sig=None)
        self.tags = []
        self.pw = []
        self.stall = 0.0
        self.carry = np.zeros(0, np.complex64)
        self.carry_off = 0

    def work(self, input_items, output_items):
        ins = input_items
        n = len(ins[0])
        base = self.nitems_read(0)
        for t in self.get_tags_in_window(0, 0, n):
            v = t.value
            if pmt.is_tuple(v) and pmt.length(v) == 2:
                v = pmt.to_uint64(pmt.tuple_ref(v, 0)) + pmt.to_double(pmt.tuple_ref(v, 1))
            elif pmt.is_number(v):
                v = pmt.to_double(v)
            else:
                v = str(v)
            self.tags.append((t.offset, pmt.symbol_to_string(t.key), v))
        x = np.concatenate([self.carry, ins[0]])
        off0 = base - len(self.carry)
        nb = len(x) // PB
        if nb:
            self.pw.append((off0, np.mean(np.abs(x[:nb * PB].reshape(nb, PB)) ** 2, axis=1)))
        self.carry = x[nb * PB:].copy()
        if self.stall:
            s, self.stall = self.stall, 0.0
            time.sleep(s)
        return n


def band_change(src, f, T):
    g = [GAIN[f] + TRIM[c] for c in range(NCH)]
    src.set_command_time(uhd.time_spec(T))
    for c in range(NCH):
        src.set_gain(g[c], c)
    req = uhd.tune_request(f)
    req.rf_freq = f
    req.rf_freq_policy = uhd.tune_request.POLICY_MANUAL
    req.dsp_freq_policy = uhd.tune_request.POLICY_NONE
    for c in range(NCH):
        src.set_command_time(uhd.time_spec(T + c * STEP))
        src.set_center_freq(req, c)
    src.set_command_time(uhd.time_spec(T + SECOND))
    for c in range(NCH):
        src.set_center_freq(req, c)
    src.clear_command_time()


def main():
    tx_freq(A)
    src = uhd.usrp_source("addr=192.168.10.2,recv_buff_size=33554432",
                          uhd.stream_args(cpu_format="fc32", channels=list(range(NCH))))
    src.set_clock_source("internal", 0)
    src.set_subdev_spec("A:0 A:1 B:0 B:1", 0)
    src.set_samp_rate(FS)
    src.set_time_unknown_pps(uhd.time_spec())
    for c in range(NCH):
        src.set_antenna("RX1" if c % 2 == 0 else "RX2", c)
        src.set_auto_dc_offset(True, c)
        try:
            src.set_lo_export_enabled(False, uhd.ALL_LOS, c)
        except Exception as e:
            print("clear export ch%d: %s" % (c, e))
    for c, s in enumerate(["external", "external", "internal", "companion"]):
        src.set_lo_source(s, uhd.ALL_LOS, c)
    src.set_lo_export_enabled(True, uhd.ALL_LOS, 2)
    for c in range(NCH):
        src.set_gain(GAIN[A] + TRIM[c], c)
    req = uhd.tune_request(A)
    req.rf_freq = A
    req.rf_freq_policy = uhd.tune_request.POLICY_MANUAL
    req.dsp_freq = 0.0
    req.dsp_freq_policy = uhd.tune_request.POLICY_MANUAL
    for c in range(NCH):
        src.set_center_freq(req, c)

    rec = Rec()
    tb = gr.top_block()
    for c in range(NCH):
        tb.connect((src, c), (rec, c))
    t_start_host = time.time()
    tb.start()
    time.sleep(1.5)

    markers = []

    def marker_pair():
        # A -> B at T (tone vanishes), back to A 200 ms later
        T = src.get_time_now().get_real_secs() + 0.05
        band_change(src, B, T)
        time.sleep(0.2)
        T2 = src.get_time_now().get_real_secs() + 0.05
        band_change(src, A, T2)
        markers.append(T)
        time.sleep(0.3)

    for _ in range(3):
        marker_pair()
    stall_at = src.get_time_now().get_real_secs()
    rec.stall = 3.0
    time.sleep(4.5)
    for _ in range(3):
        marker_pair()
    tb.stop()
    tb.wait()

    # where did the tone vanish?
    offs = np.concatenate([o + np.arange(len(p)) * PB for o, p in rec.pw])
    pw = 10 * np.log10(np.concatenate([p for _, p in rec.pw]) + 1e-20)
    hi = np.percentile(pw, 90)
    lo = np.percentile(pw, 10)
    mid = (hi + lo) / 2.0
    tone = pw > mid
    falls = offs[1:][tone[:-1] & ~tone[1:]]

    rxt = [(o, v) for o, k, v in rec.tags if k == "rx_time"]
    print("tone level %.1f dB, no-tone %.1f dB (ch0)" % (hi, lo))
    print("rx_time tags: %d" % len(rxt))
    for o, v in rxt[:12]:
        print("   offset %10d   value %.6f" % (o, v))
    other = {}
    for o, k, v in rec.tags:
        other[k] = other.get(k, 0) + 1
    print("all tag keys seen:", other)

    t0_off, t0 = rxt[0]
    later = [(o, v) for o, v in rxt[1:]]
    print("\nmarker check (tone should vanish ~0.2 ms after each timed change):")
    res = []
    for Tm in markers:
        # nearest actual fall to the prediction from the first tag
        n_pred0 = t0_off + (Tm - t0) * FS
        cand = falls[np.argmin(np.abs(falls - n_pred0))] if len(falls) else None
        row = {"Tm": Tm, "pred_from_first_tag": n_pred0, "fall": int(cand) if cand is not None else None}
        # predictions from the most recent later rx_time tag before the fall
        if cand is not None:
            prev = [(o, v) for o, v in later if o <= cand]
            if prev:
                o, v = prev[-1]
                row["last_tag_offset"] = int(o)
                row["pred_raw"] = o + (Tm - v) * FS
                row["pred_2x"] = o + (Tm - (t0 + (v - t0) / 2.0)) * FS
        res.append(row)
        after = Tm > stall_at
        print("  Tm %.4f %-15s fall at %s | first-tag pred err %s us | last-tag raw err %s us | last-tag 2x err %s us"
              % (Tm, "(after overflow)" if after else "(before)", row["fall"],
                 "%.0f" % (row["fall"] - n_pred0) if row["fall"] is not None else "-",
                 "%.0f" % (row["fall"] - row["pred_raw"]) if "pred_raw" in row else "-",
                 "%.0f" % (row["fall"] - row["pred_2x"]) if "pred_2x" in row else "-"))

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "grc_timing_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
    with open(path, "w") as fh:
        json.dump({"tags": rec.tags, "markers": markers, "stall_at": stall_at,
                   "falls": falls.tolist(), "rows": res}, fh, indent=1, default=float)
    print("\nraw data: %s" % path)


if __name__ == "__main__":
    main()
