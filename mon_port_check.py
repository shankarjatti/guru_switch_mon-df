#!/usr/bin/env python3
"""Are the ch0/ch1 ports (TwinRX board A) weaker? Checked in MON mode.

All 4 channels on their OWN internal LO (nothing shared), all on the SAME
frequency with the SAME gain, the HackRF tone through the power divider into
all 4 ports. Per band and channel: tone power in dBFS (absolute: 0 dBFS = full
scale sine), noise floor, tone over noise, lock sensor. Differences between
channels are then the RF paths only (port, cable, divider output, TwinRX
front end) -- no LO sharing involved.

    source ~/gnuradio-3.8/setup_env.sh
    python3 mon_port_check.py --bands 900e6:50,2.4e9:46,5.2e9:60,5.8e9:69
"""
import argparse
import json
import os
import time

import numpy as np
import uhd

import mon_tools

ap = argparse.ArgumentParser()
ap.add_argument("--addr", default="addr=192.168.10.2")
ap.add_argument("--bands", default="900e6:50,2.4e9:46,5.2e9:60,5.8e9:69",
                help="freq_hz:rx_gain_db; the SAME gain on every channel")
ap.add_argument("--rate", type=float, default=2e6)
ap.add_argument("--secs", type=float, default=0.5)
ap.add_argument("--repeats", type=int, default=3)
ap.add_argument("--dc-guard", type=float, default=20e3)
a = ap.parse_args()
NCH = 4
BANDS = [(float(f), float(g)) for f, g in (x.split(":") for x in a.bands.split(","))]

u = uhd.usrp.MultiUSRP(a.addr)
u.set_rx_subdev_spec(uhd.usrp.SubdevSpec(mon_tools.SUBDEV), 0)
for ch, ant in enumerate(mon_tools.ANTENNAS):
    u.set_rx_antenna(ant, ch)
u.set_rx_rate(a.rate)
for ch in range(NCH):
    u.set_rx_lo_export_enabled(False, "all", ch)
for ch in range(NCH):
    u.set_rx_lo_source("internal", "all", ch)
sa = uhd.usrp.StreamArgs("fc32", "sc16")
sa.channels = list(range(NCH))
st = u.get_rx_stream(sa)
fs = u.get_rx_rate()
N = int(a.secs * fs)


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
        if n == 0:
            raise RuntimeError("receive timed out after %d of %d samples" % (got, N))
        k = min(n, N - got)
        buf[:, got:got + k] = tmp[:, :k]
        got += k
    return buf


rows = []
w = np.hanning(N).astype(np.float32)
F = np.fft.fftfreq(N, 1.0 / fs)
away = np.abs(F) >= a.dc_guard
cg = np.sum(w) ** 2                               # window gain for a sine's bin
for f, gain in BANDS:
    print("\n== %.4f GHz, every channel gain %.0f dB, own internal LO   (%s)"
          % (f / 1e9, gain, mon_tools.tx_freq(f)))
    treq = uhd.types.TuneRequest(f)
    treq.rf_freq, treq.rf_freq_policy = f, uhd.types.TuneRequestPolicy.manual
    treq.dsp_freq, treq.dsp_freq_policy = 0.0, uhd.types.TuneRequestPolicy.manual
    for _ in range(2):
        for ch in range(NCH):
            u.set_rx_gain(gain, ch)
            u.set_rx_freq(treq, ch)
    time.sleep(1.5)                               # LO lock + the HackRF's retune
    lock = [u.get_rx_sensor("lo_locked", ch).to_bool() for ch in range(NCH)]
    src = [u.get_rx_lo_source("all", ch) for ch in range(NCH)]
    per = {ch: [] for ch in range(NCH)}
    for r in range(a.repeats):
        x = capture()
        for ch in range(NCH):
            S = np.abs(np.fft.fft(x[ch] * w)) ** 2
            k = int(np.argmax(np.where(away, S, 0)))
            tone_dbfs = 10 * np.log10(S[k] / cg + 1e-30)          # |A|^2 of the tone, 0 dBFS = amplitude 1
            noise = np.median(S[away])
            per[ch].append((float(F[k]), float(tone_dbfs), float(10 * np.log10(S[k] / noise)),
                            float(np.abs(x[ch]).max())))
    ref = np.median([p[1] for p in per[0]])
    best = max(np.median([p[1] for p in per[ch]]) for ch in range(NCH))
    for ch in range(NCH):
        t = np.array(per[ch])
        row = {"band": f, "gain": gain, "ch": ch, "port": mon_tools.PORTS[ch], "lo_source": src[ch],
               "locked": lock[ch], "tone_hz": float(np.median(t[:, 0])),
               "tone_dbfs": float(np.median(t[:, 1])), "tone_dbfs_spread": float(np.ptp(t[:, 1])),
               "snr_db": float(np.median(t[:, 2])), "adc_peak": float(t[:, 3].max())}
        rows.append(row)
        print("  ch%d %s  LO %-8s %s | tone %+8.1f Hz  %6.1f dBFS (±%.1f over %d reads) | "
              "%5.1f dB over noise | %5.1f dB vs best | ADC peak %.3f"
              % (ch, row["port"], src[ch], "LOCKED" if lock[ch] else "NOT LOCKED", row["tone_hz"],
                 row["tone_dbfs"], row["tone_dbfs_spread"] / 2, a.repeats, row["snr_db"],
                 row["tone_dbfs"] - best, row["adc_peak"]))
print("\n%s" % mon_tools.tx_freq(2.4e9))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
                   "mon_port_check_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
os.makedirs(os.path.dirname(out), exist_ok=True)
json.dump({"args": vars(a), "fs": fs, "rows": rows}, open(out, "w"), indent=1)
print("saved", out)
