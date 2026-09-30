#!/usr/bin/env python3
"""Step 1 of MON<->DF switching: does the DF phase survive a trip through MON,
and how long does each switch take?  RX only; the HackRF is only told where
to send (its tone through the power divider into all 4 ports).

Per DF band:
  * DF set up (shared LO: ch2 internal + export, ch0/ch1 external, ch3
    companion), tuned twice, reference phase = median of --ref reads.
  * then --rounds pairs, interleaved:
      MON trip  : DF -> MON (export off, all internal, every channel tuned
                  twice to another band, locks checked) -> back to DF
      baseline  : stays in DF, retuned to another band and back (what every
                  DF hop already does), same waits
    after each: chN - ch0 phase at the tone, minus the reference.
    The baseline shows what a plain retune (and the drift over the run) does
    by itself; only a difference between the two is caused by the mode switch.
  * every switch timed on the host clock: routing, tuning, until every
    channel's lo_locked sensor reads true.

Phase = angle of the cross-spectrum at the tone's own bins (+/-2), over
--secs of all 4 channels, captured with a timed num_done command.

    source ~/gnuradio-3.8/setup_env.sh
    python3 switch_check.py --bands 2.4e9:46,5.2e9:60,5.8e9:69 --rounds 50
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
ap.add_argument("--bands", default="2.4e9:46,5.2e9:60,5.8e9:69", help="DF bands, freq_hz:rx_gain_db")
ap.add_argument("--mon-freqs", default="900e6,2.4e9,5.2e9,5.8e9",
                help="MON band of ch0..ch3 (as guru_mon)")
ap.add_argument("--rounds", type=int, default=50, help="MON trips per band (+ as many baselines)")
ap.add_argument("--ref", type=int, default=5, help="reference reads at the start of each band")
ap.add_argument("--rate", type=float, default=2e6)
ap.add_argument("--secs", type=float, default=0.05, help="capture per phase read")
ap.add_argument("--mon-hold", type=float, default=0.2, help="time spent in MON per trip, s")
ap.add_argument("--settle", type=float, default=0.05, help="wait after lock before reading, s")
ap.add_argument("--lock-timeout", type=float, default=2.0)
ap.add_argument("--offset", type=float, default=200e3, help="lab tone offset (only to find its bin)")
a = ap.parse_args()
NCH = 4
BANDS = [(float(f), float(g)) for f, g in (x.split(":") for x in a.bands.split(","))]
MONF = [float(x) for x in a.mon_freqs.split(",")]
DF_SRC = ["external", "external", "internal", "companion"]

u = uhd.usrp.MultiUSRP(a.addr)
u.set_rx_subdev_spec(uhd.usrp.SubdevSpec(mon_tools.SUBDEV), 0)
for ch, ant in enumerate(mon_tools.ANTENNAS):
    u.set_rx_antenna(ant, ch)
u.set_rx_rate(a.rate)
for ch in range(NCH):
    u.set_rx_dc_offset(True, ch)
sa = uhd.usrp.StreamArgs("fc32", "sc16")
sa.channels = list(range(NCH))
st = u.get_rx_stream(sa)
fs = u.get_rx_rate()
N = int(a.secs * fs)
W = np.hanning(N).astype(np.float32)
F = np.fft.fftfreq(N, 1.0 / fs)
WIN = (F > a.offset - 60e3) & (F < a.offset + 60e3)


STEP, SECOND_PASS = 0.0004, 0.003      # the engine's phase-correct tune (twinrx_engine.cpp)
LEAD = 0.03                            # tune scheduled this far ahead on the radio clock


def treq(f, dsp_none=True):
    t = uhd.types.TuneRequest(f)
    t.rf_freq, t.rf_freq_policy = f, uhd.types.TuneRequestPolicy.manual
    if dsp_none:
        t.dsp_freq_policy = uhd.types.TuneRequestPolicy.none      # DDC stays at 0 Hz, never commanded
    else:
        t.dsp_freq, t.dsp_freq_policy = 0.0, uhd.types.TuneRequestPolicy.manual
    return t


def timed_tune(freqs, gain):
    """Exactly as the engine's band_change(): gains at T, channel c's RF tune at
    T + c*0.4 ms, the same 4 RF tunes again at T + 3 ms. Returns T (radio time)."""
    T = u.get_time_now().get_real_secs() + LEAD
    u.set_command_time(uhd.types.TimeSpec(T))
    for ch in range(NCH):
        u.set_rx_gain(gain, ch)
    for ch in range(NCH):
        u.set_command_time(uhd.types.TimeSpec(T + ch * STEP))
        u.set_rx_freq(treq(freqs[ch]), ch)
    u.set_command_time(uhd.types.TimeSpec(T + SECOND_PASS))
    for ch in range(NCH):
        u.set_rx_freq(treq(freqs[ch]), ch)
    u.clear_command_time()
    return T


def locks():
    return [u.get_rx_sensor("lo_locked", ch).to_bool() for ch in range(NCH)]


def wait_locked(T):
    """Radio reads queue behind pending timed commands, so first wait (host) until
    the second pass has executed, then poll every channel's own lock sensor.
    Returns the time from the tune T to 'all locked' in ms of radio time."""
    while u.get_time_now().get_real_secs() < T + SECOND_PASS + 0.0005:
        time.sleep(0.0005)
    while True:
        lk = locks()
        now = u.get_time_now().get_real_secs()
        if all(lk):
            return now - T, lk
        if now - T > a.lock_timeout:
            return None, lk
        time.sleep(0.0005)


def route(sources, export_ch):
    t0 = time.monotonic()
    for ch in range(NCH):
        u.set_rx_lo_export_enabled(False, "all", ch)
    for ch in range(NCH):
        u.set_rx_lo_source(sources[ch], "all", ch)
    if export_ch is not None:
        u.set_rx_lo_export_enabled(True, "all", export_ch)
    return time.monotonic() - t0


def set_df(f, gain):
    """Shared LO: export off everywhere, DF sources, export on ch2, engine tune."""
    t_route = route(DF_SRC, 2)
    T = timed_tune([f] * NCH, gain)
    t_lock, lk = wait_locked(T)
    return {"route_s": t_route, "locked_s": t_lock, "locks": lk}


def set_mon(freqs, gain):
    """Independent LOs: export off, all internal, every channel to its own band (engine tune)."""
    t_route = route(["internal"] * NCH, None)
    T = timed_tune(freqs, gain)
    t_lock, lk = wait_locked(T)
    src = [u.get_rx_lo_source("all", ch) for ch in range(NCH)]
    got = [u.get_rx_freq(ch) for ch in range(NCH)]
    return {"route_s": t_route, "locked_s": t_lock, "locks": lk, "sources": src, "freqs": got}


def df_retune(f_away, f, gain):
    """Baseline: stay in DF (routing untouched): engine tune away, hold, engine tune back."""
    wait_locked(timed_tune([f_away] * NCH, gain))
    time.sleep(a.mon_hold)
    t_lock, lk = wait_locked(timed_tune([f] * NCH, gain))
    return {"locked_s": t_lock, "locks": lk}


def capture():
    buf = np.zeros((NCH, N), dtype=np.complex64)
    md = uhd.types.RXMetadata()
    cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_done)
    cmd.num_samps = N
    cmd.stream_now = False
    cmd.time_spec = u.get_time_now() + uhd.types.TimeSpec(0.05)
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


def phase():
    """chN - ch0 at the tone's own bins; also the tone's level over noise per channel."""
    x = capture()
    X = [np.fft.fft(x[c] * W) for c in range(NCH)]
    P = sum(np.abs(Xc) ** 2 for Xc in X)
    k = int(np.argmax(np.where(WIN, P, 0)))
    jj = [(k + d) % N for d in (-2, -1, 0, 1, 2)]
    ph = [float(np.degrees(np.angle(np.sum(X[c][jj] * np.conj(X[0][jj]))))) for c in range(1, NCH)]
    snr = [float(10 * np.log10(np.abs(X[c][k]) ** 2 / (np.median(np.abs(X[c]) ** 2) + 1e-30)))
           for c in range(NCH)]
    return ph, snr, float(F[k]), float(np.abs(x).max())


def wrap(d):
    return (np.asarray(d) + 180.0) % 360.0 - 180.0


def stats(v):
    v = np.asarray(v, dtype=float)
    return {"mean": float(np.mean(v)), "std": float(np.std(v)), "max_abs": float(np.max(np.abs(v)))}


report = {"args": vars(a), "fs": fs, "bands": []}
for f, gain in BANDS:
    i = min(range(len(MONF)), key=lambda j: abs(MONF[j] - f))
    # MON exactly as guru_mon: channel k on --mon-freqs[k] (each its own band)
    mon_freqs = MONF[:NCH]
    f_away = MONF[(i + 1) % len(MONF)]
    print("\n== DF %.4f GHz, gain %.0f dB  (%s)" % (f / 1e9, gain, mon_tools.tx_freq(f)))
    print("   MON trip: channels to %s GHz; baseline: DF retune to %.4f GHz and back"
          % ("/".join("%.4g" % (m / 1e9) for m in mon_freqs), f_away / 1e9))
    route(DF_SRC, 2)
    for ch in range(NCH):                            # engine init: DDC pinned at 0 Hz, once
        u.set_rx_gain(gain, ch)
        r0 = u.set_rx_freq(treq(f, dsp_none=False), ch)
        if r0.actual_dsp_freq != 0.0:
            raise SystemExit("DDC not at 0 Hz on ch%d" % ch)
    s0 = set_df(f, gain)
    time.sleep(1.5)                                  # the HackRF's retune + LO settle
    ref = [phase() for _ in range(a.ref)]
    P0 = np.degrees(np.angle(np.mean(np.exp(1j * np.radians([r[0] for r in ref])), axis=0)))
    ref_spread = wrap(np.array([r[0] for r in ref]) - P0)
    print("   reference: ch1/ch2/ch3 %+7.2f %+7.2f %+7.2f deg (spread over %d reads %.2f deg), "
          "SNR %s dB, tone %+.0f Hz, ADC peak %.3f, lock %s"
          % (P0[0], P0[1], P0[2], a.ref, float(np.max(np.abs(ref_spread))),
             "/".join("%.0f" % s for s in ref[0][1]), ref[0][2], ref[0][3], s0["locks"]))
    trips, bases = [], []
    for r in range(a.rounds):
        m = set_mon(mon_freqs, gain)
        mon_ok = all(s == "internal" for s in m["sources"]) and all(m["locks"])
        time.sleep(a.mon_hold)
        d = set_df(f, gain)
        time.sleep(a.settle)
        ph, snr, tf, pk = phase()
        trips.append({"to_mon": m, "to_df": d, "mon_ok": mon_ok, "dphase": wrap(np.array(ph) - P0).tolist(),
                      "snr": snr, "tone_hz": tf, "peak": pk})
        b = df_retune(f_away, f, gain)
        time.sleep(a.settle)
        ph, snr, tf, pk = phase()
        bases.append({"retune": b, "dphase": wrap(np.array(ph) - P0).tolist(), "snr": snr})
        if (r + 1) % 10 == 0:
            print("   round %d: last MON trip %s | last baseline %s" % (
                r + 1, " ".join("%+6.2f" % v for v in trips[-1]["dphase"]),
                " ".join("%+6.2f" % v for v in bases[-1]["dphase"])))
    D = np.array([t["dphase"] for t in trips])
    Bd = np.array([b["dphase"] for b in bases])
    band = {"freq": f, "gain": gain, "mon_freqs": mon_freqs, "ref_phase": P0.tolist(),
            "ref_spread_max": float(np.max(np.abs(ref_spread))), "trips": trips, "baselines": bases,
            "mon_trip": {"ch%d" % (c + 1): stats(D[:, c]) for c in range(3)},
            "baseline": {"ch%d" % (c + 1): stats(Bd[:, c]) for c in range(3)},
            "mon_setups_ok": int(sum(t["mon_ok"] for t in trips)),
            "to_mon_lock_s": stats([t["to_mon"]["locked_s"] or np.nan for t in trips]),
            "to_df_lock_s": stats([t["to_df"]["locked_s"] or np.nan for t in trips]),
            "to_mon_route_s": stats([t["to_mon"]["route_s"] for t in trips]),
            "to_df_route_s": stats([t["to_df"]["route_s"] for t in trips]),
            "lock_timeouts": int(sum((t["to_mon"]["locked_s"] is None) + (t["to_df"]["locked_s"] is None)
                                     for t in trips))}
    report["bands"].append(band)
    print("   RESULT %.4f GHz over %d MON trips (MON set up correctly in %d):"
          % (f / 1e9, a.rounds, band["mon_setups_ok"]))
    for c in range(3):
        mt, bl = band["mon_trip"]["ch%d" % (c + 1)], band["baseline"]["ch%d" % (c + 1)]
        print("     ch%d-ch0 after MON trip: mean %+6.2f  std %5.2f  worst %6.2f deg | "
              "baseline retune: mean %+6.2f  std %5.2f  worst %6.2f deg"
              % (c + 1, mt["mean"], mt["std"], mt["max_abs"], bl["mean"], bl["std"], bl["max_abs"]))
    tm, td = band["to_mon_lock_s"], band["to_df_lock_s"]
    print("     lock confirmed after the timed tune (radio clock): DF->MON mean %.1f ms, worst %.1f ms | "
          "MON->DF mean %.1f ms, worst %.1f ms | lock timeouts %d"
          % (tm["mean"] * 1e3, tm["max_abs"] * 1e3, td["mean"] * 1e3, td["max_abs"] * 1e3,
             band["lock_timeouts"]))
    rm, rd = band["to_mon_route_s"], band["to_df_route_s"]
    print("     LO routing change (host clock, before the tune): to MON mean %.1f ms, worst %.1f ms | "
          "to DF mean %.1f ms, worst %.1f ms  (+ %.0f ms tune lead, chosen here)"
          % (rm["mean"] * 1e3, rm["max_abs"] * 1e3, rd["mean"] * 1e3, rd["max_abs"] * 1e3, LEAD * 1e3))

print("\n%s" % mon_tools.tx_freq(2.4e9))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
                   "switch_check_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
json.dump(report, open(out, "w"), indent=1, default=lambda o: bool(o) if isinstance(o, np.bool_) else str(o))
print("saved", out)
