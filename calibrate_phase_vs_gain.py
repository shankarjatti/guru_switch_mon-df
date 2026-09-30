#!/usr/bin/env python3
"""
Measure the TwinRX inter-channel phase offset as a function of RX gain.

The TwinRX variable-gain stage has its own phase response (AM-PM), and the
four chains do not share it exactly, so a calibration taken at one gain is
not valid at another.  This sweeps the gain and records the real, measured
offset at each step so the correction can follow the slider.

The whole sweep runs inside ONE device session on purpose.  Re-opening the
USRP re-locks the LO dividers, which lands on a different phase each time and
would make the points incomparable.

Output columns: gain_dB  theta1_rad  theta2_rad  theta3_rad
where theta_k = angle(ch0) - angle(ch_k), the same convention as
doa.twinrx_phase_offset_est and doa.phase_correct_hier.
"""

import argparse
import sys
import threading
import time

import numpy
from gnuradio import blocks, filter, gr
from gnuradio.filter import firdes

import doa


class ring4(gr.sync_block):
    """Keeps the most recent `depth` samples of 4 complex streams."""

    def __init__(self, depth):
        gr.sync_block.__init__(
            self, name="ring4", in_sig=[numpy.complex64] * 4, out_sig=None)
        self.depth = depth
        self.buf = numpy.zeros((4, depth), dtype=numpy.complex64)
        self.wp = 0
        self.count = 0
        self._lk = threading.Lock()

    def work(self, input_items, output_items):
        n = len(input_items[0])
        with self._lk:
            end = self.wp + n
            for ch in range(4):
                x = input_items[ch][:n]
                if end <= self.depth:
                    self.buf[ch, self.wp:end] = x
                else:
                    first = self.depth - self.wp
                    self.buf[ch, self.wp:] = x[:first]
                    self.buf[ch, :end - self.depth] = x[first:]
            self.wp = end % self.depth
            self.count += n
        return n

    def snapshot(self):
        with self._lk:
            return self.buf.copy(), self.count

    def samples_seen(self):
        with self._lk:
            return self.count


class sweeper(gr.top_block):
    def __init__(self, args):
        gr.top_block.__init__(self, "phase vs gain")
        self.args = args

        taps = firdes.complex_band_pass(
            1.0, args.rate,
            args.tone - args.bw / 2.0, args.tone + args.bw / 2.0,
            args.bw / 4.0, firdes.WIN_HAMMING)

        self.src = doa.twinrx_usrp_source(
            samp_rate=int(args.rate),
            center_freq=int(args.freq),
            gain=args.gains[0],
            sources=4,
            addresses=args.addr,
        )
        self.ring = ring4(args.nsamp)

        for ch in range(4):
            dcb = filter.dc_blocker_cc(1024, True)
            bp = filter.fir_filter_ccc(1, taps)
            self.connect((self.src, ch), dcb, bp, (self.ring, ch))

    def measure(self):
        """Grab a fresh, fully-refreshed buffer and return per-channel stats."""
        start = self.ring.samples_seen()
        need = start + self.args.nsamp
        deadline = time.time() + 30.0
        while self.ring.samples_seen() < need:
            if time.time() > deadline:
                raise RuntimeError("timed out waiting for samples")
            time.sleep(0.05)

        buf, _ = self.ring.snapshot()
        ref = buf[0]
        p_ref = float(numpy.mean(numpy.abs(ref) ** 2))

        thetas, amps, cohs = [], [float(numpy.sqrt(p_ref))], []
        for k in range(1, 4):
            x = buf[k]
            cross = numpy.mean(ref * numpy.conj(x))
            p_x = float(numpy.mean(numpy.abs(x) ** 2))
            thetas.append(float(numpy.angle(cross)))
            amps.append(float(numpy.sqrt(p_x)))
            denom = numpy.sqrt(p_ref * p_x)
            cohs.append(float(numpy.abs(cross) / denom) if denom > 0 else 0.0)
        return thetas, amps, cohs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--addr", default="type=x300")
    p.add_argument("--freq", type=float, default=5.1e9)
    p.add_argument("--rate", type=float, default=1e6)
    p.add_argument("--tone", type=float, default=200e3)
    p.add_argument("--bw", type=float, default=20e3)
    p.add_argument("--nsamp", type=int, default=262144)
    p.add_argument("--settle", type=float, default=1.5,
                   help="seconds to wait after a gain change")
    p.add_argument("--gains", type=float, nargs="+",
                   default=[10, 20, 30, 40, 50, 60, 70, 80, 90])
    p.add_argument("--out", default="twinrx_phase_vs_gain.cfg")
    args = p.parse_args()

    tb = sweeper(args)
    tb.start()
    time.sleep(3.0)  # let the stream and filters settle

    rows = []
    try:
        for g in args.gains:
            tb.src.set_gain(g)
            time.sleep(args.settle)
            thetas, amps, cohs = tb.measure()
            rows.append((g, thetas, amps, cohs))
            print("gain %5.1f dB | theta(rad) %8.4f %8.4f %8.4f "
                  "| deg %8.2f %8.2f %8.2f | rms %.4f %.4f %.4f %.4f "
                  "| coh %.3f %.3f %.3f"
                  % (g, thetas[0], thetas[1], thetas[2],
                     numpy.degrees(thetas[0]), numpy.degrees(thetas[1]),
                     numpy.degrees(thetas[2]),
                     amps[0], amps[1], amps[2], amps[3],
                     cohs[0], cohs[1], cohs[2]))
            sys.stdout.flush()
    finally:
        tb.stop()
        tb.wait()

    with open(args.out, "w") as f:
        f.write("# TwinRX phase offset vs RX gain -- MEASURED, not modelled\n")
        f.write("# freq %.6g Hz, rate %.6g Sps, tone %+.6g Hz, bw %.6g Hz\n"
                % (args.freq, args.rate, args.tone, args.bw))
        f.write("# measured %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        f.write("# theta_k = angle(ch0) - angle(ch_k), radians\n")
        f.write("# gain_dB theta1 theta2 theta3\n")
        for g, th, _a, _c in rows:
            f.write("%.3f %.9f %.9f %.9f\n" % (g, th[0], th[1], th[2]))
    print("\nwrote %s (%d points)" % (args.out, len(rows)))


if __name__ == "__main__":
    main()
