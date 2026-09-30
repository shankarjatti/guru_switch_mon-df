#!/usr/bin/env python3
"""Two facts the MON<->DF engine design depends on (RX only, HackRF tone on --band).

A. Timed LO routing: in a running DF setup, schedule at radio time T the MON
   routing (export off, all internal) + the engine tune to the MON bands, and
   at T2 the DF routing + tune back. One burst covers T-3 ms .. T2+15 ms.
   ch0 goes to --mon-ch0 in MON, so its tone must vanish AT T (not before),
   and come back after T2. Then: is the phase after the return the same as
   before (as in step 1, where the routing was done untimed while idle)?
B. Back-to-back bursts: --nb bursts of --blen samples, each timed exactly at
   the end of the previous one. Does every burst arrive, starting on its
   commanded sample, with no gap?

    source ~/gnuradio-3.8/setup_env.sh
    python3 route_burst_test.py
"""
import argparse
import time

import numpy as np
import uhd

import mon_tools

ap = argparse.ArgumentParser()
ap.add_argument("--addr", default="addr=192.168.10.2")
ap.add_argument("--band", type=float, default=2.4e9)
ap.add_argument("--gain", type=float, default=46)
ap.add_argument("--mon", default="900e6,2.4e9,5.2e9,5.8e9")
ap.add_argument("--rate", type=float, default=2e6)
ap.add_argument("--trips", type=int, default=10)
ap.add_argument("--nb", type=int, default=200)
ap.add_argument("--blen", type=int, default=10000)
a = ap.parse_args()
NCH = 4
MONF = [float(x) for x in a.mon.split(",")]
DF_SRC = ["external", "external", "internal", "companion"]
STEP, SECOND_PASS = 0.0004, 0.003

u = uhd.usrp.MultiUSRP(a.addr)
u.set_rx_subdev_spec(uhd.usrp.SubdevSpec(mon_tools.SUBDEV), 0)
for ch, ant in enumerate(mon_tools.ANTENNAS):
    u.set_rx_antenna(ant, ch)
u.set_rx_rate(a.rate)
fs = u.get_rx_rate()
sa = uhd.usrp.StreamArgs("fc32", "sc16")
sa.channels = list(range(NCH))
st = u.get_rx_stream(sa)


def treq(f, dsp_none=True):
    t = uhd.types.TuneRequest(f)
    t.rf_freq, t.rf_freq_policy = f, uhd.types.TuneRequestPolicy.manual
    if dsp_none:
        t.dsp_freq_policy = uhd.types.TuneRequestPolicy.none
    else:
        t.dsp_freq, t.dsp_freq_policy = 0.0, uhd.types.TuneRequestPolicy.manual
    return t


def ts(t):
    return uhd.types.TimeSpec(t)


def route_timed(T, sources, export_ch):
    u.set_command_time(ts(T))
    for ch in range(NCH):
        u.set_rx_lo_export_enabled(False, "all", ch)
    for ch in range(NCH):
        u.set_rx_lo_source(sources[ch], "all", ch)
    if export_ch is not None:
        u.set_rx_lo_export_enabled(True, "all", export_ch)
    u.clear_command_time()


def tune_timed(T, freqs):
    for ch in range(NCH):
        u.set_command_time(ts(T + ch * STEP))
        u.set_rx_freq(treq(freqs[ch]), ch)
    u.set_command_time(ts(T + SECOND_PASS))
    for ch in range(NCH):
        u.set_rx_freq(treq(freqs[ch]), ch)
    u.clear_command_time()


def burst_cmd(t0, n):
    cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_done)
    cmd.num_samps, cmd.stream_now, cmd.time_spec = n, False, ts(t0)
    st.issue_stream_cmd(cmd)


def recv_burst(t0, n, issue=True):
    if issue:
        burst_cmd(t0, n)
    buf = np.zeros((NCH, n), dtype=np.complex64)
    tmp = np.zeros((NCH, 20000), dtype=np.complex64)
    md = uhd.types.RXMetadata()
    got, first = 0, None
    while got < n:
        k = st.recv(tmp, md, 2.0)
        if md.error_code != uhd.types.RXMetadataErrorCode.none:
            raise RuntimeError(md.strerror())
        if k == 0:
            raise RuntimeError("timeout after %d of %d" % (got, n))
        if first is None:
            first = md.time_spec.get_real_secs()
        k = min(k, n - got)
        buf[:, got:got + k] = tmp[:, :k]
        got += k
    return buf, first


def tone_phase(x):
    N = x.shape[1]
    w = np.hanning(N).astype(np.float32)
    F = np.fft.fftfreq(N, 1 / fs)
    X = [np.fft.fft(x[c] * w) for c in range(NCH)]
    P = sum(np.abs(v) ** 2 for v in X)
    k = int(np.argmax(np.where((F > 140e3) & (F < 260e3), P, 0)))
    jj = [(k + d) % N for d in (-2, -1, 0, 1, 2)]
    return np.array([np.degrees(np.angle(np.sum(X[c][jj] * np.conj(X[0][jj])))) for c in range(1, NCH)])


def wrap(d):
    return (np.asarray(d) + 180) % 360 - 180


print(mon_tools.tx_freq(a.band))
# DF setup as the engine: routing, gains, DDC pinned once, then one engine tune
route_timed(u.get_time_now().get_real_secs() + 0.05, DF_SRC, 2)
time.sleep(0.1)
for ch in range(NCH):
    u.set_rx_gain(a.gain, ch)
    u.set_rx_freq(treq(a.band, dsp_none=False), ch)
tune_timed(u.get_time_now().get_real_secs() + 0.05, [a.band] * NCH)
time.sleep(1.5)
ref = tone_phase(recv_burst(u.get_time_now().get_real_secs() + 0.05, 100000)[0])
print("A. reference DF phase ch1/ch2/ch3: %s deg" % " ".join("%+.2f" % v for v in ref))

res = []
for trip in range(a.trips):
    T = u.get_time_now().get_real_secs() + 0.1
    T2 = T + 0.050
    b0 = T - 0.003
    n = int(round((T2 + 0.015 - b0) * fs))
    burst_cmd(b0, n)              # the radio runs commands in order: earliest first
    route_timed(T, ["internal"] * NCH, None)
    tune_timed(T, MONF)
    route_timed(T2, DF_SRC, 2)
    tune_timed(T2, [a.band] * NCH)
    x, first = recv_burst(b0, n, issue=False)
    # ch0 tone amplitude in 0.25 ms blocks: where does it vanish / come back?
    blk = int(0.00025 * fs)
    nbk = n // blk
    F = np.fft.fftfreq(blk, 1 / fs)
    kk = int(np.argmin(np.abs(F - 192e3)))
    amp = np.array([np.abs(np.fft.fft(x[0, i * blk:(i + 1) * blk]))[max(kk - 2, 0):kk + 3].max()
                    for i in range(nbk)])
    on = amp > 0.3 * np.median(amp[:8])
    t_blk = b0 + (np.arange(nbk) + 0.5) * blk / fs
    off_idx = np.where(~on)[0]
    t_off = (t_blk[off_idx[0]] - T) * 1e3 if len(off_idx) else None
    back = np.where(on & (t_blk > T2))[0]
    t_back = (t_blk[back[0]] - T2) * 1e3 if len(back) else None
    time.sleep(0.05)
    ph = tone_phase(recv_burst(u.get_time_now().get_real_secs() + 0.05, 100000)[0])
    d = wrap(ph - ref)
    res.append((t_off, t_back, d))
    print("   trip %2d: ch0 tone gone %s ms after T | back %s ms after T2 | phase change %s deg"
          % (trip + 1, "%+.2f" % t_off if t_off is not None else "NEVER",
             "%+.2f" % t_back if t_back is not None else "NEVER", " ".join("%+.2f" % v for v in d)))
D = np.array([r[2] for r in res])
offs = [r[0] for r in res if r[0] is not None]
print("A. RESULT: ch0 tone vanished %s ms after T (never before T = routing waited for its time: %s); "
      "worst phase change after return %.2f deg"
      % ("%.2f..%.2f" % (min(offs), max(offs)) if offs else "never",
         all(o is not None and o > -0.25 for o in [r[0] for r in res]), float(np.max(np.abs(D)))))

# B. MON-style continuous coverage: chained bursts (NUM_SAMPS_AND_MORE, each next
#    one issued while the previous runs, at most --ahead queued), the last one
#    NUM_SAMPS_AND_DONE. Every packet's time stamp is checked against the sample
#    count, so any gap shows.
AHEAD = 3
t0 = u.get_time_now().get_real_secs() + 0.2
n0 = int(np.ceil(t0 * fs))


def chain_cmd(i):
    last = i == a.nb - 1
    cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_done if last else uhd.types.StreamMode.num_more)
    cmd.num_samps = a.blen
    cmd.stream_now = i > 0
    if i == 0:
        cmd.time_spec = ts(n0 / fs)
    st.issue_stream_cmd(cmd)


issued = 0
for _ in range(AHEAD):
    chain_cmd(issued)
    issued += 1
tmp = np.zeros((NCH, 20000), dtype=np.complex64)
md = uhd.types.RXMetadata()
got_total, errors, gaps, eob = 0, [], 0, 0
deadline = time.monotonic() + 5 + a.nb * a.blen / fs
while got_total < a.nb * a.blen and time.monotonic() < deadline:
    k = st.recv(tmp, md, 0.5)
    if md.error_code != uhd.types.RXMetadataErrorCode.none:
        errors.append(md.strerror())
        if md.error_code == uhd.types.RXMetadataErrorCode.timeout:
            break
        continue
    if k == 0:
        continue
    if md.has_time_spec:
        n_ts = int(round(md.time_spec.get_real_secs() * fs)) - n0
        if n_ts != got_total:
            gaps += 1
    got_total += k
    eob += 1 if md.end_of_burst else 0
    while issued < a.nb and issued * a.blen - got_total < AHEAD * a.blen:
        chain_cmd(issued)
        issued += 1
print("B. %d chained bursts of %d (at most %d queued): received %d of %d samples, time-stamp gaps %d, "
      "end-of-burst marks %d, errors %s"
      % (a.nb, a.blen, AHEAD, got_total, a.nb * a.blen, gaps, eob, errors[:3] if errors else "none"))
