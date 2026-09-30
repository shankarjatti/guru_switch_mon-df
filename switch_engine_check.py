#!/usr/bin/env python3
"""Engine + switch_source on the radio, no GUI: DF and MON in turn, --cycles times.

The HackRF sends the tone on --tone-band (cable: into all 4 ports). A sink
block reads all 8 outputs and measures every dwell as it arrives:
  DF  (outputs 0-3, between hop_on and the next hop_off): chN - ch0 phase at
      the tone's bins, only for dwells of the tone band
  MON (outputs 4-7, per mon_on dwell): per channel, is the tone there (the
      channel on the tone band must see it, the others must not), and are
      the MON samples continuous (every MON dwell the length commanded)
Then: DF phase after every return from MON vs the first DF period, switch
times (request -> first dwell of the new mode), schedule and burst stats.

    source ~/gnuradio-3.8/setup_env.sh
    python3 switch_engine_check.py --cycles 10
"""
import argparse
import json
import os
import time

import numpy as np
import pmt
from gnuradio import gr

import switch_source

ap = argparse.ArgumentParser()
ap.add_argument("--cycles", type=int, default=10)
ap.add_argument("--df-secs", type=float, default=2.0)
ap.add_argument("--mon-secs", type=float, default=2.0)
ap.add_argument("--tone-band", type=float, default=2.4e9)
ap.add_argument("--rate", type=float, default=2e6)
ap.add_argument("--rt", type=int, default=90)
ap.add_argument("--switch-gap", type=float, default=0.010)
a = ap.parse_args()
NCH = 4
FS = a.rate
BANDS = [(2.4e9, 46.0, 0.005), (5.2e9, 60.0, 0.005), (5.8e9, 69.0, 0.005)]
MONF = (900e6, 2.4e9, 5.2e9, 5.8e9)
MON_DWELL = 0.020


def tone_line(x):
    N = len(x)
    w = np.hanning(N).astype(np.float32)
    S = np.abs(np.fft.fft(x * w)) ** 2
    F = np.fft.fftfreq(N, 1 / FS)
    k = int(np.argmax(np.where(np.abs(F) > 20e3, S, 0)))
    return float(F[k]), float(10 * np.log10(S[k] / (np.median(S) + 1e-30)))


class sink(gr.sync_block):
    def __init__(self):
        gr.sync_block.__init__(self, "check sink", in_sig=[np.complex64] * (2 * NCH), out_sig=None)
        self.df_band = None
        self.df_buf = None
        self.df = []                   # (time, band, phases[3], snr0)
        self.mon_buf = None
        self.mon = []                  # (time, len, [(f, db)] per channel)
        self.mon_bad = 0
        self.t0 = time.monotonic()
        self.mode_now = "DF"

    def _end_df(self):
        if self.df_buf is not None and self.df_band is not None and sum(len(v) for v in self.df_buf[0]) > 1000:
            x = [np.concatenate(b) for b in self.df_buf]
            if abs(self.df_band - a.tone_band) < 1:
                N = len(x[0])
                w = np.hanning(N).astype(np.float32)
                X = [np.fft.fft(v * w) for v in x]
                F = np.fft.fftfreq(N, 1 / FS)
                P = sum(np.abs(v) ** 2 for v in X)
                k = int(np.argmax(np.where((F > 140e3) & (F < 260e3), P, 0)))
                jj = [(k + d) % N for d in (-2, -1, 0, 1, 2)]
                ph = [float(np.degrees(np.angle(np.sum(X[c][jj] * np.conj(X[0][jj]))))) for c in range(1, NCH)]
                snr = float(10 * np.log10(np.abs(X[0][k]) ** 2 / (np.median(np.abs(X[0]) ** 2) + 1e-30)))
                self.df.append((time.monotonic() - self.t0, self.df_band, ph, snr, N))
        self.df_buf = None

    def _end_mon(self):
        if self.mon_buf is not None:
            x = [np.concatenate(b) for b in self.mon_buf]
            if len(x[0]):
                self.mon.append((time.monotonic() - self.t0, len(x[0]), [tone_line(v) for v in x]))
        self.mon_buf = None

    def work(self, input_items, output_items):
        inp = input_items
        n = len(inp[0])
        w0 = self.nitems_read(0)
        ev = []
        for t in self.get_tags_in_range(0, w0, w0 + n):
            k = pmt.symbol_to_string(t.key)
            if k in ("hop_on", "hop_off"):
                ev.append((t.offset - w0, k, pmt.to_double(t.value)))
        for t in self.get_tags_in_range(NCH, w0, w0 + n):
            k = pmt.symbol_to_string(t.key)
            if k in ("mon_on", "mon_bad", "mon_off"):
                ev.append((t.offset - w0, k, 0.0))
        ev.sort()
        pos = 0
        for off, k, v in ev + [(n, None, 0)]:
            if off > pos:
                if self.df_buf is not None:
                    for c in range(NCH):
                        self.df_buf[c].append(inp[c][pos:off].copy())
                if self.mon_buf is not None:
                    for c in range(NCH):
                        self.mon_buf[c].append(inp[NCH + c][pos:off].copy())
            pos = off
            if k == "hop_off":
                self._end_df()
                self.df_band = v if v > 0 else None
            elif k == "hop_on":
                self._end_df()
                self.df_band = v
                self.df_buf = [[] for _ in range(NCH)]
            elif k == "mon_on":
                self._end_mon()
                self.mon_buf = [[] for _ in range(NCH)]
            elif k == "mon_off":
                self._end_mon()
            elif k == "mon_bad":
                self._end_mon()
                self.mon_bad += 1
        return n


src = switch_source.switch_source(samp_rate=FS, bands=BANDS, settle=0.007, guard_pre=0.00025,
                                  tx_control="127.0.0.1:5123", park_freq=a.tone_band, lock_check=0.0065,
                                  min_slack=0.003, rt_priority=a.rt, preroll=0.00025, mon_freqs=MONF,
                                  mon_gains=(60, 46, 60, 69), mon_dwell=MON_DWELL, start_mode="df",
                                  switch_gap=a.switch_gap)
snk = sink()
tb = gr.top_block()
for c in range(2 * NCH):
    tb.connect((src, c), (snk, c))
tb.start()
time.sleep(1.5 + a.df_secs)
marks = []
for cyc in range(a.cycles):
    marks.append(("MON", time.monotonic() - snk.t0))
    src.set_mode("mon")
    time.sleep(a.mon_secs)
    mi_mon = src.get_mode_info()
    marks.append(("DF", time.monotonic() - snk.t0))
    src.set_mode("df")
    time.sleep(a.df_secs)
    mi_df = src.get_mode_info()
    print("cycle %2d: to MON %s ms (%s) | back to DF %s ms (%s, routing %.1f ms) | DF dwells %d, MON dwells %d, MON not used %d"
          % (cyc + 1, "%.1f" % mi_mon["last_request_to_dwell_ms"] if mi_mon["last_request_to_dwell_ms"] else "?",
             mi_mon["last_switch_ok"],
             "%.1f" % mi_df["last_request_to_dwell_ms"] if mi_df["last_request_to_dwell_ms"] else "?",
             mi_df["last_switch_ok"], mi_df["last_route_ms"], len(snk.df), len(snk.mon), snk.mon_bad))
tb.stop()
tb.wait()
stats = src.get_schedule_stats()
mi = src.get_mode_info()
bi = src.get_burst_info()

# DF phase per DF period (between marks) vs the first period
periods = []
edges = [0.0] + [t for m, t in marks if m == "MON"] + [1e9]
for j in range(len(edges) - 1):
    p = [d for d in snk.df if edges[j] <= d[0] < edges[j + 1]]
    if p:
        ph = np.array([d[2] for d in p])
        periods.append((len(p), np.degrees(np.angle(np.mean(np.exp(1j * np.radians(ph)), axis=0)))))
ref = periods[0][1]
print("\nDF (tone band %.4f GHz) phase per DF period (ch1/ch2/ch3), change vs the first period:" % (a.tone_band / 1e9))
worst = 0.0
for j, (n, m) in enumerate(periods):
    d = (m - ref + 180) % 360 - 180
    worst = max(worst, float(np.max(np.abs(d))))
    print("  period %2d: %4d dwells  %+8.2f %+8.2f %+8.2f deg   change %+6.2f %+6.2f %+6.2f"
          % (j, n, m[0], m[1], m[2], d[0], d[1], d[2]))
dfall = np.array([d[2] for d in snk.df])
spread = [float(np.std(((dfall[:, c] - ref[c] + 180) % 360) - 180)) for c in range(3)] if len(dfall) else []
print("  worst period change %.2f deg; single-dwell spread (std) %s deg; DF dwell lengths %s"
      % (worst, "/".join("%.2f" % s for s in spread), sorted(set(d[4] for d in snk.df))))

# MON: which channel saw the tone, dwell lengths
tone_ch = [i for i, f in enumerate(MONF) if abs(f - a.tone_band) < 1]
lens = sorted(set(m[1] for m in snk.mon))
seen = np.array([[l[1] for l in m[2]] for m in snk.mon]) if snk.mon else np.zeros((0, 4))
print("\nMON: %d dwells measured (%d not used), lengths %s samples (commanded %d)"
      % (len(snk.mon), snk.mon_bad, lens, int(MON_DWELL * FS)))
for c in range(NCH):
    if len(seen):
        print("  ch%d %.4g GHz: tone line over noise median %.1f dB (min %.1f)%s"
              % (c, MONF[c] / 1e9, float(np.median(seen[:, c])), float(np.min(seen[:, c])),
                 "   <- the tone band" if c in tone_ch else ""))
print("\nswitches %d (bad %d); schedule %s" % (mi["switches"], mi["switches_bad"],
      {k: stats[k] for k in ("slots", "valid", "skipped", "late", "unlocked", "timing_lost", "bursts")}))
print("samples: MON dwell %d, DF dwell %d; ring fill at the end %d" % (mi["mon_dwell_samples"],
      mi["df_dwell_samples"], bi["ring_fill"]))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
                   "switch_engine_check_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
json.dump({"args": vars(a), "periods": [(n, m.tolist()) for n, m in periods], "df": snk.df,
           "mon": snk.mon, "mon_bad": snk.mon_bad, "marks": marks, "stats": stats, "mode": mi}, open(out, "w"),
          indent=1, default=str)
print("saved", out)
