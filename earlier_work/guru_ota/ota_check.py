#!/usr/bin/env python3
"""Over the air: is the tone strong and are the 4 channels' phases steady?

RX only (the HackRF is only asked to change its VGA, then put back). For each
HackRF VGA: tune all 4 channels to the band exactly like guru (LO routing,
gain + trim, DDC 0 Hz), record --secs continuously and report per channel:
  peak |x| (ADC full scale 1.0), tone level, SNR of the tone bin in 5 ms
and, per 5 ms block, chN - ch0 phase at the tone: its spread (std) and how
much of it is fast (block-to-block jitter = noise) or slow (wander =
reflections, e.g. a fan or people moving).

    source ~/gnuradio-3.8/setup_env.sh
    python3 ota_check.py --band 2.4e9 --gain 46 --vgas 14,30,40
"""
import argparse
import json
import os
import socket
import time

import numpy as np
import uhd

ap = argparse.ArgumentParser()
ap.add_argument("--addr", default="addr=192.168.10.2")
ap.add_argument("--band", type=float, default=2.4e9)
ap.add_argument("--gain", type=float, default=46.0)
ap.add_argument("--trim", default="0.0,-13.3,1.5,-1.7")
ap.add_argument("--vgas", default="14", help="HackRF VGA values to try (dB)")
ap.add_argument("--restore-vga", type=int, default=None)
ap.add_argument("--rate", type=float, default=2e6)
ap.add_argument("--offset", type=float, default=200e3)
ap.add_argument("--secs", type=float, default=2.0)
ap.add_argument("--tx-control", default="127.0.0.1:5123")
a = ap.parse_args()
NCH = 4
trim = [float(x) for x in a.trim.split(",")]


def tx(cmd):
    h, p = a.tx_control.split(":")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3.0)
    s.sendto(cmd.encode(), (h, int(p)))
    try:
        return s.recv(256).decode(errors="replace").strip()
    finally:
        s.close()


u = uhd.usrp.MultiUSRP(a.addr)
u.set_rx_subdev_spec(uhd.usrp.SubdevSpec("A:0 A:1 B:0 B:1"), 0)
for ch, ant in enumerate(["RX1", "RX2", "RX1", "RX2"]):
    u.set_rx_antenna(ant, ch)
u.set_rx_rate(a.rate)
for ch in range(NCH):
    try:
        u.set_rx_lo_export_enabled(False, "all", ch)
    except Exception:
        pass
for ch, src in enumerate(["external", "external", "internal", "companion"]):
    u.set_rx_lo_source(src, "all", ch)
u.set_rx_lo_export_enabled(True, "all", 2)
for ch in range(NCH):
    u.set_rx_dc_offset(True, ch)
treq = uhd.types.TuneRequest(a.band)
treq.rf_freq = a.band
treq.rf_freq_policy = uhd.types.TuneRequestPolicy.manual
treq.dsp_freq = 0.0
treq.dsp_freq_policy = uhd.types.TuneRequestPolicy.manual
for _ in range(2):
    for ch in range(NCH):
        r = u.get_rx_gain_range(ch)
        u.set_rx_gain(max(r.start(), min(r.stop(), a.gain + trim[ch])), ch)
        u.set_rx_freq(treq, ch)
sa = uhd.usrp.StreamArgs("fc32", "sc16")
sa.channels = list(range(NCH))
st = u.get_rx_stream(sa)
fs = u.get_rx_rate()
N = int(a.secs * fs)
B = int(0.005 * fs)                         # one 5 ms block = one dwell


def capture():
    buf = np.zeros((NCH, N), dtype=np.complex64)
    md = uhd.types.RXMetadata()
    cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_done)
    cmd.num_samps = N
    cmd.stream_now = False
    cmd.time_spec = u.get_time_now() + uhd.types.TimeSpec(0.1)
    st.issue_stream_cmd(cmd)
    got = 0
    tmp = np.zeros((NCH, 20000), dtype=np.complex64)
    while got < N:
        n = st.recv(tmp, md, 1.0)
        if md.error_code != uhd.types.RXMetadataErrorCode.none:
            raise RuntimeError(md.strerror())
        k = min(n, N - got)
        buf[:, got:got + k] = tmp[:, :k]
        got += k
    return buf


print("HackRF:", tx("freq %d" % int(a.band)), "| receiver gain %.0f dB + trim" % a.gain)
rows = []
F = np.fft.fftfreq(B, 1.0 / fs)
w = np.hanning(B).astype(np.float32)
win = (F > a.offset - 60e3) & (F < a.offset + 60e3)
for v in [int(x) for x in a.vgas.split(",")]:
    print("\n== HackRF VGA %d dB: %s" % (v, tx("vga %d" % v)))
    time.sleep(2.0)
    x = capture()
    nb = N // B
    X = np.fft.fft(x[:, :nb * B].reshape(NCH, nb, B) * w, axis=2)          # [ch, block, bin]
    P = np.abs(X) ** 2
    k = int(np.argmax(np.where(win, P.sum(axis=(0, 1)), 0)))              # the tone's bin
    snr = 10 * np.log10(P[:, :, k] / (np.median(P, axis=2) + 1e-30))       # [ch, block]
    ph = np.degrees(np.angle(X[1:, :, k] * np.conj(X[0, :, k])[None]))     # [3, block]
    un = np.unwrap(np.radians(ph), axis=1)
    fast = np.degrees(np.std(np.diff(un, axis=1), axis=1) / np.sqrt(2))   # block-to-block jitter
    tot = np.degrees(np.std(un - un.mean(axis=1, keepdims=True), axis=1))
    row = {"vga": v, "tone_hz": float(F[k]), "peak": [float(np.abs(x[c]).max()) for c in range(NCH)],
           "snr_median": [float(np.median(snr[c])) for c in range(NCH)],
           "snr_min": [float(snr[c].min()) for c in range(NCH)],
           "phase_std_total": tot.tolist(), "phase_jitter_fast": fast.tolist()}
    rows.append(row)
    print("  tone at %+.0f Hz" % F[k])
    for c in range(NCH):
        print("  ch%d  ADC peak %.3f | tone SNR per 5 ms: median %5.1f dB, worst %5.1f dB"
              % (c, row["peak"][c], row["snr_median"][c], row["snr_min"][c]))
    for c in range(3):
        print("  ch%d-ch0 phase over %.1f s: spread %.2f deg  (fast jitter %.2f deg = noise; the rest = slow wander)"
              % (c + 1, a.secs, tot[c], fast[c]))
    # what the phase wobble is made of: its spectrum (one value per 5 ms block)
    fr = np.fft.rfftfreq(nb, 0.005)
    for c in range(3):
        sp = np.abs(np.fft.rfft(un[c] - un[c].mean() - np.polyval(np.polyfit(np.arange(nb), un[c], 1), np.arange(nb)) + np.polyval(np.polyfit(np.arange(nb), un[c], 1), np.arange(nb)).mean())) ** 2
        sp[0] = 0
        top = np.argsort(sp)[::-1][:3]
        share = sp[top].sum() / sp.sum() * 100
        print("  ch%d-ch0 phase wobble strongest at %s Hz (these 3 carry %.0f %% of it)"
              % (c + 1, ", ".join("%.1f" % fr[i] for i in sorted(top, key=lambda i: fr[i])), share))
    amp = [float(np.std(np.abs(X[c, :, k]) / np.abs(X[c, :, k]).mean())) * 100 for c in range(NCH)]
    print("  tone amplitude variation per channel: " + "  ".join("ch%d %.1f %%" % (c, amp[c]) for c in range(NCH)))
if a.restore_vga is not None:
    print("\nHackRF VGA back to %d: %s" % (a.restore_vga, tx("vga %d" % a.restore_vga)))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
                   "ota_check_%dMHz_%s.json" % (a.band / 1e6, time.strftime("%Y%m%d_%H%M%S")))
json.dump({"args": vars(a), "rows": rows}, open(out, "w"), indent=1)
print("saved", out)
