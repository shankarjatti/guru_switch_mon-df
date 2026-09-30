#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""USRP-2945 (X310 + 2x TwinRX) source with hopping on the radio's clock.

The radio work runs in a C++ engine (engine/twinrx_engine.cpp, loaded from
libtwinrx_engine.so): a receive thread filling a ring buffer and a scheduler
thread sending one timed command batch per slot. Neither ever waits for
Python's interpreter lock, which is what made a Python scheduler miss ~1 % of
slots once the GUI was running. This block only copies samples out of the
ring and places the hop tags.

Why not gr-uhd: driving the same schedule through gr-uhd left ch0 exactly
180 deg off on 6-12 % of 5.8 GHz dwells (gr_flip_test.py); the UHD C++ API
used directly (as pyuhd and this engine do) never did.

Each slot = switching time (settle) + the band's dwell. The band change at
radio time S is one timed batch (gains at S, channel c's RF tune at S +
c*0.4 ms, the same RF tunes again at S + 3 ms), sent one slot ahead; lo_locked
is read at S + lock_check before the next batch is sent.

Output 0 carries, on the exact samples:
  rx_time  at sample 0: the radio time of the first sample (the commanded start)
  hop_off  at S - guard_pre: switching begins (value: the band being switched to)
  hop_cycle  with the hop_off of every switch into band 0: one per cycle
  hop_on   at S + settle - guard_pre: dwell on this band (value: its freq)
A slot that was skipped, late or unlocked -- or whose verdict is not in within
20 ms of its first dwell sample, or (burst mode) whose burst never came -- gets
no hop_on and is never used.

burst=True: the X310 sends only each dwell plus `preroll` seconds before it
(inside the switching time, never used), nothing while the LO relocks. The
engine puts every burst back on the continuous sample timeline, zeros in the
gaps, after checking it starts on its commanded sample and holds exactly its
commanded length -- so the tags and everything downstream are the same as in
continuous mode. A stream
error, a gap in the packet timestamps or a full ring stops all dwell marking
for the rest of the run ("timing lost").
"""
import ctypes
import os
import socket
import time

import numpy as np
import pmt
from gnuradio import gr

from .hop_blocks import _K_OFF, _K_ON

NCH = 4
# start of every cycle: the switch into band 0 (a plot can trigger on it)
_K_CYCLE = pmt.intern("hop_cycle")


def _load():
    lib = ctypes.CDLL(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "libtwinrx_engine.so"))
    D, I, L, P = ctypes.c_double, ctypes.c_int, ctypes.c_long, ctypes.c_void_p
    DP = ctypes.POINTER(ctypes.c_double)
    lib.eng_create.restype = P
    lib.eng_create.argtypes = [ctypes.c_char_p, D, I, DP, DP, DP, DP, D, D, D, D, D, I,
                               I, D, ctypes.c_char_p, I]
    lib.eng_start.restype = D
    lib.eng_start.argtypes = [P, I]
    lib.eng_read.restype = L
    lib.eng_read.argtypes = [P, P, P, P, P, L, D]
    lib.eng_slots.restype = I
    lib.eng_slots.argtypes = [P, L, DP, I]
    lib.eng_stats.restype = None
    lib.eng_stats.argtypes = [P, DP]
    lib.eng_lost_reason.restype = I
    lib.eng_lost_reason.argtypes = [P, ctypes.c_char_p, I]
    lib.eng_burst_info.restype = None
    lib.eng_burst_info.argtypes = [P, DP]
    lib.eng_stop.argtypes = [P]
    lib.eng_destroy.argtypes = [P]
    return lib


def _arr(vals):
    a = (ctypes.c_double * len(vals))(*[float(v) for v in vals])
    return ctypes.cast(a, ctypes.POINTER(ctypes.c_double)), a


class twinrx_radio_source(gr.sync_block):

    def __init__(self, samp_rate=1e6, addresses="addr=192.168.10.2",
                 bands=((2.4e9, 46.0, 0.01),), settle=0.01, guard_pre=0.00025,
                 gain_trim=(0.0, 0.0, 0.0, 0.0), hop_enable=True, start_delay=0.5,
                 tx_control="", park_freq=0.0, lock_check=0.007, min_slack=0.008,
                 recv_buff_size=33554432, rt_priority=0, burst=False, preroll=0.00025):
        gr.sync_block.__init__(self, name="TwinRX Radio-Clock Source",
                               in_sig=None, out_sig=[np.complex64] * NCH)
        self.fs = float(samp_rate)
        self.bands = [(float(f), float(g), float(d)) for f, g, d in bands]
        if not self.bands:
            raise ValueError("twinrx_radio_source: no bands")
        self.settle = float(settle)
        self.gpre = float(guard_pre)
        if not 0 <= self.gpre < self.settle:
            raise ValueError("twinrx_radio_source: need 0 <= guard_pre < settle")
        self.gpost = self.settle - self.gpre
        trim = [float(x) for x in gain_trim][:NCH]
        trim += [0.0] * (NCH - len(trim))
        self.hop_enable = bool(hop_enable)
        self.tx_control = tx_control or ""
        self.wait_max = 0.020
        self.unknown_in_time = 0
        self._slots = {}              # id -> dict(S, freq, next, valid, off_done, on_done)
        self._from_id = 0
        self._wait_since = None
        self._rows = (ctypes.c_double * (6 * 256))()
        self._stat = (ctypes.c_double * 16)()
        self.burst = bool(burst)
        self.preroll = float(preroll)
        self.start_dev = None
        self._h = None
        self._cur = ("starting", 0.0)    # what the samples leaving this block are
        self._band_stats = {}             # freq -> slots / locked / unlocked / late / skipped

        self._lib = _load()
        args = addresses + (",recv_buff_size=%d" % int(recv_buff_size) if recv_buff_size else "")
        self._keep = []
        fp, a1 = _arr([b[0] for b in self.bands])
        gp, a2 = _arr([b[1] for b in self.bands])
        dp, a3 = _arr([b[2] for b in self.bands])
        tp, a4 = _arr(trim)
        self._keep += [a1, a2, a3, a4]
        err = ctypes.create_string_buffer(512)
        self._h = self._lib.eng_create(args.encode(), self.fs, len(self.bands), fp, gp, dp, tp,
                                       self.settle, self.gpre, float(lock_check),
                                       float(min_slack), float(start_delay), int(rt_priority),
                                       1 if self.burst else 0, self.preroll, err, 512)
        if not self._h:
            raise RuntimeError("twinrx_radio_source: radio setup failed: %s" % err.value.decode())
        print("[radio] X310 ready (C++ engine): %d band(s), %.2f ms switching "
              "(%.2f before + %.2f after each switch), DDC 0 Hz, real-time priority %s"
              % (len(self.bands), self.settle * 1e3, self.gpre * 1e3, self.gpost * 1e3,
                 rt_priority if rt_priority else "off"))
        for i, (f, g, d) in enumerate(self.bands):
            print("        band %d: %8.4f GHz  gain %4.1f dB (+trim)  dwell %7.2f ms"
                  % (i, f / 1e9, g, d * 1e3))
        if self.burst:
            print("        BURST mode: the X310 sends only each dwell (+%.2f ms pre-roll inside "
                  "the switching time), nothing while the LO relocks" % (self.preroll * 1e3))
        if float(park_freq) > 0:
            self.set_park_freq(park_freq)

    # ------------------------------------------------------------------ stream
    def start(self):
        self.start_dev = self._lib.eng_start(self._h, 1 if self.hop_enable else 0)
        self._first = True
        return True

    def stop(self):
        if self._h:
            self._lib.eng_stop(self._h)
            print("[radio] stopped. %s" % self.get_schedule_stats())
        return True

    def offset_of(self, t):
        return int(round((t - self.start_dev) * self.fs))

    def _refresh_slots(self):
        n = self._lib.eng_slots(self._h, self._from_id, self._rows, 256)
        r = self._rows
        for j in range(n):
            sid = int(r[6 * j])
            s = self._slots.get(sid)
            if s is None:
                if sid < self._from_id:
                    continue
                s = self._slots[sid] = {"S": r[6 * j + 1], "freq": r[6 * j + 2],
                                        "next": r[6 * j + 3], "off_done": False,
                                        "on_done": False}
            s["valid"] = int(r[6 * j + 4])
            s["why"] = int(r[6 * j + 5])
            if s["valid"] == -1:
                continue
            key = "locked" if s["valid"] == 1 else \
                {1: "skipped", 2: "late", 3: "unlocked", 4: "no burst"}.get(s["why"], "invalid")
            b = self._band_stats.setdefault(s["freq"], {"slots": 0, "locked": 0, "unlocked": 0,
                                                        "late": 0, "skipped": 0, "no burst": 0})
            if not s.get("counted"):
                s["counted"] = key
                b["slots"] += 1
                b[key] = b.get(key, 0) + 1
            elif s["counted"] != key:       # a locked slot whose burst never came
                b[s["counted"]] -= 1
                b[key] = b.get(key, 0) + 1
                s["counted"] = key

    def work(self, input_items, output_items):
        n = len(output_items[0])
        base = self.nitems_written(0)
        self._refresh_slots()
        lost = self.is_timing_lost()
        # Never take more samples out of the ring than may be output now: a
        # dwell whose verdict is still pending holds its first sample back.
        limit = n
        for sid in sorted(self._slots):
            s = self._slots[sid]
            if s["on_done"]:
                continue
            o = self.offset_of(s["S"] + self.gpost)
            if s["valid"] == -1 and o >= base:
                now = time.time()
                if self._wait_since is None:
                    self._wait_since = now
                if now - self._wait_since < self.wait_max:
                    limit = min(limit, o - base)
                break
        if limit <= 0:
            time.sleep(0.0005)
            return 0
        o_ptr = [output_items[c].ctypes.data for c in range(NCH)]
        got = self._lib.eng_read(self._h, o_ptr[0], o_ptr[1], o_ptr[2], o_ptr[3], limit, 20.0)
        if got <= 0:
            return 0
        # verdicts again, after the read: in burst mode the engine turns a slot
        # invalid (its burst never came) before that dwell's samples appear
        self._refresh_slots()
        lost = lost or self.is_timing_lost()
        if self._first:
            self._first = False
            full = int(self.start_dev)
            self.add_item_tag(0, 0, pmt.intern("rx_time"),
                              pmt.make_tuple(pmt.from_uint64(full),
                                             pmt.from_double(self.start_dev - full)))
            self.add_item_tag(0, 0, _K_OFF, pmt.from_double(-1.0))
        end = base + got
        for sid in sorted(self._slots):
            s = self._slots[sid]
            if not s["off_done"]:
                o = max(self.offset_of(s["S"] - self.gpre), base)
                if o < end:
                    self.add_item_tag(0, o, _K_OFF, pmt.from_double(s["freq"]))
                    self._cur = ("switching", s["freq"])
                    if abs(s["freq"] - self.bands[0][0]) < 1.0:
                        self.add_item_tag(0, o, _K_CYCLE, pmt.PMT_T)
                    s["off_done"] = True
            if s["off_done"] and not s["on_done"]:
                o = self.offset_of(s["S"] + self.gpost)
                if o < base:
                    s["on_done"] = True
                elif o < end:
                    if s["valid"] == -1:
                        self.unknown_in_time += 1
                    self._wait_since = None
                    if s["valid"] == 1 and not lost:
                        self.add_item_tag(0, o, _K_ON, pmt.from_double(s["freq"]))
                        self._cur = ("%g ms dwell" % (self._dwell_of(s["freq"]) * 1e3), s["freq"])
                    else:
                        self._cur = ("slot NOT USED: %s" % {0: "ok", 1: "skipped", 2: "late",
                                     3: "unlocked", 4: "no burst"}.get(s.get("why", -1), "no verdict"),
                                     s["freq"])
                    s["on_done"] = True
        done = [sid for sid, s in self._slots.items() if s["on_done"]]
        for sid in done:
            del self._slots[sid]
        if done:
            self._from_id = max(self._from_id, max(done) + 1)
        return got

    def _dwell_of(self, freq):
        return min(self.bands, key=lambda b: abs(b[0] - freq))[2]

    # --------------------------------------------------------------- status
    def get_band_lock_stats(self):
        """Per band: slots finished, locked (used), unlocked, late, skipped."""
        return {f: dict(v) for f, v in self._band_stats.items()}

    def get_current(self):
        """(state, band freq) of the samples this block is emitting now."""
        return self._cur

    def is_timing_lost(self):
        buf = ctypes.create_string_buffer(8)
        return bool(self._lib.eng_lost_reason(self._h, buf, 8))

    def get_schedule_stats(self):
        self._lib.eng_stats(self._h, self._stat)
        o = self._stat
        why = ctypes.create_string_buffer(512)
        lost = self._lib.eng_lost_reason(self._h, why, 512)
        return {"slots": int(o[0]), "valid": int(o[1]), "skipped": int(o[2]), "late": int(o[3]),
                "unlocked": int(o[4]), "unknown_in_time": self.unknown_in_time,
                "max_send_ms": o[5], "avg_send_ms": o[13], "timing_lost": why.value.decode() if lost else None,
                "stream_errors": {"overflow": int(o[7]), "timeout": int(o[8]), "other": int(o[9])},
                "pkt_ts_scale": o[10],
                "bursts": ({"ok": int(o[14]), "missing": int(o[15])} if self.burst else None),
                "rt_priority": {1: "on", 0: "REFUSED by the OS", -1: "off"}[int(o[11])]}

    def get_burst_info(self):
        """Burst mode: the last burst exactly as the radio delivered it."""
        if not self.burst or not self._h:
            return None
        o = (ctypes.c_double * 8)()
        self._lib.eng_burst_info(self._h, o)
        return {"received": int(o[0]), "start_sample": int(o[1]), "commanded": int(o[2]),
                "pre_roll": int(round(self.preroll * self.fs)), "min": int(o[3]), "max": int(o[4]),
                "start_time": self.start_dev + o[1] / self.fs if o[1] >= 0 and self.start_dev else None,
                "dwell_samples_total": int(o[5]), "dwells_total": int(o[6]),
                "ring_fill": int(o[7]), "ring_size": 1 << 22}

    def stream_is_alive(self):
        s = self.get_schedule_stats()
        return s["timing_lost"] is None and not s["stream_errors"]["overflow"] \
            and not s["stream_errors"]["other"]

    def get_stream_stalls(self):
        return self.get_schedule_stats()["stream_errors"]["timeout"]

    def set_park_freq(self, freq):
        """Lab only: park the calibration tone on the displayed band."""
        freq = float(freq)
        if freq <= 0 or not self.tx_control:
            return
        try:
            host, port = self.tx_control.split(":")
            sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sk.settimeout(1.0)
            sk.sendto(("freq %d" % int(freq)).encode(), (host, int(port)))
            sk.recv(64)
            sk.close()
            print("[radio] calibration tone parked on %.4f GHz" % (freq / 1e9))
        except Exception as e:
            print("[radio] TRANSMITTER DID NOT MOVE to %.4f GHz: %s" % (freq / 1e9, e))
