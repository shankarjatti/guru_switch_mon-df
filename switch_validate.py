#!/usr/bin/env python3
"""Step 5: validate the running guru_switch through its control API (RX only).

Switches DF <-> MON --switches times (random hold between --min-hold and
--max-hold s in each mode) and after every switch reads, from the engine's own
counters: the switch verdict, request -> first dwell of the new mode, routing
time. Every --status-every s: slots used / late / unlocked, bursts missing,
timing lost. The DF phase is taken from guru's own meter lines in the receiver
log (/tmp/guru_rx.log, band of the lab tone): compared across the whole run,
before vs after the MON periods.

    python3 switch_validate.py --switches 150
"""
import argparse
import json
import os
import random
import re
import socket
import time

ap = argparse.ArgumentParser()
ap.add_argument("--api", default="127.0.0.1:5124")
ap.add_argument("--switches", type=int, default=150)
ap.add_argument("--min-hold", type=float, default=1.0)
ap.add_argument("--max-hold", type=float, default=6.0)
ap.add_argument("--log", default="/tmp/guru_rx.log")
ap.add_argument("--band", default="2.4000 GHz", help="DF band of the lab tone, as the meter lines write it")
a = ap.parse_args()
H, P = a.api.split(":")


def api(cmd):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3)
    s.sendto(cmd.encode(), (H, int(P)))
    try:
        return json.loads(s.recv(65536).decode())
    finally:
        s.close()


log_start = os.path.getsize(a.log)
t0 = time.time()
first = api("status")
print("start: mode %s, switches %d, slots %d used %d late %d, timing lost %s"
      % (first["mode"]["mode"], first["mode"]["switches"], first["schedule"]["slots"],
         first["schedule"]["valid"], first["schedule"]["late"], first["schedule"]["timing_lost"]))
rows = []
mode = first["mode"]["mode"].lower()
for i in range(a.switches):
    time.sleep(random.uniform(a.min_hold, a.max_hold))
    target = "mon" if mode == "df" else "df"
    before = api("status")["mode"]["switches"]
    api("mode %s" % target)
    t1 = time.monotonic()
    m = None
    while time.monotonic() - t1 < 3:
        m = api("status")["mode"]
        if m["switches"] > before and m["last_switch_ok"] != "pending":
            break
        time.sleep(0.1)
    mode = target
    rows.append({"i": i + 1, "t": time.time() - t0, "to": target, "ok": m["last_switch_ok"],
                 "req_to_dwell_ms": m["last_request_to_dwell_ms"], "route_ms": m["last_route_ms"],
                 "switches": m["switches"], "bad": m["switches_bad"]})
    if (i + 1) % 10 == 0:
        s = api("status")["schedule"]
        print("%3d switches, %4.0f s | this: to %-3s %s, request -> dwell %s ms | total bad %d | slots %d used %d "
              "late %d unlocked %d | bursts missing %d | lost %s"
              % (i + 1, rows[-1]["t"], target.upper(), m["last_switch_ok"],
                 "%.1f" % m["last_request_to_dwell_ms"] if m["last_request_to_dwell_ms"] else "?", m["switches_bad"],
                 s["slots"], s["valid"], s["late"], s["unlocked"], s["bursts"]["missing"], s["timing_lost"]))
        if s["timing_lost"]:
            break
end = api("status")
s, m = end["schedule"], end["mode"]
print("\nEND after %.0f s: switches %d (not used %d) | slots %d used %d late %d unlocked %d skipped %d | "
      "bursts ok %d missing %d | timing lost %s"
      % (time.time() - t0, m["switches"], m["switches_bad"], s["slots"], s["valid"], s["late"], s["unlocked"],
         s["skipped"], s["bursts"]["ok"], s["bursts"]["missing"], s["timing_lost"]))
for t in ("df", "mon"):
    v = [r["req_to_dwell_ms"] for r in rows if r["to"] == t and r["req_to_dwell_ms"]]
    bad = [r for r in rows if r["to"] == t and r["ok"] != "locked"]
    if v:
        print("to %-3s: %d switches, request -> first dwell mean %.1f ms, min %.1f, worst %.1f | not locked/used %d"
              % (t.upper(), len([r for r in rows if r["to"] == t]), sum(v) / len(v), min(v), max(v), len(bad)))
rt = [r["route_ms"] for r in rows if r["route_ms"]]
print("LO routing change: mean %.1f ms, worst %.1f ms" % (sum(rt) / len(rt), max(rt)))

# DF phase of the lab-tone band from guru's own meter lines, over the run
txt = open(a.log, errors="replace").read()[log_start:]
ph = []
for line in txt.splitlines():
    if line.startswith("[meter]") and a.band in line and "ch1" in line:
        v = re.findall(r"ch(\d)\s+([+-]\d+\.\d+)", line)
        if len(v) == 3:
            ph.append([float(x[1]) for x in v])
if ph:
    import numpy as np
    A = np.array(ph)
    ref = A[0]
    d = (A - ref + 180) % 360 - 180
    print("DF %s phase (guru's meter, %d readings over the run): first %s deg; change over the run: "
          "worst %s deg, std %s deg"
          % (a.band, len(A), " ".join("%+.2f" % x for x in ref),
             " ".join("%.2f" % x for x in np.max(np.abs(d), axis=0)), " ".join("%.2f" % x for x in np.std(d, axis=0))))
else:
    print("DF phase: no meter line for %s in the log (lab tone elsewhere?)" % a.band)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
                   "switch_validate_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
json.dump({"args": vars(a), "rows": rows, "end": end, "df_phase": ph}, open(out, "w"), indent=1, default=str)
print("saved", out)
