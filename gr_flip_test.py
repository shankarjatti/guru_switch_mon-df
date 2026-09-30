#!/usr/bin/env python3
"""Where do the 5.8 GHz ch0 180-degree flips come from?

Seen through guru's chain (twinrx_hopping_source, schedule=radio): ~12% of
5.8 GHz dwell windows have ch0 exactly 180 deg off; never seen through pyuhd.
This runs the same radio-clock schedule with the tone parked on --band and
measures chN - ch0 on every dwell window of that band, in one of two ways:

  --source raw     plain gr-uhd usrp_source, set up exactly like the pyuhd
                   tests (DDC pinned to 0 Hz on all channels at start)

Result 2026-09-28: 6-8 % of 5.8 GHz windows flipped through gr-uhd, 0 % through
pyuhd (sched_hop_test.py, fast_chain_check.py) -- why twinrx_radio_source
drives the radio through pyuhd.

    python3 gr_flip_test.py --source raw --band 5.8e9 --secs 20
"""
import argparse
import threading
import time

import numpy as np
import pmt
from gnuradio import gr, uhd, blocks

from dwell_test import tx_freq

FS = 1e6
NCH = 4
BANDS = [(2.4e9, 46.0), (5.2e9, 60.0), (5.8e9, 69.0)]
TRIM = (0.0, -13.3, 1.5, -1.7)
STEP, SECOND = 0.0004, 0.003
OFF, ON, GPRE = 0.010, 0.010, 0.00025


class WinRec(gr.sync_block):
    """Accumulates chN*conj(ch0) over [start, stop) sample windows given in advance."""

    def __init__(self):
        gr.sync_block.__init__(self, "winrec", in_sig=[np.complex64] * NCH, out_sig=None)
        self.t0 = self.n0 = None
        self.wins = []          # [n_start, n_stop, acc(3), p(4)]
        self.lock = threading.Lock()
        self.done = []

    def add_window(self, t_start, t_stop, tag):
        with self.lock:
            self.wins.append([t_start, t_stop, np.zeros(3, complex), np.zeros(4), tag, 0])

    def work(self, input_items, output_items):
        n = len(input_items[0])
        base = self.nitems_read(0)
        if self.t0 is None:
            for t in self.get_tags_in_window(0, 0, n, pmt.intern("rx_time")):
                self.t0 = pmt.to_uint64(pmt.tuple_ref(t.value, 0)) + pmt.to_double(pmt.tuple_ref(t.value, 1))
                self.n0 = t.offset
                break
            if self.t0 is None:
                return n
        x = input_items
        with self.lock:
            keep = []
            for w in self.wins:
                a = int(round(self.n0 + (w[0] - self.t0) * FS)) - base
                b = int(round(self.n0 + (w[1] - self.t0) * FS)) - base
                lo, hi = max(a, 0), min(b, n)
                if hi > lo:
                    for c in range(1, NCH):
                        w[2][c - 1] += np.sum(x[c][lo:hi] * np.conj(x[0][lo:hi]))
                    for c in range(NCH):
                        w[3][c] += np.sum(np.abs(x[c][lo:hi]) ** 2)
                    w[5] += hi - lo
                if b <= n:
                    self.done.append(w)
                else:
                    keep.append(w)
            self.wins = keep
        return n


def band_change(src, f, g, T):
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


def make_raw():
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
        except Exception:
            pass
    for c, s in enumerate(["external", "external", "internal", "companion"]):
        src.set_lo_source(s, uhd.ALL_LOS, c)
    src.set_lo_export_enabled(True, uhd.ALL_LOS, 2)
    f0, g0 = BANDS[2]
    for c in range(NCH):
        src.set_gain(g0 + TRIM[c], c)
    req = uhd.tune_request(f0)
    req.rf_freq = f0
    req.rf_freq_policy = uhd.tune_request.POLICY_MANUAL
    req.dsp_freq = 0.0
    req.dsp_freq_policy = uhd.tune_request.POLICY_MANUAL
    for c in range(NCH):
        src.set_center_freq(req, c)
    return src, src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["raw"], default="raw")
    ap.add_argument("--band", type=float, default=5.8e9)
    ap.add_argument("--secs", type=float, default=20.0)
    a = ap.parse_args()
    print(tx_freq(a.band).strip(), "-> tone parked on %.1f GHz" % (a.band / 1e9))
    blk, src = make_raw()
    rec = WinRec()
    tb = gr.top_block()
    for c in range(NCH):
        tb.connect((blk, c), (rec, c))
    tb.start()
    time.sleep(1.0)
    gains = [[g + TRIM[c] for c in range(NCH)] for _, g in BANDS]
    slot = OFF + ON
    S = src.get_time_now().get_real_secs() + 0.2
    k = 0
    late = 0
    sends = {}
    t_end = time.time() + a.secs
    off = [0.0]

    def now():
        x = time.perf_counter()
        d = src.get_time_now().get_real_secs()
        off[0] = d - (x + time.perf_counter()) / 2
        return d

    def sleep_until(d):
        while True:
            r = d - (time.perf_counter() + off[0])
            if r <= 0:
                return
            time.sleep(r - 0.0005 if r > 0.001 else 0.0001)

    now()
    i = k % 3
    band_change(src, BANDS[i][0], gains[i], S)
    if BANDS[i][0] == a.band:
        rec.add_window(S + OFF - GPRE, S + slot - GPRE, k)
    while time.time() < t_end:
        sleep_until(S + 0.007)
        src.get_sensor("lo_locked", 2)
        k += 1
        S += slot
        i = k % 3
        now()
        h0 = time.perf_counter()
        band_change(src, BANDS[i][0], gains[i], S)
        sends[k] = (time.perf_counter() - h0) * 1e3
        if time.perf_counter() + off[0] >= S:
            late += 1
        if BANDS[i][0] == a.band:
            rec.add_window(S + OFF - GPRE, S + slot - GPRE, k)
    time.sleep(0.3)
    tb.stop()
    tb.wait()
    ph = np.array([np.degrees(np.angle(w[2])) for w in rec.done if w[5] > 0])
    m = np.degrees(np.angle(np.sum(np.exp(1j * np.radians(ph)), axis=0)))
    d = (ph - m + 180) % 360 - 180
    flip = np.abs(d).max(axis=1) > 90
    print("source=%s band %.1f GHz: %d windows, late %d, flipped %d (%.1f%%)"
          % (a.source, a.band / 1e9, len(ph), late, flip.sum(), 100 * flip.mean()))
    ks = [w[4] for w in rec.done if w[5] > 0]
    dev0 = d[:, 0]
    print("  deviation of ch1-ch0 per window, histogram (deg):")
    hist, edges = np.histogram(dev0, bins=np.arange(-180, 181, 30))
    print("   " + "  ".join("%+d..%+d:%d" % (edges[j], edges[j + 1], hist[j]) for j in range(len(hist)) if hist[j]))
    same = np.abs(d - d[:, :1]).max(axis=1) < 2.0
    print("  windows whose 3 pair deviations are equal (= ch0 alone moved): %d of %d moved"
          % (int(np.sum(same & (np.abs(dev0) > 2))), int(np.sum(np.abs(dev0) > 2))))
    sm = np.array([sends.get(k, np.nan) for k in ks])
    mv = np.abs(dev0) > 2
    if mv.any():
        print("  send ms, moved windows: median %.2f  | steady windows: median %.2f"
              % (np.nanmedian(sm[mv]), np.nanmedian(sm[~mv])))
        print("  moved window slot numbers (first 30): %s" % [ks[j] for j in np.where(mv)[0][:30]])
    print("  median phase ch1/ch2/ch3: %s" % np.round(np.median(ph, axis=0), 2).tolist())
    print("  non-flipped spread (max dev): %s" % np.round(np.abs(d[~flip]).max(axis=0), 3).tolist())


if __name__ == "__main__":
    main()
