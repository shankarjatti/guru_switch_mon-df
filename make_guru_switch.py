#!/usr/bin/env python3
"""Build guru_switch.grc: the verified DF flowgraph (guru_burst.grc) + MON mode + switching.

  * source: switch_source (this folder; engine libtwinrx_switch.so) in place of
    twinrx_radio_source, with the SAME instance name, so every DF block, tab
    and snippet of guru_burst works unchanged on outputs 0-3
  * MODE selector (DF / MON) above the tabs -> switch_source.set_mode; a mode
    line under it (current mode, switches, last switch time, measured)
  * MON tab: per LO a spectrum, a time graph (real I/Q of verified MON dwells)
    and a status line (its own lock as the engine read it, MON samples counted,
    strongest line of the newest samples, ADC peak), fed from outputs 4-7
  * mode changes ONLY with the MODE selector (user, 2026-09-30); an optional control
    API (--api 127.0.0.1:5124: 'mode df' | 'mode mon' | 'status') is off by default
  * MON is ONE continuous stream (timed start, stop at the switch back); DF is burst mode
  * LAB TONE selector gets 900 MHz (only MON ch0 can see it)

    python3 make_guru_switch.py && GRC_BLOCKS_PATH=$GRC_BLOCKS_PATH:$PWD/grc grcc guru_switch.grc -o .
"""
import argparse
import copy
import sys

import yaml

ap = argparse.ArgumentParser()
ap.add_argument("--src", default="guru_burst.grc")
ap.add_argument("--out", default="guru_switch.grc")
ap.add_argument("--mon", default="900e6:60,2.4e9:46,5.2e9:60,5.8e9:69",
                help="MON band:gain of ch0..ch3 (each its own LO)")
ap.add_argument("--mon-dwell", type=float, default=0.020)
ap.add_argument("--switch-gap", type=float, default=0.010)
ap.add_argument("--start-mode", default="df", choices=["df", "mon"])
ap.add_argument("--api", default="",
                help="host:port for a control API ('mode df' / 'mode mon' / 'status'); OFF by default: "
                     "the mode is changed only with the MODE selector (user, 2026-09-30)")
a = ap.parse_args()
MON = [(float(f), float(g)) for f, g in (x.split(":") for x in a.mon.split(","))]
if len(MON) != 4:
    sys.exit("make_guru_switch: 4 MON bands, one per channel")
for f, _ in MON:
    if not 10e6 <= f <= 6e9 or 5.00e9 <= f <= 5.14e9:
        sys.exit("make_guru_switch: %.4f GHz not usable on this TwinRX" % (f / 1e9))
PORTS = ["A/RX1", "A/RX2", "B/RX1", "B/RX2"]

g = yaml.safe_load(open(a.src))
B = {b["name"]: b for b in g["blocks"]}
C = g["connections"]


def st(x, y):
    return {"alias": "", "bus_sink": False, "bus_source": False, "bus_structure": None,
            "coordinate": [x, y], "rotation": 0, "state": "enabled"}


def add(name, bid, params, xy, template=None):
    p = copy.deepcopy(B[template]["parameters"]) if template else {}
    p.update(params)
    p.setdefault("comment", "")
    blk = {"name": name, "id": bid, "parameters": p, "states": st(*xy)}
    g["blocks"].append(blk)
    B[name] = blk
    return blk


g["options"]["parameters"]["id"] = "guru_switch"
g["options"]["parameters"]["title"] = ("Guru SWITCH: USRP-2945 DF (shared LO, 5 ms / 7 ms hopping) + MON "
                                       "(own LO per channel), switched on the radio clock")

# --- source ----------------------------------------------------------------------
src = B["twinrx_radio_source_0"]
old = src["parameters"]
new = {k: old[k] for k in ("samp_rate", "addresses", "num_bands", "settle", "guard_pre", "gain_trim",
                           "start_delay", "tx_control", "park_freq", "lock_check", "min_slack",
                           "recv_buff_size", "rt_priority", "preroll", "affinity", "alias", "comment",
                           "maxoutbuf", "minoutbuf") if k in old}
for i in range(4):
    for k in ("freq_%d" % i, "gain_%d" % i, "dwell_%d" % i):
        if k in old:
            new[k] = old[k]
new.update(mon_freqs="(%s)" % ", ".join(repr(f) for f, _ in MON),
           mon_gains="(%s)" % ", ".join(repr(gn) for _, gn in MON),
           mon_dwell=repr(a.mon_dwell), start_mode="mode", switch_gap=repr(a.switch_gap),
           comment="DF on outputs 0-3 (as guru_burst), MON on 4-7; mode switched on the radio clock")
src["id"] = "switch_source"
src["parameters"] = new

# --- MODE selector + mode line (above the tabs) ------------------------------------
add("mode", "variable_qtgui_chooser", {
    "gui_hint": "0,0,1,1", "label": "MODE", "type": "string", "num_opts": "2",
    "value": repr(a.start_mode), "option0": "'df'", "label0": "DF - shared LO, coherent hopping",
    "option1": "'mon'", "label1": "MON - own LO per channel", "option2": "2", "label2": "",
    "option3": "3", "label3": "", "option4": "4", "label4": "",
    "comment": "switch_source.set_mode(): taken at the next slot boundary on the radio clock"},
    (8, 60), "tone_band")
add("mode_state", "variable_qtgui_label", {
    "gui_hint": "0,1,1,3", "label": "", "type": "string", "value": "'starting'",
    "comment": "set by the switch snippet from switch_source.get_mode_info() (engine counters)"},
    (250, 60), "stream_state")

# --- lab tone: 900 MHz for MON ch0 -----------------------------------------------------
tb = B["tone_band"]["parameters"]
n = int(tb["num_opts"])
if n < 5 and not any(abs(float(tb["option%d" % i]) - MON[0][0]) < 1 for i in range(n)):
    tb["option%d" % n] = repr(MON[0][0])
    tb["label%d" % n] = "%g MHz (MON ch0 only)" % (MON[0][0] / 1e6)
    tb["num_opts"] = str(n + 1)

# --- MON tab --------------------------------------------------------------------------
tabs = B["tabs"]["parameters"]
MT = int(tabs["num_tabs"])
tabs["num_tabs"] = str(MT + 1)
tabs["label%d" % MT] = "MON"

# MON readout: C++ blocks only (Python's lock is shared with the DF chain, which
# already runs close to its limit at 2 MS/s): per channel the newest 8192-sample
# block, one in SNAP_EVERY, into a probe the GUI reads twice a second. The MON
# sample count shown is the engine's own (every MON sample, packet by packet).
SNAP, SNAP_EVERY = 8192, 25            # 8192 samples = 4.1 ms; one block in 25 = every 102 ms
DISP_EVERY = 10                         # displays: whole 4096-sample blocks, one in 10
FS_T = B["qtgui_freq_sink_x_0"]["parameters"]
TS_T = B["wave_sink"]["parameters"]
for i, (f, gn) in enumerate(MON):
    R, Cc = (i // 2) * 3, (i % 2) * 2
    add("mon_lbl%d" % i, "variable_qtgui_label", {
        "gui_hint": "tabs@%d:%d,%d,1,2" % (MT, R, Cc), "label": "LO%d ch%d %s  %.4g GHz" % (i, i, PORTS[i], f / 1e9),
        "type": "string", "value": "'MON not running'", "comment": "set by the switch snippet"},
        (2200, 1800 + 60 * i), "stream_state")
    fs_ = copy.deepcopy(FS_T)
    fs_.update(name='"MON LO%d ch%d - spectrum"' % (i, i), fc=repr(f), bw="samp_rate", nconnections="1",
               gui_hint="tabs@%d:%d,%d,2,1" % (MT, R + 1, Cc), label1="ch%d %s" % (i, PORTS[i]),
               fftsize="4096", ymax="0", ymin="-140", average="0.2", comment="MON output %d" % (4 + i))
    add("mon_spec%d" % i, "qtgui_freq_sink_x", fs_, (2400, 1800 + 120 * i))
    ts = copy.deepcopy(TS_T)
    ts.update(name='"MON LO%d ch%d - time (real samples, I and Q)"' % (i, i), type="complex",
              nconnections="1", size="400", srate="samp_rate", gui_hint="tabs@%d:%d,%d,2,1" % (MT, R + 1, Cc + 1),
              tr_mode="qtgui.TRIG_MODE_FREE", tr_tag='""', tr_chan="0", tr_delay="0",
              autoscale="True", ctrlpanel="False", label1="I", label2="Q", color1="blue", color2="red",
              ymin="-0.1", ymax="0.1", entags="False", comment="whole 4096-sample blocks of MON output, one in %d" % DISP_EVERY)
    add("mon_time%d" % i, "qtgui_time_sink_x", ts, (2600, 1800 + 120 * i))
    # displays: whole blocks of real samples, one in DISP_EVERY (C++)
    add("mon_s2v%d" % i, "blocks_stream_to_vector", {"type": "complex", "num_items": "4096", "vlen": "1",
        "affinity": "", "alias": "", "maxoutbuf": "0", "minoutbuf": "0"}, (2000, 1800 + 120 * i))
    add("mon_k1n%d" % i, "blocks_keep_one_in_n", {"type": "complex", "n": str(DISP_EVERY), "vlen": "4096",
        "affinity": "", "alias": "", "maxoutbuf": "0", "minoutbuf": "0"}, (2150, 1800 + 120 * i))
    add("mon_v2s%d" % i, "blocks_vector_to_stream", {"type": "complex", "num_items": "4096", "vlen": "1",
        "affinity": "", "alias": "", "maxoutbuf": "0", "minoutbuf": "0"}, (2300, 1800 + 120 * i))
    C.append(["twinrx_radio_source_0", str(4 + i), "mon_s2v%d" % i, "0"])
    C.append(["mon_s2v%d" % i, "0", "mon_k1n%d" % i, "0"])
    C.append(["mon_k1n%d" % i, "0", "mon_v2s%d" % i, "0"])
    C.append(["mon_v2s%d" % i, "0", "mon_spec%d" % i, "0"])
    C.append(["mon_v2s%d" % i, "0", "mon_time%d" % i, "0"])
    # readout snapshot: newest 8192-sample block, one in SNAP_EVERY, into a probe (C++)
    add("mon_snap_s2v%d" % i, "blocks_stream_to_vector", {"type": "complex", "num_items": str(SNAP), "vlen": "1",
        "affinity": "", "alias": "", "maxoutbuf": "0", "minoutbuf": "0"}, (2000, 2400 + 120 * i))
    add("mon_snap_k1n%d" % i, "blocks_keep_one_in_n", {"type": "complex", "n": str(SNAP_EVERY), "vlen": str(SNAP),
        "affinity": "", "alias": "", "maxoutbuf": "0", "minoutbuf": "0"}, (2150, 2400 + 120 * i))
    add("mon_probe%d" % i, "blocks_probe_signal_vx", {"type": "complex", "vlen": str(SNAP),
        "affinity": "", "alias": ""}, (2300, 2400 + 120 * i))
    C.append(["twinrx_radio_source_0", str(4 + i), "mon_snap_s2v%d" % i, "0"])
    C.append(["mon_snap_s2v%d" % i, "0", "mon_snap_k1n%d" % i, "0"])
    C.append(["mon_snap_k1n%d" % i, "0", "mon_probe%d" % i, "0"])

# --- snippet: mode line, MON lines, control API --------------------------------------
HOST, PORT = a.api.split(":") if a.api else ("", "0")
add("snippet_switch", "snippet", {"section": "main_after_start", "priority": "5", "code": '''# MON <-> DF: status twice a second from the engine's own counters (never a
# radio read here: it would wait behind the timed commands), and the control
# API on udp://@@HOST@@:@@PORT@@ ('mode df' | 'mode mon' | 'status').
import json
import socket
import threading
import numpy as np
from PyQt5 import QtCore

_src = self.twinrx_radio_source_0
_FS = float(self.samp_rate)
_MONF = @@MONF@@
self._sw_api_mode = None

def _readout(x):
    N = len(x)
    S = np.abs(np.fft.fft(x * np.hanning(N).astype(np.float32))) ** 2
    F = np.fft.fftfreq(N, 1.0 / _FS)
    k = int(np.argmax(np.where(np.abs(F) >= 20e3, S, 0)))
    return float(F[k]), float(10 * np.log10(S[k] / (np.median(S) + 1e-30))), float(np.abs(x).max())

def _sw_poll():
    mi = _src.get_mode_info()
    last = mi["last_request_to_dwell_ms"]
    txt = ("NOW %s%s | switches %d (not used %d) | last: to %s, request -> first dwell %s, %s | "
           "samples: MON %d, DF %d" % (
               mi["mode"], "" if mi["requested"] == mi["mode"] else "  (switching to %s)" % mi["requested"],
               mi["switches"], mi["switches_bad"], mi["last_switch_to"] or "-",
               "%.1f ms" % last if last else "-", mi["last_switch_ok"] if mi["switches"] else "-",
               mi["mon_dwell_samples"], mi["df_dwell_samples"]))
    self.set_mode_state(txt)
    for c in range(4):
        lk = mi["mon_lock"][c]
        s = "%s | MON samples (engine) %d, MON slots used %d, not used %d" % (
            "LOCKED" if lk else ("LOCK NOT READ YET" if lk is None else "NOT LOCKED"),
            mi["mon_dwell_samples"], mi["mon_slots_verified"], mi["mon_slots_not_used"])
        if mi["mode"] != "MON":
            s = "not in MON (mode %s) | last: " % mi["mode"] + s
        x = np.asarray(getattr(self, "mon_probe%d" % c).level(), dtype=np.complex64)
        if len(x) and mi["mode"] == "MON":
            # a block that overlaps a switch gap (the zeros of DF time) is no MON reading
            if np.count_nonzero(x == 0) > 16:
                s += " | newest block overlaps a switch: not read"
            else:
                f, db, pk = _readout(x)
                s += " | newest %d samples: %s %+.1f kHz %.1f dB | ADC peak %.3f%s" % (
                    len(x), "TONE" if db >= 30 else "no tone, strongest line", f / 1e3, db, pk,
                    "  OVERLOAD" if pk > 0.5 else "")
        getattr(self, "set_mon_lbl%d" % c)(s)
    # the API may have changed the mode: show it on the selector (GUI thread)
    if self._sw_api_mode and self._sw_api_mode != self.mode:
        self.set_mode(self._sw_api_mode)
    self._sw_api_mode = None

self._sw_timer = QtCore.QTimer()
self._sw_timer.timeout.connect(_sw_poll)
self._sw_timer.start(500)

def _api():
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sk.bind(("@@HOST@@", @@PORT@@))
    except OSError as e:
        print("[switch] control API NOT started (%s)" % e)
        return
    print("[switch] control API on udp://@@HOST@@:@@PORT@@  ('mode df' | 'mode mon' | 'status')")
    while True:
        data, peer = sk.recvfrom(256)
        cmd = data.decode(errors="ignore").split()
        try:
            if len(cmd) == 2 and cmd[0] == "mode" and cmd[1] in ("df", "mon"):
                _src.set_mode(cmd[1])            # the engine takes it at the next slot
                self._sw_api_mode = cmd[1]       # the selector follows in the GUI thread
                reply = {"ok": True, "requested": cmd[1]}
            elif cmd and cmd[0] == "status":
                reply = {"ok": True, "mode": _src.get_mode_info(), "schedule": _src.get_schedule_stats()}
            else:
                reply = {"ok": False, "error": "commands: 'mode df' | 'mode mon' | 'status'"}
        except Exception as e:
            reply = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
        sk.sendto(json.dumps(reply, default=str).encode(), peer)

if @@API_ON@@:
    threading.Thread(target=_api, daemon=True).start()
else:
    print("[switch] no control API: the mode changes only with the MODE selector")
'''.replace("@@HOST@@", HOST).replace("@@PORT@@", PORT).replace("@@API_ON@@", "True" if a.api else "False").replace("@@MONF@@", repr([f for f, _ in MON]))},
    (8, 2000))

yaml.safe_dump(g, open(a.out, "w"), default_flow_style=False, sort_keys=False, width=100)
print("wrote %s: DF from %s + MON %s + MODE selector + API udp://%s" % (
    a.out, a.src, ", ".join("ch%d %.4g GHz %g dB" % (i, f / 1e9, gn) for i, (f, gn) in enumerate(MON)), a.api))
