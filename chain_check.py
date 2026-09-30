#!/usr/bin/env python3
"""Read what the flowgraph's own phase estimator produces, headless.

The correction block's arithmetic is provably right (0.0000 deg on synthetic
input) and the table matches a fresh measurement, yet the readouts are
reported as not zeroed. The difference between what was verified and what is
displayed is the chain in between: dc block -> band pass -> correction ->
twinrx_phase_offset_est -> rad2deg -> moving average.

So this builds exactly that chain, on the real radio, and prints the numbers
the displays would show. Anything wrong here is in the chain; anything right
here is in the GUI.

    source ~/gnuradio-3.8/setup_env.sh
    ./chain_check.py
"""
import math, sys, time
import numpy as np
from gnuradio import gr, blocks, filter
from gnuradio.filter import firdes
import doa

SAMP_RATE, TONE, DISP_BW, PH_AVG = 1000000, 200e3, 300e3, 16384
GAIN_TRIM = (0.0, -13.3, 1.5, -1.7)
BANDS = [(2400000000, 46.0, 6.0), (5200000000, 60.0, 6.0), (5800000000, 69.0, 6.0)]
TABLE = [(2400000000, (173.6047, -90.5480, -173.8282)),
         (5200000000, (103.5930,  53.4658,   16.2792)),
         (5800000000, ( 83.9507, 143.4729,  159.8349))]


class Tap(gr.sync_block):
    """Latest value of each of the four phase outputs."""
    def __init__(self):
        gr.sync_block.__init__(self, name="tap",
                               in_sig=[np.float32]*4, out_sig=None)
        self.last = [0.0]*4
    def work(self, input_items, output_items):
        for i in range(4):
            if len(input_items[i]):
                self.last[i] = float(input_items[i][-1])
        return len(input_items[0])


class TB(gr.top_block):
    def __init__(self, correct=True):
        gr.top_block.__init__(self)
        self.src = doa.twinrx_hopping_source(
            samp_rate=SAMP_RATE, sources=4, addresses="type=x300",
            lo_export_direction="B", cpu_format="fc32",
            bands=BANDS, settle=1.0, hop_enable=True,
            tx_control="127.0.0.1:5123", blank_during_settle=False,
            lo_lock_fallback=False, gain_trim=GAIN_TRIM, start_delay=2.0)
        taps = firdes.complex_band_pass(1.0, SAMP_RATE, TONE - DISP_BW/2,
                                        TONE + DISP_BW/2, DISP_BW/4,
                                        firdes.WIN_HAMMING)
        self.corr = None
        if correct:
            self.corr = doa.phase_correct_hopping(
                num_channels=4, bands=[(f, d, 10.0) for f, d in TABLE],
                follow_source=True)
        self.est = doa.twinrx_phase_offset_est(5, 8192)
        self.tap = Tap()
        heads = []
        for ch in range(4):
            dc = filter.dc_blocker_cc(1024, True)
            bp = filter.fir_filter_ccc(1, taps)
            self.connect((self.src, ch), dc, bp)
            heads.append(bp)
        if correct:
            for ch in range(4):
                self.connect(heads[ch], (self.corr, ch))
            heads = [(self.corr, ch) for ch in range(4)]
        # natural channel order, matching the fixed flowgraph
        self.connect(heads[0], (self.est, 0))
        self.connect(heads[0], (self.est, 1))
        self.connect(heads[1], (self.est, 2))
        self.connect(heads[2], (self.est, 3))
        self.connect(heads[3], (self.est, 4))
        for p in range(4):
            d = blocks.multiply_const_ff(-180.0/math.pi)
            a = blocks.moving_average_ff(PH_AVG, 1.0/PH_AVG, 65536, 1)
            self.connect((self.est, p), d, a, (self.tap, p))


def main():
    correct = "--raw" not in sys.argv
    print("chain: dcblock -> bandpass -> %s -> ph_est -> deg -> avg"
          % ("CORRECTION" if correct else "no correction"))
    print("out_p = ch_{p+1} - ch0 in degrees, natural order. Target: |x| < 0.5\n")
    tb = TB(correct)
    tb.start()
    try:
        last, seen = None, 0
        while seen < 9:
            time.sleep(0.3)
            if not tb.src.is_settled():
                continue
            i = tb.src.get_band_index()
            if i < 0 or i == last:
                continue
            if tb.corr is not None:
                tb.corr.set_band_freq(BANDS[i][0])
            time.sleep(3.0)                      # sit in the dwell
            if tb.src.get_band_index() != i or not tb.src.is_settled():
                continue
            v = list(tb.tap.last)
            last, seen = i, seen + 1
            print("  %8.4f GHz   ch0-ch0 %+8.2f   ch1-ch0 %+8.2f   "
                  "ch2-ch0 %+8.2f   ch3-ch0 %+8.2f"
                  % (BANDS[i][0]/1e9, v[0], v[1], v[2], v[3]))
            worst = max(abs(x) for x in v)
            print("              worst |offset| %.2f deg   %s"
                  % (worst, "PASS" if worst < 0.5 else "*** OVER 0.5 ***"))
    finally:
        try:
            tb.src.stop_hopping()
        except Exception as e:
            # Reported, not swallowed: a hop thread left running through
            # teardown is what wedges the X310's control plane.
            print('could not stop the hop thread: %s' % e)
        tb.stop(); tb.wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
