#!/usr/bin/env python3
"""How clean is the lab tone at the receiver, for several HackRF drive levels?

For each TX VGA setting: park the HackRF on the band, set its VGA, wait for its
~1 s transmit buffer to empty, record all four channels with guru's receive
settings (LO routing, gain + per-channel trim, DDC 0 Hz) and report per channel:
  peak |x|     -- how close to the ADC's full scale (1.0); must stay well below
  SNR          -- tone power vs everything else in the display band
                  (tone_offset +/- 150 kHz, 0 Hz and the tone's own bins excluded)
  worst line   -- the strongest single spurious line, dB below the tone
The VGA is put back to the band's normal value at the end.

    source ~/gnuradio-3.8/setup_env.sh
    python3 tone_level_check.py --band 2.4e9 --gain 46 --vgas 14,18,22,26 --offset 10e3
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
ap.add_argument("--trim", default="0.0,-13.3,1.5,-1.7", help="guru's per-channel gain trim, dB")
ap.add_argument("--vgas", default="14,18,22,26")
ap.add_argument("--restore-vga", type=int, default=14)
ap.add_argument("--offset", type=float, default=10e3, help="where the tone should arrive, Hz")
ap.add_argument("--bw", type=float, default=300e3, help="display bandwidth around the tone, Hz")
ap.add_argument("--secs", type=float, default=0.2)
ap.add_argument("--tx-control", default="127.0.0.1:5123")
a = ap.parse_args()
NCH = 4
trim = [float(x) for x in a.trim.split(",")]


def tx(cmd):
    host, port = a.tx_control.split(":")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3.0)
    s.sendto(cmd.encode(), (host, int(port)))
    try:
        return s.recv(256).decode(errors="replace").strip()
    finally:
        s.close()


u = uhd.usrp.MultiUSRP(a.addr)
u.set_rx_subdev_spec(uhd.usrp.SubdevSpec("A:0 A:1 B:0 B:1"), 0)
for ch, ant in enumerate(["RX1", "RX2", "RX1", "RX2"]):
    u.set_rx_antenna(ant, ch)
u.set_rx_rate(1e6)
for ch in range(NCH):
    try:
        u.set_rx_lo_export_enabled(False, "all", ch)
    except Exception:
        pass
for ch, src in enumerate(["external", "external", "internal", "companion"]):
    u.set_rx_lo_source(src, "all", ch)
u.set_rx_lo_export_enabled(True, "all", 2)
for ch in range(NCH):
    u.set_rx_dc_offset(True, ch)                   # as the engine does
sa = uhd.usrp.StreamArgs("fc32", "sc16")
sa.channels = list(range(NCH))
st = u.get_rx_stream(sa)
fs = u.get_rx_rate()
N = int(a.secs * fs)
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
print("HackRF:", tx("freq %d" % int(a.band)))


def capture():
    buf = np.zeros((NCH, N), dtype=np.complex64)
    md = uhd.types.RXMetadata()
    cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_done)
    cmd.num_samps = N
    cmd.stream_now = False
    cmd.time_spec = u.get_time_now() + uhd.types.TimeSpec(0.1)
    st.issue_stream_cmd(cmd)
    got = 0
    tmp = np.zeros((NCH, 10000), dtype=np.complex64)
    while got < N:
        n = st.recv(tmp, md, 1.0)
        if md.error_code != uhd.types.RXMetadataErrorCode.none:
            raise RuntimeError("receive error: %s" % md.strerror())
        k = min(n, N - got)
        buf[:, got:got + k] = tmp[:, :k]
        got += k
    return buf


rows = []
F = np.fft.fftfreq(N, 1.0 / fs)
res = fs / N
w = np.hanning(N).astype(np.float32)
for v in [int(x) for x in a.vgas.split(",")]:
    print("\nTX VGA %d dB: %s" % (v, tx("vga %d" % v)))
    time.sleep(2.0)                                # the HackRF's transmit buffer
    x = capture()
    for ch in range(NCH):
        y = x[ch] - x[ch].mean()                   # as the display does (0 Hz removed)
        S = np.abs(np.fft.fft(y * w)) ** 2
        band = np.abs(F - a.offset) <= a.bw / 2
        away_dc = np.abs(F) > 3 * res
        k = int(np.argmax(np.where(band & away_dc, S, 0)))
        tone = np.abs(F - F[k]) <= 8 * res         # the tone's own bins (Hann main lobe + margin)
        p_tone = S[tone].sum()
        p_rest = S[band & away_dc & ~tone].sum()
        # strongest single line outside the tone: peak bin vs the tone's peak bin
        rest = np.where(band & away_dc & ~(np.abs(F - F[k]) <= 50 * res), S, 0)
        j = int(np.argmax(rest))
        row = {"vga": v, "ch": ch, "peak": float(np.abs(x[ch]).max()),
               "amp": float(np.sqrt(np.mean(np.abs(y) ** 2))),
               "tone_hz": float(F[k]), "snr_db": float(10 * np.log10(p_tone / p_rest)),
               "worst_line_hz": float(F[j]), "worst_line_dbc": float(10 * np.log10(S[j] / S[k]))}
        rows.append(row)
        print("  ch%d  peak |x| %.3f of full scale | tone %.3f rms at %+.0f Hz | SNR in %g kHz %5.1f dB"
              " | worst line %+.0f Hz %6.1f dBc" % (ch, row["peak"], row["amp"], row["tone_hz"],
                                                   a.bw / 1e3, row["snr_db"], row["worst_line_hz"],
                                                   row["worst_line_dbc"]))
print("\nTX VGA back to %d: %s" % (a.restore_vga, tx("vga %d" % a.restore_vga)))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
                   "tone_level_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
json.dump({"args": vars(a), "rows": rows}, open(out, "w"), indent=1)
print("saved", out)
