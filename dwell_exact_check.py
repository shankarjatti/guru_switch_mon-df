#!/usr/bin/env python3
"""Prove the dwell is fixed: measure the hop marks of a real radio-clock run.

Runs twinrx_radio_source (the C++ engine) for --secs and records every
hop_off / hop_on tag on stream 0. For every slot it reports, in samples
(1 sample = 1 us at 1 Msps):
  * dwell  = hop_on  -> next hop_off     (must be exactly dwell * fs)
  * switch = hop_off -> hop_on           (must be exactly settle * fs)
  * period = hop_off -> next hop_off     (must be exactly (settle + dwell) * fs)
Any slot the engine did not mark valid shows up as a missing hop_on.

    python3 dwell_exact_check.py --secs 60
"""
import argparse
import time

import numpy as np
import pmt
from gnuradio import gr, blocks

import doa


class TagRec(gr.sync_block):
    def __init__(self):
        gr.sync_block.__init__(self, "tagrec", in_sig=[np.complex64], out_sig=None)
        self.ev = []

    def work(self, input_items, output_items):
        n = len(input_items[0])
        for t in self.get_tags_in_window(0, 0, n):
            k = pmt.symbol_to_string(t.key)
            if k in ("hop_on", "hop_off"):
                self.ev.append((int(t.offset), k, pmt.to_double(t.value)))
        return n


ap = argparse.ArgumentParser()
ap.add_argument("--secs", type=float, default=60.0)
a = ap.parse_args()
src = doa.twinrx_radio_source(
    samp_rate=1e6, addresses="addr=192.168.10.2",
    bands=[(2.4e9, 46, 0.01), (5.2e9, 60, 0.01), (5.8e9, 69, 0.01)],
    settle=0.01, guard_pre=0.00025, gain_trim=(0.0, -13.3, 1.5, -1.7),
    hop_enable=True, start_delay=0.5, tx_control="", park_freq=0)
rec = TagRec()
tb = gr.top_block()
tb.connect((src, 0), rec)
for c in range(1, 4):
    tb.connect((src, c), blocks.null_sink(gr.sizeof_gr_complex))
tb.start()
time.sleep(a.secs)
tb.stop()
tb.wait()

ev = sorted(set(rec.ev))
offs = [o for o, k, v in ev if k == "hop_off" and v > 0]
ons = [o for o, k, v in ev if k == "hop_on"]
period = np.diff(offs)
switch, dwell = [], []
for on in ons:
    prev_off = max([o for o in offs if o < on], default=None)
    next_off = min([o for o in offs if o > on], default=None)
    if prev_off is not None:
        switch.append(on - prev_off)
    if next_off is not None:
        dwell.append(next_off - on)
st = src.get_schedule_stats()
print("slots scheduled %d, marked valid (hop_on) %d, engine: %s" % (len(offs), len(ons), st))
for name, x, want in (("dwell", dwell, 10000), ("switch", switch, 10000), ("period", period, 20000)):
    x = np.array(x)
    print("%-6s: %d slots  min %d  max %d samples  (must be exactly %d)  -> %s"
          % (name, len(x), x.min(), x.max(), want,
             "EXACT ON EVERY SLOT" if len(x) and x.min() == x.max() == want else "NOT EXACT"))
