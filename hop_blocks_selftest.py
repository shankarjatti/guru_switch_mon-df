#!/usr/bin/env python3
"""Offline self-test of the hop-mark blocks -- no radio needed.

Synthesises 4 channels hopping 3 bands (20 ms slots: 10 ms switching + 10 ms
dwell), a tone with known phases (10/20/30 deg) on band A only, the hop_off /
hop_on marks twinrx_radio_source would put on stream 0, and one slot of band A
deliberately left unmarked (as the source does for a late or unlocked slot).
Checks:
  * hop_tag_rotator removes exactly the band's table offsets
  * hop_band_select passes exactly the marked dwell samples of band A
  * no switching sample and no unmarked slot gets through
  * a window-start tag lands frame_offset samples into every window
  * hop_phase_meter: one reading per band-A window, NaN on a band with no tone
Exit status 0 only if every check passes.

    python3 hop_blocks_selftest.py
"""
import sys

import numpy as np
import pmt
from gnuradio import gr, blocks

import doa
from doa.hop_blocks import hop_tag_rotator, hop_band_select, hop_phase_meter

FS = 1e6
A, B, C = 2.4e9, 5.2e9, 5.8e9
BANDS = [A, B, C]
OFF, ON, GPRE = 0.010, 0.010, 0.00025
SLOT = OFF + ON
NSLOTS, BAD = 60, 9                     # slot 9 is band A and is left unmarked
PH = np.radians([10.0, 20.0, 30.0])
FRAME = 100


def main():
    n0 = 50000
    N = n0 + NSLOTS * int(SLOT * FS) + 50000
    rng = np.random.default_rng(1)
    x = [((rng.normal(size=N) + 1j * rng.normal(size=N)) * 0.01).astype(np.complex64)
         for _ in range(4)]
    band_at = np.full(N, -1)
    tags = []
    for k in range(NSLOTS):
        S = n0 + k * int(SLOT * FS)
        band_at[S:S + int(SLOT * FS)] = k % 3
        t = gr.tag_t()
        t.offset, t.key, t.value = S - int(GPRE * FS), pmt.intern("hop_off"), pmt.from_double(BANDS[(k + 1) % 3])
        tags.append(t)
        if k != BAD:
            t = gr.tag_t()
            t.offset, t.key, t.value = S + int((OFF - GPRE) * FS), pmt.intern("hop_on"), pmt.from_double(BANDS[k % 3])
            tags.append(t)
    tone = np.exp(2j * np.pi * 200e3 * np.arange(N) / FS)
    mA = band_at == 0
    x[0][mA] += tone[mA]
    for c in range(1, 4):
        x[c][mA] += (tone[mA] * np.exp(1j * PH[c - 1])).astype(np.complex64)

    srcs = [blocks.vector_source_c(x[0].tolist(), False, 1, tags)] + \
           [blocks.vector_source_c(x[c].tolist(), False) for c in range(1, 4)]
    rot = hop_tag_rotator(4, [(A, list(PH)), (B, [0, 0, 0]), (C, [0, 0, 0])])
    sel = hop_band_select(4, A, "hop_frame", FRAME)
    met = hop_phase_meter(4, A, FS, report_s=1e9)
    metB = hop_phase_meter(4, B, FS, report_s=1e9)
    ss = [blocks.vector_sink_c() for _ in range(4)]
    ms = [blocks.vector_sink_f() for _ in range(4)]
    mb = blocks.vector_sink_f()
    tb = gr.top_block()
    for c in range(4):
        tb.connect(srcs[c], (rot, c))
        tb.connect((rot, c), (sel, c))
        tb.connect((sel, c), ss[c])
        tb.connect((rot, c), (met, c))
        tb.connect((met, c), ms[c])
        tb.connect((rot, c), (metB, c))
    tb.connect((metB, 1), mb)
    for c in (0, 2, 3):
        tb.connect((metB, c), blocks.null_sink(gr.sizeof_float))
    tb.run()

    ok = True

    def check(cond, what):
        nonlocal ok
        print("%-4s %s" % ("PASS" if cond else "FAIL", what))
        ok = ok and cond

    y = [np.array(s.data()) for s in ss]
    good = [k for k in range(NSLOTS) if k % 3 == 0 and k != BAD]
    win = int(ON * FS)
    check(len(y[0]) == len(good) * win,
          "band select passed %d samples = %d marked band-A dwells x %d" % (len(y[0]), len(good), win))
    res = np.degrees(np.angle(np.sum(y[1:] * np.conj(y[0])[None], axis=1)))
    check(np.all(np.abs(res) < 0.05), "residual after correction %s deg (expect 0)" % np.round(res, 4).tolist())
    check(int(np.sum(np.abs(y[0]) < 0.5)) == 0, "no switching or no-tone sample in the selection")
    ft = sorted(t.offset for t in ss[0].tags() if pmt.symbol_to_string(t.key) == "hop_frame")
    want = [i * win + FRAME for i in range(len(good))]
    check(ft == want, "window-start tags at %d samples into each of %d windows" % (FRAME, len(want)))
    m = [np.array(s.data()) for s in ms]
    check(len(m[1]) == len(good), "meter: %d readings for %d band-A windows" % (len(m[1]), len(good)))
    check(np.all(np.abs(m[1:3]) < 0.05) if len(m[1]) else False, "meter residuals ~0")
    b = np.array(mb.data())
    check(len(b) > 0 and np.all(np.isnan(b)), "meter on a band with no tone: %d readings, all NaN" % len(b))
    print("SELFTEST %s" % ("PASSED" if ok else "FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
