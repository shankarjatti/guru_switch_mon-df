#!/usr/bin/env python3
"""Run the real guru_fast GUI, show each display band in turn, save a picture.

The receiver hops all bands the whole time (10 ms on / 10 ms off); only the
DISPLAY BAND (and, in the lab, where the calibration tone is parked) changes.
Pictures are taken with Qt's own window capture, after the band has been on
screen for --secs, and saved as results/gui_<band>_<time>.png.

    python3 gui_band_tour.py --secs 25
"""
import argparse
import os
import signal
import sys
import time

from PyQt5 import Qt

import guru_fast as gf

ap = argparse.ArgumentParser()
ap.add_argument("--secs", type=float, default=25.0)
ap.add_argument("--bands", default="2.4e9,5.2e9,5.8e9")
ap.add_argument("--tabs", default="0", help="tab indices to picture, e.g. 0,2")
ap.add_argument("--calibrate", action="store_true", help="press CALIBRATE first and wait for it")
ap.add_argument("--tone-away", action="store_true",
                help="at the end, move the lab tone off every band for a few s and take a picture")
a = ap.parse_args()
bands = [float(x) for x in a.bands.split(",")]
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
os.makedirs(out, exist_ok=True)

qapp = Qt.QApplication(sys.argv)
tb = gf.guru_fast()
gf.snippets_main_after_init(tb)
tb.start()
gf.snippets_main_after_start(tb)
tb.resize(1850, 1300)
tb.show()
signal.signal(signal.SIGINT, lambda *x: Qt.QApplication.quit())
signal.signal(signal.SIGTERM, lambda *x: Qt.QApplication.quit())
state = {"i": 0, "t": time.time(), "cal": a.calibrate}
if a.calibrate:
    t_end = time.time() + 3.0
    while time.time() < t_end:
        qapp.processEvents()
        time.sleep(0.02)
    tb._cal.start(restore_freq=bands[0])
    print("[tour] CALIBRATE pressed")
    while tb._cal.busy:
        qapp.processEvents()
        time.sleep(0.05)
    print("[tour] CALIBRATE result: %s" % tb._cal.status)
    state["t"] = time.time()
print("[tour] showing %.1f GHz" % (bands[0] / 1e9))
(tb.set_tone_band if hasattr(tb, "set_tone_band") else tb.set_disp_band)(bands[0])


def tick():
    if time.time() - state["t"] < a.secs:
        return
    b = bands[state["i"]]
    for ti in [int(x) for x in a.tabs.split(",")]:
        tb.tabs.setCurrentIndex(ti)
        t_end = time.time() + 3.0          # let the plot trigger and draw
        while time.time() < t_end:
            qapp.processEvents()
            time.sleep(0.02)
        path = os.path.join(out, "gui_%dMHz_tab%d_%s.png" % (b / 1e6, ti, time.strftime("%H%M%S")))
        w = None
        (w if w is not None else tb).grab().save(path)
    tb.tabs.setCurrentIndex(0)
    s = tb.twinrx_radio_source_0.get_schedule_stats()
    print("[tour] %.1f GHz picture: %s | schedule %s" % (b / 1e9, path, s))
    state["i"] += 1
    state["t"] = time.time()
    if state["i"] >= len(bands):
        if a.tone_away and not state.get("away_done"):
            state["away_done"] = True
            import socket
            sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sk.settimeout(2.0)
            sk.sendto(b"freq 1000000000", ("127.0.0.1", 5123))
            sk.recv(64)
            t_end = time.time() + 4.0
            while time.time() < t_end:
                qapp.processEvents()
                time.sleep(0.02)
            tb.tabs.setCurrentIndex(0)
            path = os.path.join(out, "gui_tone_away_%s.png" % time.strftime("%H%M%S"))
            tb.grab().save(path)
            print("[tour] tone moved off all bands -- picture: %s" % path)
            sk.sendto(("freq %d" % int(bands[0])).encode(), ("127.0.0.1", 5123))
            sk.recv(64)
            sk.close()
        Qt.QApplication.quit()
        return
    print("[tour] showing %.1f GHz" % (bands[state["i"]] / 1e9))
    (tb.set_tone_band if hasattr(tb, "set_tone_band") else tb.set_disp_band)(bands[state["i"]])


timer = Qt.QTimer()
timer.timeout.connect(tick)
timer.start(250)


def quitting():
    tb.stop()
    tb.wait()
    gf.snippets_main_after_stop(tb)


qapp.aboutToQuit.connect(quitting)
qapp.exec_()
