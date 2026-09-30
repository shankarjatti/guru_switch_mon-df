#!/usr/bin/env python3
"""Build guru_mon.grc: MON mode, every TwinRX channel on its OWN LO and own band.

Per LO: its spectrum, its time graph (I and Q of the real samples), a gain
slider, a frequency box and one status line -- LO lock (that channel's own
sensor), samples received (every sample counted), stream breaks, strongest
line + level, ADC peak. LAB TONE only tells the HackRF where to send.

Block templates are taken from guru_burst.grc / guru.grc (same GR 3.8 blocks).

    python3 make_guru_mon.py && grcc guru_mon.grc -o .
    python3 make_guru_mon.py --bands 900e6:40,2.4e9:46,5.2e9:60,5.8e9:69
"""
import argparse
import copy
import os
import sys

import yaml

ap = argparse.ArgumentParser()
ap.add_argument("--bands", default="900e6:40,2.4e9:46,5.2e9:60,5.8e9:69",
                help="freq_hz:rx_gain_db for ch0..ch3 (one band per LO)")
ap.add_argument("--samp-rate", type=float, default=2e6)
ap.add_argument("--out", default="guru_mon.grc")
a = ap.parse_args()
# block templates (GR 3.8 blocks as guru uses them), kept in templates/
TPL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
BANDS = [(float(f), float(g)) for f, g in (x.split(":") for x in a.bands.split(","))]
if len(BANDS) != 4:
    sys.exit("make_guru_mon: 4 bands, one per LO (ch0..ch3)")
for f, _ in BANDS:
    if not 10e6 <= f <= 6e9:
        sys.exit("make_guru_mon: %.4f GHz is outside the TwinRX range (10 MHz - 6 GHz)" % (f / 1e9))
    if 5.00e9 <= f <= 5.14e9:
        sys.exit("make_guru_mon: %.4f GHz: this TwinRX cannot tune into 5.00-5.14 GHz" % (f / 1e9))
if abs(200e6 / a.samp_rate - round(200e6 / a.samp_rate)) > 1e-9:
    sys.exit("make_guru_mon: the X310 samples at 200 MHz / an integer")

T = {b["name"]: b for b in yaml.safe_load(open(os.path.join(TPL, "guru_burst.grc")))["blocks"]}
T.update({"gain": b for b in yaml.safe_load(open(os.path.join(TPL, "guru.grc")))["blocks"] if b["name"] == "gain"})
opts = yaml.safe_load(open(os.path.join(TPL, "guru_burst.grc")))["options"]
PORTS = ["A/RX1", "A/RX2", "B/RX1", "B/RX2"]
ANT = ["RX1", "RX2", "RX1", "RX2"]
blocks, conns = [], []


def st(x, y):
    return {"alias": "", "bus_sink": False, "bus_source": False, "bus_structure": None,
            "coordinate": [x, y], "rotation": 0, "state": "enabled"}


def add(name, bid, params, xy, template=None):
    p = copy.deepcopy(T[template]["parameters"]) if template else {}
    p.update(params)
    p.setdefault("comment", "")
    blocks.append({"name": name, "id": bid, "parameters": p, "states": st(*xy)})


def var(name, value, xy):
    add(name, "variable", {"value": value}, xy)


opts = copy.deepcopy(opts)
opts["parameters"].update(
    id="guru_mon", title="Guru MON: USRP-2945, every channel its own LO and band (monitoring)",
    comment="MON mode: 4 TwinRX channels, each on its OWN internal LO, one band each.\n"
            "GNU Radio 3.8 / UHD 3.15. Everything shown is measured on the RX.",
    description="Monitoring: 4 independent LOs", window_size="1700,1000")
opts["states"] = st(8, 8)

var("samp_rate", repr(int(a.samp_rate)), (200, 8))
var("subdev", repr("A:0 A:1 B:0 B:1"), (300, 8))
add("imports", "import", {"imports": "import mon_tools"}, (420, 8))

# --- top row: lab tone band + what the HackRF answered ------------------------
tone_opts = [BANDS[i][0] for i in range(4)]
add("tone_band", "variable_qtgui_chooser", {
    "gui_hint": "0,0,1,2", "label": "LAB TONE (HackRF) BAND - only tells the HackRF where to send",
    "num_opts": "4", "value": repr(BANDS[1][0]),
    **{"option%d" % i: repr(f) for i, f in enumerate(tone_opts)},
    **{"label%d" % i: "%g MHz (ch%d)" % (f / 1e6, i) for i, f in enumerate(tone_opts)}},
    (8, 120), "tone_band")
add("tx_state", "variable_qtgui_label", {
    "gui_hint": "0,2,1,2", "label": "TRANSMITTER", "type": "string",
    "value": "mon_tools.tx_freq(tone_band)",
    "comment": "The HackRF's own reply to the band request (UDP 'freq'). Not a measurement."},
    (300, 120), "stream_state")

# --- source: stock gr-uhd, 4 channels, each its own internal LO -----------------
u = {"dev_addr": '"addr=192.168.10.2"', "dev_args": '""', "clock_rate": "200e6", "nchan": "4",
     "sd_spec0": "subdev", "samp_rate": "samp_rate", "show_lo_controls": "True", "sync": "none",
     "comment": "MON: every channel its OWN internal LO, export off (set again, in order, by "
                "mon_tools.mon_setup before the start: the TwinRX keeps the last program's routing)"}
for i, (f, g) in enumerate(BANDS):
    u.update({"center_freq%d" % i: "f%d" % i, "gain%d" % i: "g%d" % i, "ant%d" % i: repr(ANT[i]),
              "lo_source%d" % i: "internal", "lo_export%d" % i: "False", "bw%d" % i: "0",
              "rx_agc%d" % i: "Default", "norm_gain%d" % i: "False"})
add("uhd_usrp_source_0", "uhd_usrp_source", u, (8, 400), "uhd_usrp_source_0")
blocks[-1]["states"]["state"] = "enabled"

# --- MON meter: counts every sample, notes stream breaks, keeps a snapshot -------
METER = '''"""MON meter: counts EVERY sample of each channel (real count, not a rate x time),
counts stream breaks (UHD tags each restart after an overflow with rx_time), and
on request keeps the newest `keep` samples of each channel for the readout."""
import time

import numpy as np
import pmt
from gnuradio import gr


class blk(gr.sync_block):
    def __init__(self, nch=4, keep=8192):
        gr.sync_block.__init__(self, name="MON meter", in_sig=[np.complex64] * nch, out_sig=None)
        self.nch, self.keep = nch, keep
        self.count = [0] * nch
        self.rx_time_tags = [0] * nch
        self.t_first = None
        self._buf = [[] for _ in range(nch)]
        self._have = [0] * nch
        self.snap = [None] * nch
        self._want = [True] * nch
        self._key = pmt.intern("rx_time")

    def request(self):
        for c in range(self.nch):
            self._want[c] = True

    def work(self, input_items, output_items):
        n = len(input_items[0])
        if self.t_first is None:
            self.t_first = time.monotonic()
        w0 = self.nitems_read(0)
        for c in range(self.nch):
            self.count[c] += n
            self.rx_time_tags[c] += len(self.get_tags_in_range(c, w0, w0 + n, self._key))
            if self._want[c]:
                x = input_items[c]
                self._buf[c].append(x.copy())
                self._have[c] += len(x)
                if self._have[c] >= self.keep:
                    self.snap[c] = np.concatenate(self._buf[c])[-self.keep:]
                    self._buf[c], self._have[c], self._want[c] = [], 0, False
        return n
'''
add("mon_meter", "epy_block", {"_source_code": METER, "nch": "4", "keep": "8192",
                                "affinity": "", "alias": "", "maxoutbuf": "0", "minoutbuf": "0"},
    (700, 900))
blocks[-1]["states"]["_io_cache"] = ("('MON meter', 'blk', [('nch', '4'), ('keep', '8192')], "
                                     "[('0', 'complex', 1), ('1', 'complex', 1), ('2', 'complex', 1), "
                                     "('3', 'complex', 1)], [], '', [])")

# --- per LO: gain, frequency, status line, spectrum, time graph ----------------
for i, (f, g) in enumerate(BANDS):
    R, C = 1 + (i // 2) * 4, (i % 2) * 2
    add("g%d" % i, "variable_qtgui_range", {
        "gui_hint": "%d,%d,1,1" % (R + 1, C), "label": "ch%d RX gain (dB)" % i, "value": repr(g),
        "comment": "TwinRX gain 0..93 dB"}, (200 + 300 * i, 250), "gain")
    add("f%d" % i, "variable_qtgui_entry", {
        "gui_hint": "%d,%d,1,1" % (R + 1, C + 1), "label": "ch%d frequency (Hz)" % i,
        "type": "real", "value": repr(f)}, (200 + 300 * i, 330))
    add("mon%d" % i, "variable_qtgui_label", {
        "gui_hint": "%d,%d,1,2" % (R, C), "label": "LO%d  ch%d %s" % (i, i, PORTS[i]),
        "type": "string", "value": "'starting'", "comment": "set by the MON poll (snippet)"},
        (200 + 300 * i, 170), "stream_state")
    fs_ = copy.deepcopy(T["qtgui_freq_sink_x_0"]["parameters"])
    fs_.update(name='"LO%d ch%d - spectrum"' % (i, i), fc="f%d" % i, bw="samp_rate",
               nconnections="1", gui_hint="%d,%d,2,1" % (R + 2, C), label1="ch%d %s" % (i, PORTS[i]),
               fftsize="4096", ymax="0", ymin="-140", average="0.2", comment="")
    add("spec%d" % i, "qtgui_freq_sink_x", fs_, (400, 500 + 200 * i))
    ts = copy.deepcopy(T["wave_sink"]["parameters"])
    ts.update(name='"LO%d ch%d - time (real samples, I and Q)"' % (i, i), type="complex",
              nconnections="1", size="400", srate="samp_rate", gui_hint="%d,%d,2,1" % (R + 2, C + 1),
              tr_mode="qtgui.TRIG_MODE_FREE", tr_tag='""', autoscale="True", ctrlpanel="False",
              label1="I", label2="Q", color1="blue", color2="red", ymin="-0.1", ymax="0.1", comment="")
    add("time%d" % i, "qtgui_time_sink_x", ts, (700, 500 + 200 * i))
    conns.append(["uhd_usrp_source_0", str(i), "spec%d" % i, "0"])
    conns.append(["uhd_usrp_source_0", str(i), "time%d" % i, "0"])
    conns.append(["uhd_usrp_source_0", str(i), "mon_meter", str(i)])

# --- MON setup before the start, poll after the start --------------------------
FREQS = "[%s]" % ", ".join("self.f%d" % i for i in range(4))
GAINS = "[%s]" % ", ".join("self.g%d" % i for i in range(4))
add("snippet_mon_setup", "snippet", {"section": "main_after_init", "priority": "0", "code":
    "# MON mode, in order: export off, all LOs internal, tune each channel twice\n"
    "self._mon_setup = mon_tools.mon_setup(self.uhd_usrp_source_0, %s, %s)\n" % (FREQS, GAINS)},
    (8, 700))
add("snippet_mon_poll", "snippet", {"section": "main_after_start", "priority": "0", "code": '''# Twice a second: every channel's own lock sensor, samples counted, stream
# breaks, strongest line of the newest 8192 samples, ADC peak. Every 5 s the
# same line goes to the log.
import time
from PyQt5 import QtCore

self._mon_last_log = 0.0
FS = float(self.samp_rate)

def _mon_poll():
    m = self.mon_meter
    now = time.monotonic()
    el = (now - m.t_first) if m.t_first else 0.0
    log = now - self._mon_last_log >= 5.0
    for c in range(4):
        lk = mon_tools.lo_locked(self.uhd_usrp_source_0, c)
        lock = "LOCKED" if lk else ("LOCK UNKNOWN" if lk is None else "NOT LOCKED")
        brk = max(m.rx_time_tags[c] - 1, 0)
        txt = "%s | %.4f GHz | samples %d (%.3f MS/s) | stream breaks %d" % (
            lock, self.uhd_usrp_source_0.get_center_freq(c) / 1e9, m.count[c],
            (m.count[c] / el / 1e6) if el > 0 else 0.0, brk)
        x = m.snap[c]
        if x is not None:
            r = mon_tools.readout(x, FS)
            txt += " | newest %d samples: %s %+.1f kHz %.1f dB | ADC peak %.3f%s" % (len(x),
                "TONE" if r["tone"] else "no tone, strongest line", r["f"] / 1e3, r["db"],
                r["peak"], "  OVERLOAD" if r["peak"] > 0.5 else "")
        getattr(self, "set_mon%d" % c)(txt)
        if log:
            print("[mon] %s ch%d %s" % (time.strftime("%H:%M:%S"), c, txt))
    if log:
        self._mon_last_log = now
    m.request()

self._mon_timer = QtCore.QTimer()
self._mon_timer.timeout.connect(_mon_poll)
self._mon_timer.start(500)
'''}, (8, 800))

g = {"options": opts, "blocks": blocks, "connections": conns, "metadata": {"file_format": 1}}
yaml.safe_dump(g, open(a.out, "w"), default_flow_style=False, sort_keys=False, width=100)
for i, (f, gg) in enumerate(BANDS):
    print("LO%d ch%d %s: %.4f GHz, gain %g dB" % (i, i, PORTS[i], f / 1e9, gg))
print("wrote", a.out)
