#!/usr/bin/env python3
"""Phase-offset stability under frequency hopping, USRP-2945.

Hops the receiver through a list of frequencies, dwelling at each, and records
the inter-channel phase offsets (ch1-ch0, ch2-ch0, ch3-ch0) plus the tone SNR
on every channel.  Repeated cycles give the spread at each frequency, which
answers the question this test exists for: does a frequency give the SAME
offset every time we come back to it?

SNR gates the result.  A channel receiving nothing still produces a perfectly
steady phase, so a sample is only kept when every channel actually sees the
tone.  Skipping that check has produced false PASS results on this rig before.

The transmitter cannot corrupt this measurement: all four channels receive the
same tone, so any TX phase drift -- and the B210's ~1.6 ppm frequency error --
is common mode and cancels in the differences.

  source ~/gnuradio-3.8/setup_env.sh

  # the real run (transmitter must hop in step)
  python3 twinrx_hop_test.py --freqs 2.4e9,5.1e9,5.8e9 --dwell 2 --cycles 20 \
          --log hop.csv --plot hop.png

Optional, once the offsets are known to repeat:
  --cal-out FILE   measure a per-frequency correction table
  --cal-in  FILE   apply it; the printed offsets then become residuals
"""
import argparse
import math
import os
import socket
import sys
import threading
import time

import numpy as np
from gnuradio import gr, blocks


# --------------------------------------------------------------------------
# sample capture
# --------------------------------------------------------------------------
class Snapshot(gr.sync_block):
    """Keeps the most recent `depth` samples of each channel."""

    def __init__(self, nchan=4, depth=65536):
        gr.sync_block.__init__(self, name="snapshot",
                               in_sig=[np.complex64] * nchan, out_sig=None)
        self.nchan, self.depth = nchan, depth
        self.lock_ = threading.Lock()
        self.buf = [np.zeros(0, np.complex64) for _ in range(nchan)]

    def work(self, input_items, output_items):
        n = len(input_items[0])
        with self.lock_:
            for i in range(self.nchan):
                self.buf[i] = np.concatenate(
                    [self.buf[i], input_items[i]])[-self.depth:]
        return n

    def reset(self):
        with self.lock_:
            self.buf = [np.zeros(0, np.complex64) for _ in range(self.nchan)]

    def grab(self, n=None):
        """Newest n samples per channel, or None if not enough yet."""
        n = n or self.depth
        with self.lock_:
            if len(self.buf[0]) < n:
                return None
            return [b[-n:].copy() for b in self.buf]


# --------------------------------------------------------------------------
# measurement
# --------------------------------------------------------------------------
def analyse(chans, rate, offset, search=20e3):
    """(rel_phase_deg[4], snr_db[4], peak_khz) measured at the tone bin.

    The bin is located on ch0 and then reused for every channel, so the phases
    are directly comparable.  `search` covers the transmitter's frequency error
    -- a free-running B210 lands several kHz away from the nominal offset.
    """
    n = len(chans[0])
    w = np.hanning(n)
    k = int(round(offset / rate * n))
    span = max(1, int(round(search / rate * n)))

    spectra = [np.fft.fft(d * w) for d in chans]
    psd0 = np.abs(spectra[0]) ** 2

    # Look on both sides of DC. Low-side LO injection inverts the spectrum, so
    # a tone transmitted at +offset arrives at -offset; that happens whenever
    # the driver falls back to low-side LO1 to get a lock.
    best = None
    for centre in (k, n - k):
        lo = max(centre - span, 1)
        hi = min(centre + span + 1, n - 1)
        if hi <= lo:
            continue
        cand = lo + int(np.argmax(psd0[lo:hi]))
        if best is None or psd0[cand] > psd0[best]:
            best = cand
    peak = best

    phases, snrs = [], []
    for sp in spectra:
        psd = np.abs(sp) ** 2
        phases.append(math.degrees(np.angle(sp[peak])))
        sig = psd[peak - 3:peak + 4].sum()
        mask = np.ones(n, bool)
        mask[max(peak - 300, 0):peak + 300] = False
        noise = np.median(psd[mask]) * 7
        snrs.append(10 * math.log10(max(sig, 1e-30) / max(noise, 1e-30)))

    rel = [wrap180(p - phases[0]) for p in phases]
    khz = peak / n * rate / 1e3
    if khz > rate / 2e3:                 # report the negative half as negative
        khz -= rate / 1e3
    return rel, snrs, khz


def wrap180(d):
    return (d + 180.0) % 360.0 - 180.0


def circ_mean_deg(vals):
    return math.degrees(np.angle(np.mean(np.exp(1j * np.radians(vals)))))


def circ_spread_deg(vals):
    """Peak-to-peak width about the circular mean -- wrap safe."""
    if len(vals) == 0:
        return float("nan")
    d = [wrap180(v - circ_mean_deg(vals)) for v in vals]
    return max(d) - min(d)


# --------------------------------------------------------------------------
# sources
# --------------------------------------------------------------------------
class TB(gr.top_block):
    """ch0 is the reference and passes straight through; ch1..ch3 carry a
    rotation whose constant can be changed at runtime.

    doa.phase_correct_hier cannot be used for a hopping correction -- it reads
    its .cfg once in __init__ -- so the same maths is applied with
    multiply_const_cc, whose set_k() is a runtime callback.
    """

    def __init__(self, freq, rate, gain, depth, offset, lo_fallback=False):
        gr.top_block.__init__(self)
        import doa
        self.src = doa.twinrx_usrp_source(
            samp_rate=int(rate), center_freq=int(freq),
            gain=gain, sources=4, addresses="type=x300",
            lo_lock_fallback=lo_fallback)
        self.snap = Snapshot(4, depth)
        self.rot = [None] + [blocks.multiply_const_cc(1 + 0j) for _ in range(3)]
        self.connect((self.src, 0), (self.snap, 0))
        for ch in (1, 2, 3):
            self.connect((self.src, ch), self.rot[ch], (self.snap, ch))

    def set_correction(self, phases_rad):
        """phases_rad = measured (angle_chN - angle_ch0); undo it."""
        for ch in (1, 2, 3):
            k = 1 + 0j if phases_rad is None else np.exp(-1j * phases_rad[ch - 1])
            self.rot[ch].set_k(complex(k))


# --------------------------------------------------------------------------
# calibration table
# --------------------------------------------------------------------------
def load_cal(path):
    tbl = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [x for x in line.replace(",", " ").split() if x]
            tbl[float(parts[0])] = [float(x) for x in parts[1:4]]
    return tbl


def nearest_cal(tbl, f, tol=5e6):
    if not tbl:
        return None
    k = min(tbl, key=lambda c: abs(c - f))
    return tbl[k] if abs(k - f) <= tol else None


class TxControl:
    """Commands the transmitter to retune, so both sides hop together.

    The transmitter runs in its own process -- the HackRF needs system
    gr-osmosdr while the TwinRX needs GR 3.8 -- so it is driven over UDP
    rather than by both sides watching a clock.
    """

    def __init__(self, target, timeout=1.5):
        host, port = target.split(":")
        self.addr = (host, int(port))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(timeout)

    def _cmd(self, text):
        self.sock.sendto(text.encode(), self.addr)
        try:
            return self.sock.recv(256).decode().strip()
        except socket.timeout:
            return None

    def ping(self):
        return self._cmd("ping") is not None

    def retune(self, freq):
        r = self._cmd(f"freq {freq:.0f}")
        return r is not None and r.startswith("ok")


def search_window(freq, ppm=30.0, floor=25e3):
    """How far to hunt for the tone.

    The HackRF's stock crystal is around +/-20 ppm, so at 5.8 GHz the tone can
    sit ~116 kHz from nominal. Scale the window with the carrier and keep a
    floor for the low bands.
    """
    return max(floor, freq * ppm * 1e-6)


# --------------------------------------------------------------------------
def measure_settling(tb, rate, offset, search, probe=8192, timeout=1.0, tol=0.5):
    """Time from tune until the offsets stop moving.

    Uses short probes so the answer reflects the hardware, not the time it
    takes to fill the main buffer.  Returns (ms, settled) -- settled is False
    if it never went quiet inside `timeout`.
    """
    t0 = time.time()
    prev, stable_since = None, None
    while time.time() - t0 < timeout:
        s = tb.snap.grab(probe)
        if s is not None:
            rel, _, _ = analyse(s, rate, offset, search)
            if prev is not None and all(abs(wrap180(a - b)) < tol
                                        for a, b in zip(rel[1:], prev[1:])):
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since > 0.05:
                    return (stable_since - t0) * 1e3, True
            else:
                stable_since = None
            prev = rel
        time.sleep(0.01)
    return (time.time() - t0) * 1e3, False


def verdict(spread):
    if spread < 1.0:
        return "CONSTANT      (table reusable)"
    if spread < 3.0:
        return "normal        (expected for this hardware)"
    if spread < 10.0:
        return "usable        (recalibrate periodically)"
    return "INVESTIGATE   (too large -- suspect a fault)"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freqs", default="2.4e9,5.1e9,5.8e9")
    p.add_argument("--dwell", type=float, default=2.0)
    p.add_argument("--cycles", type=int, default=20)
    p.add_argument("--rate", type=float, default=1e6)
    p.add_argument("--gain", type=float, default=60)
    p.add_argument("--offset", type=float, default=200e3,
                   help="tone offset from centre; must match the transmitter")
    p.add_argument("--depth", type=int, default=65536)
    p.add_argument("--min-snr", dest="min_snr", type=float, default=20.0,
                   help="discard a sample if any channel is below this (dB)")
    p.add_argument("--log", default=None, help="write per-hop CSV here")
    p.add_argument("--plot", default=None, help="write a PNG of the offsets here")
    p.add_argument("--cal-out", dest="cal_out", default=None)
    p.add_argument("--cal-in", dest="cal_in", default=None)
    p.add_argument("--lo-fallback", dest="lo_fallback", action="store_true",
                   help="allow the low-side LO fallback where UHD picks a "
                        "high-side LO that will not lock (5.00-5.14 GHz on "
                        "this unit). Off by default: the band reports the "
                        "failure and stays dead rather than being rescued.")
    p.add_argument("--tx-control", dest="tx_control", default=None,
                   help="host:port of hackrf_tone_source.py; the receiver "
                        "then commands each hop so both sides stay in step")
    p.add_argument("--search-ppm", dest="search_ppm", type=float, default=30.0,
                   help="tone search window as ppm of the carrier "
                        "(HackRF ~20 ppm, B210 ~2 ppm)")
    a = p.parse_args()

    freqs = [float(f) for f in a.freqs.split(",")]
    cal = load_cal(a.cal_in) if a.cal_in else {}
    if a.cal_in:
        print(f"calibration loaded from {a.cal_in}: "
              f"{sorted(round(f/1e9, 3) for f in cal)} GHz")

    tx = None
    if a.tx_control:
        tx = TxControl(a.tx_control)
        if tx.ping():
            print(f"transmitter reachable at {a.tx_control} -- it will be "
                  f"commanded on every hop")
        else:
            print(f"WARNING: no reply from the transmitter at {a.tx_control}.")
            print("         Start hackrf_tone_source.py first, or drop "
                  "--tx-control and hop it yourself.")
            sys.exit(1)

    tb = TB(freqs[0], a.rate, a.gain, a.depth, a.offset, a.lo_fallback)
    tb.start()
    time.sleep(1.0)

    hist = {f: [] for f in freqs}
    rows, dropped = [], 0

    print(f"\nhopping: "
          f"{[round(f/1e9, 3) for f in freqs]} GHz  ·  dwell {a.dwell}s  ·  "
          f"{a.cycles} cycles  ·  tone +{a.offset/1e3:.0f} kHz  ·  "
          f"SNR gate {a.min_snr:.0f} dB")
    kind = "residual" if a.cal_in else "raw offset"
    print(f"\ncyc  freq_GHz  settle_ms   {'ch1-ch0':>9} {'ch2-ch0':>9} {'ch3-ch0':>9}"
          f"   <- {kind} (deg)    minSNR  peak_kHz   status")
    print("-" * 110)

    try:
        for cyc in range(a.cycles):
            for f in freqs:
                t_hop = time.time()
                if tx and not tx.retune(f):
                    print(f"{cyc:3d}  {f/1e9:8.3f}       --        "
                          f"transmitter did not acknowledge the retune")
                    dropped += 1
                    time.sleep(a.dwell)
                    continue
                tb.src.set_center_freq(int(f), 4)
                # the correction, when used, switches WITH the centre frequency
                tb.set_correction(nearest_cal(cal, f) if cal else None)
                tb.snap.reset()

                win = search_window(f, a.search_ppm)
                settle_ms, settled = measure_settling(tb, a.rate, a.offset, win)

                s, t_wait = None, time.time()
                while s is None and time.time() - t_wait < a.dwell:
                    s = tb.snap.grab()
                    if s is None:
                        time.sleep(0.01)
                if s is None:
                    print(f"{cyc:3d}  {f/1e9:8.3f}       --        "
                          f"no full buffer within the dwell")
                    dropped += 1
                    continue

                rel, snr, pk = analyse(s, a.rate, a.offset, win)
                worst = min(snr)
                ok = worst >= a.min_snr
                if ok:
                    hist[f].append(rel)
                else:
                    dropped += 1

                rows.append([time.time(), f, settle_ms, rel[1], rel[2], rel[3],
                             *snr, pk, int(ok)])
                note = "ok" if ok else "DROPPED - low SNR"
                if ok and not settled:
                    note = "ok (settling not resolved)"
                print(f"{cyc:3d}  {f/1e9:8.3f}   {settle_ms:8.0f}   "
                      f"{rel[1]:+9.2f} {rel[2]:+9.2f} {rel[3]:+9.2f}"
                      f"                   {worst:6.1f}  {pk:8.1f}   {note}")

                left = a.dwell - (time.time() - t_hop)
                if left > 0:
                    time.sleep(left)
    except KeyboardInterrupt:
        print("\ninterrupted -- summarising what was collected")
    finally:
        tb.stop()
        tb.wait()

    # ---------------- summary ----------------
    print("\n" + "=" * 78)
    print("DOES EACH FREQUENCY REPEAT?   (spread = peak-to-peak about the mean)")
    print("=" * 78)
    print(f"{'freq_GHz':>9}  {'pair':<9} {'n':>4} {'mean_deg':>10} {'spread_deg':>11}   verdict")
    print("-" * 78)
    for f in freqs:
        rws = hist[f]
        if len(rws) < 2:
            print(f"{f/1e9:9.3f}  {'--':<9} {len(rws):>4}   too few valid samples")
            continue
        arr = np.array(rws)
        for j, name in ((1, "ch1-ch0"), (2, "ch2-ch0"), (3, "ch3-ch0")):
            col = arr[:, j]
            print(f"{f/1e9:9.3f}  {name:<9} {len(col):>4} {circ_mean_deg(col):>10.2f} "
                  f"{circ_spread_deg(col):>11.2f}   {verdict(circ_spread_deg(col))}")
    if dropped:
        print(f"\n{dropped} sample(s) discarded -- a channel did not see the tone.")
        print("That is the gate working: a dead channel reports a perfectly steady phase.")


    # ---------------- outputs ----------------
    if a.log and rows:
        with open(a.log, "w") as fh:
            fh.write("unix_time,freq_hz,settle_ms,ch1_ch0_deg,ch2_ch0_deg,"
                     "ch3_ch0_deg,snr0_db,snr1_db,snr2_db,snr3_db,peak_khz,kept\n")
            for r in rows:
                fh.write(",".join(f"{v:.6f}" if isinstance(v, float) else str(v)
                                  for v in r) + "\n")
        print(f"\nper-hop log -> {a.log}   ({len(rows)} rows)")

    if a.cal_out:
        with open(a.cal_out, "w") as fh:
            fh.write("# freq_hz, ch1_rad, ch2_rad, ch3_rad\n")
            fh.write("# measured (angle_chN - angle_ch0)\n")
            fh.write("# valid for THIS power session only -- the A-to-B LO phase\n")
            fh.write("# re-locks to a new value on every power cycle\n")
            for f in freqs:
                if len(hist[f]) < 2:
                    continue
                arr = np.array(hist[f])
                m = [math.radians(circ_mean_deg(arr[:, j])) for j in (1, 2, 3)]
                fh.write(f"{f:.0f}, {m[0]:.9f}, {m[1]:.9f}, {m[2]:.9f}\n")
        print(f"calibration table -> {a.cal_out}")
        print(f"  verify with:  --cal-in {os.path.basename(a.cal_out)}  "
              f"(offsets should then read near 0)")

    if a.plot and rows:
        make_plot(rows, freqs, a.plot)
        print(f"plot -> {a.plot}")


def make_plot(rows, freqs, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    arr = np.array([r for r in rows if r[-1]], dtype=float)
    if not len(arr):
        return
    t0 = arr[0][0]
    fig, axes = plt.subplots(len(freqs), 1, figsize=(11, 2.6 * len(freqs)),
                             sharex=True, squeeze=False)
    for ax, f in zip(axes[:, 0], freqs):
        sel = arr[np.isclose(arr[:, 1], f)]
        for j, (col, name) in enumerate(((3, "ch1-ch0"), (4, "ch2-ch0"), (5, "ch3-ch0"))):
            if len(sel):
                v = sel[:, col]
                ax.plot(sel[:, 0] - t0, v - circ_mean_deg(v), ".-", ms=4,
                        lw=1.1, label=f"{name}  (mean {circ_mean_deg(v):+.1f}°)")
        ax.set_title(f"{f/1e9:.3f} GHz — deviation from that frequency's mean", fontsize=11)
        ax.set_ylabel("deg")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc="upper right")
    axes[-1, 0].set_xlabel("seconds since start")
    fig.tight_layout()
    fig.savefig(path, dpi=130)


if __name__ == "__main__":
    main()
