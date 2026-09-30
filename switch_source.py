#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""USRP-2945 source with DF and MON modes, switched on the radio's clock.

The engine (oot/engine/twinrx_engine.cpp, built as libtwinrx_switch.so in
this folder -- NOT the installed doa one) runs:
  DF  : the verified hopping (board B exports its LO: ch0/ch1 external, ch2
        internal + export, ch3 companion), every band on all 4 channels
  MON : every channel on its OWN internal LO and own band, not retuned while
        MON lasts: consecutive MON bursts join with no gap
A mode request (set_mode) is taken at the next slot the scheduler plans: the
LO routing is sent timed at that slot's S, then the usual phase-correct tune.

Outputs 0-3 (DF): exactly what twinrx_radio_source gives -- hop_off / hop_on /
  hop_cycle on the exact samples, zeros outside DF dwells. A MON period starts
  with hop_off = -1 (no band), so the DF chain measures nothing during MON.
Outputs 4-7 (MON): the samples of MON slots only (zeros during DF), tagged
  mon_on  at the first sample of every MON dwell whose slot was verified
          (sent in time, every channel's own lock read true, burst came),
          value = the slot id
  mon_bad at a MON dwell that was NOT verified (value: why)
  mon_off at the sample right after the last MON dwell of a MON period
A switch between the modes has a gap (switch_gap) between the old mode's last
dwell and the new slot; the end marks (hop_off on 0-3, mon_off on 4-7) are put
exactly at the end of the old mode's last dwell, not after the gap.
  rx_time at sample 0 on every output.
"""
import ctypes
import os
import socket
import time

import numpy as np
import pmt
from gnuradio import gr

from doa.hop_blocks import _K_OFF, _K_ON

NCH = 4
_K_CYCLE = pmt.intern("hop_cycle")
_K_MON_ON = pmt.intern("mon_on")
_K_MON_BAD = pmt.intern("mon_bad")
_K_MON_OFF = pmt.intern("mon_off")
WHY = {0: "ok", 1: "skipped", 2: "late", 3: "unlocked", 4: "no burst"}
ROW = 10


def _load():
    lib = ctypes.CDLL(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "oot", "engine", "libtwinrx_switch.so"))
    D, I, L, P = ctypes.c_double, ctypes.c_int, ctypes.c_long, ctypes.c_void_p
    DP = ctypes.POINTER(ctypes.c_double)
    lib.eng_create2.restype = P
    lib.eng_create2.argtypes = [ctypes.c_char_p, D, I, DP, DP, DP, DP, D, D, D, D, D, I, I, D,
                                I, DP, DP, D, I, ctypes.c_char_p, I]
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
    lib.eng_set_mode.restype = I
    lib.eng_set_mode.argtypes = [P, I]
    lib.eng_mode_info.restype = None
    lib.eng_mode_info.argtypes = [P, DP]
    lib.eng_set_switch_gap.restype = None
    lib.eng_set_switch_gap.argtypes = [P, D]
    lib.eng_stop.argtypes = [P]
    lib.eng_destroy.argtypes = [P]
    return lib


def _arr(vals):
    a = (ctypes.c_double * len(vals))(*[float(v) for v in vals])
    return ctypes.cast(a, ctypes.POINTER(ctypes.c_double)), a


class switch_source(gr.sync_block):

    def __init__(self, samp_rate=2e6, addresses="addr=192.168.10.2",
                 bands=((2.4e9, 46.0, 0.005),), settle=0.007, guard_pre=0.00025,
                 gain_trim=(0.0, 0.0, 0.0, 0.0), start_delay=0.5, tx_control="", park_freq=0.0,
                 lock_check=0.0065, min_slack=0.003, recv_buff_size=33554432, rt_priority=0,
                 preroll=0.00025, mon_freqs=(900e6, 2.4e9, 5.2e9, 5.8e9),
                 mon_gains=(60.0, 46.0, 60.0, 69.0), mon_dwell=0.020, start_mode="df",
                 switch_gap=0.025):
        gr.sync_block.__init__(self, name="TwinRX DF/MON Source",
                               in_sig=None, out_sig=[np.complex64] * (2 * NCH))
        self.fs = float(samp_rate)
        self.bands = [(float(f), float(g), float(d)) for f, g, d in bands]
        if not self.bands:
            raise ValueError("switch_source: no DF band")
        self.mon_freqs = [float(x) for x in mon_freqs][:NCH]
        self.mon_gains = [float(x) for x in mon_gains][:NCH]
        self.mon_dwell = float(mon_dwell)
        if len(self.mon_freqs) != NCH or len(self.mon_gains) != NCH:
            raise ValueError("switch_source: 4 MON frequencies and 4 MON gains")
        self.settle = float(settle)
        self.gpre = float(guard_pre)
        self.gpost = self.settle - self.gpre
        trim = [float(x) for x in gain_trim][:NCH]
        trim += [0.0] * (NCH - len(trim))
        self.tx_control = tx_control or ""
        self.wait_max = 0.020
        self.unknown_in_time = 0
        self._slots = {}
        self._from_id = 0
        self._wait_since = None
        self._rows = (ctypes.c_double * (ROW * 256))()
        self._stat = (ctypes.c_double * 16)()
        self._mi = (ctypes.c_double * 16)()
        self.preroll = float(preroll)
        self.start_dev = None
        self._h = None
        self._cur = ("starting", 0.0)
        self._band_stats = {}
        # sample regions: (first output sample, mode) in time order
        self._regions = []
        self._mon_verified = 0
        self._mon_bad = 0

        self._lib = _load()
        args = addresses + (",recv_buff_size=%d" % int(recv_buff_size) if recv_buff_size else "")
        self._keep = []
        ptrs = []
        for vals in ([b[0] for b in self.bands], [b[1] for b in self.bands], [b[2] for b in self.bands],
                     trim, self.mon_freqs, self.mon_gains):
            p, keep = _arr(vals)
            ptrs.append(p)
            self._keep.append(keep)
        m0 = 1 if str(start_mode).lower() == "mon" else 0
        err = ctypes.create_string_buffer(512)
        self._h = self._lib.eng_create2(args.encode(), self.fs, len(self.bands), ptrs[0], ptrs[1], ptrs[2],
                                        ptrs[3], self.settle, self.gpre, float(lock_check),
                                        float(min_slack), float(start_delay), int(rt_priority), 1,
                                        self.preroll, 1, ptrs[4], ptrs[5], self.mon_dwell, m0, err, 512)
        if not self._h:
            raise RuntimeError("switch_source: radio setup failed: %s" % err.value.decode())
        # extra time before a slot that changes the LO routing (its batch is longer to send)
        self.switch_gap = float(switch_gap)
        self._lib.eng_set_switch_gap(self._h, self.switch_gap)
        print("[radio] X310 ready (C++ engine, DF + MON): start mode %s, real-time priority %s"
              % ("MON" if m0 else "DF", rt_priority if rt_priority else "off"))
        for i, (f, g, d) in enumerate(self.bands):
            print("        DF band %d: %8.4f GHz  gain %4.1f dB (+trim)  dwell %6.2f ms, %.2f ms switching"
                  % (i, f / 1e9, g, d * 1e3, self.settle * 1e3))
        print("        MON: %s  gains %s dB, %g ms bursts back to back (own LO per channel)"
              % ("  ".join("ch%d %.4g GHz" % (c, self.mon_freqs[c] / 1e9) for c in range(NCH)),
                 "/".join("%g" % g for g in self.mon_gains), self.mon_dwell * 1e3))
        if float(park_freq) > 0:
            self.set_park_freq(park_freq)

    # ------------------------------------------------------------------ stream
    def start(self):
        self.start_dev = self._lib.eng_start(self._h, 1)
        self._first = True
        return True

    def stop(self):
        if self._h:
            self._lib.eng_stop(self._h)
            print("[radio] stopped. %s" % self.get_schedule_stats())
            print("[radio] modes: %s" % self.get_mode_info())
        return True

    def offset_of(self, t):
        return int(round((t - self.start_dev) * self.fs))

    def _refresh_slots(self):
        n = self._lib.eng_slots(self._h, self._from_id, self._rows, 256)
        r = self._rows
        for j in range(n):
            q = ROW * j
            sid = int(r[q])
            s = self._slots.get(sid)
            if s is None:
                if sid < self._from_id:
                    continue
                s = self._slots[sid] = {"S": r[q + 1], "freq": r[q + 2], "off_done": False,
                                        "on_done": False, "mode": int(r[q + 6]), "band": int(r[q + 7]),
                                        "pre": r[q + 8], "tuned": bool(r[q + 9])}
                prev_mode = self._regions[-1][1] if self._regions else s["mode"]
                s["mode_change"] = s["mode"] != prev_mode
                # the old mode's last dwell ended switch_gap before this slot's guard
                back = (self.gpre if s["tuned"] else 0.0) + (self.switch_gap if s["mode_change"] else 0.0)
                start = self.offset_of(s["S"] - back)
                s["region_start"] = start
                if not self._regions or start > self._regions[-1][0]:
                    self._regions.append((start, s["mode"]))
            s["valid"] = int(r[q + 4])
            s["why"] = int(r[q + 5])
            if s["valid"] == -1:
                continue
            key = "locked" if s["valid"] == 1 else WHY.get(s["why"], "invalid")
            # MON slots under -1.0: a number (the DF screen compares the keys with its
            # band frequencies) that is no DF band
            bkey = -1.0 if s["mode"] == 1 else s["freq"]
            b = self._band_stats.setdefault(bkey, {"slots": 0, "locked": 0, "unlocked": 0,
                                                   "late": 0, "skipped": 0, "no burst": 0})
            if not s.get("counted"):
                s["counted"] = key
                b["slots"] += 1
                b[key] = b.get(key, 0) + 1
            elif s["counted"] != key:
                b[s["counted"]] -= 1
                b[key] = b.get(key, 0) + 1
                s["counted"] = key

    def _split(self, output_items, base, got):
        """MON outputs = a copy of the samples; then zero, on each side, what
        belongs to the other mode."""
        for c in range(NCH):
            output_items[NCH + c][:got] = output_items[c][:got]
        end = base + got
        # regions overlapping [base, end)
        while len(self._regions) > 1 and self._regions[1][0] <= base:
            self._regions.pop(0)
        for j, (start, mode) in enumerate(self._regions):
            stop = self._regions[j + 1][0] if j + 1 < len(self._regions) else end
            a, b = max(start, base) - base, min(stop, end) - base
            if b <= a:
                continue
            side = NCH if mode == 0 else 0          # zero the OTHER mode's outputs
            for c in range(NCH):
                output_items[side + c][a:b] = 0
        if self._regions and self._regions[0][0] > base:     # before the first slot: nothing
            a = min(self._regions[0][0], end) - base
            for c in range(2 * NCH):
                output_items[c][:a] = 0

    def work(self, input_items, output_items):
        n = len(output_items[0])
        base = self.nitems_written(0)
        self._refresh_slots()
        lost = self.is_timing_lost()
        limit = n
        for sid in sorted(self._slots):
            s = self._slots[sid]
            if s["on_done"]:
                continue
            o = self.offset_of(s["S"] + s["pre"])
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
        self._refresh_slots()
        lost = lost or self.is_timing_lost()
        self._split(output_items, base, got)
        if self._first:
            self._first = False
            full = int(self.start_dev)
            for c in (0, NCH):
                self.add_item_tag(c, 0, pmt.intern("rx_time"),
                                  pmt.make_tuple(pmt.from_uint64(full),
                                                 pmt.from_double(self.start_dev - full)))
            self.add_item_tag(0, 0, _K_OFF, pmt.from_double(-1.0))
        end = base + got
        for sid in sorted(self._slots):
            s = self._slots[sid]
            if not s["off_done"]:
                if s["tuned"]:
                    o = max(self.offset_of(s["S"] - self.gpre), base)
                    r = max(s["region_start"], base)
                    if min(o, r) >= end:
                        continue
                    if s["mode"] == 0:
                        if s["mode_change"] and not s.get("mon_off_done"):
                            if r >= end:
                                continue
                            self.add_item_tag(NCH, r, _K_MON_OFF, pmt.PMT_T)     # MON period over
                            s["mon_off_done"] = True
                        if o >= end:
                            continue
                        self.add_item_tag(0, o, _K_OFF, pmt.from_double(s["freq"]))
                        self._cur = ("DF switching", s["freq"])
                        if abs(s["freq"] - self.bands[0][0]) < 1.0:
                            self.add_item_tag(0, o, _K_CYCLE, pmt.PMT_T)
                    else:
                        # a MON period begins: the DF chain sees a switch to no band,
                        # right where its last dwell ended
                        at = r if s["mode_change"] else o
                        if at >= end:
                            continue
                        self.add_item_tag(0, at, _K_OFF, pmt.from_double(-1.0))
                        self._cur = ("switching to MON", 0.0)
                s["off_done"] = True
            if s["off_done"] and not s["on_done"]:
                o = self.offset_of(s["S"] + s["pre"])
                if o < base:
                    s["on_done"] = True
                elif o < end:
                    if s["valid"] == -1:
                        self.unknown_in_time += 1
                    self._wait_since = None
                    good = s["valid"] == 1 and not lost
                    if s["mode"] == 0:
                        if good:
                            self.add_item_tag(0, o, _K_ON, pmt.from_double(s["freq"]))
                            self._cur = ("DF %g ms dwell" % (self._dwell_of(s["freq"]) * 1e3), s["freq"])
                        else:
                            self._cur = ("DF slot NOT USED: %s" % WHY.get(s.get("why", -1), "no verdict"),
                                         s["freq"])
                    else:
                        if good:
                            self.add_item_tag(NCH, o, _K_MON_ON, pmt.from_long(sid))
                            self._mon_verified += 1
                            self._cur = ("MON", 0.0)
                        else:
                            why = "timing lost" if lost else WHY.get(s.get("why", -1), "no verdict")
                            self.add_item_tag(NCH, o, _K_MON_BAD, pmt.intern(why))
                            self._mon_bad += 1
                            self._cur = ("MON slot NOT USED: %s" % why, 0.0)
                    s["on_done"] = True
        done = [sid for sid, s in self._slots.items() if s["on_done"]]
        for sid in done:
            del self._slots[sid]
        if done:
            self._from_id = max(self._from_id, max(done) + 1)
        return got

    def _dwell_of(self, freq):
        return min(self.bands, key=lambda b: abs(b[0] - freq))[2]

    # ----------------------------------------------------------------- modes
    def set_mode(self, mode):
        """'df' / 'mon' (or 0 / 1). Taken at the next slot the engine plans."""
        m = 1 if str(mode).lower() in ("mon", "1") else 0
        r = self._lib.eng_set_mode(self._h, m)
        print("[radio] mode %s requested" % ("MON" if m else "DF"))
        return r

    def get_mode_info(self):
        self._lib.eng_mode_info(self._h, self._mi)
        o = self._mi
        name = {0: "DF", 1: "MON"}
        req, sw_S, sw_dwell = o[4], o[5], o[6]
        return {"requested": name.get(int(o[0])), "mode": name.get(int(o[1])),
                "switches": int(o[2]), "switches_bad": int(o[3]),
                "last_switch_to": name.get(int(o[8])),
                "last_switch_ok": {-1: "pending", 0: "NOT locked / not used", 1: "locked"}.get(int(o[7])),
                # request -> first dwell sample of the new mode, on the radio clock
                "last_request_to_dwell_ms": (sw_dwell - req) * 1e3 if req and sw_dwell > req else None,
                "last_switch_to_dwell_ms": (sw_dwell - sw_S) * 1e3 if sw_S else None,
                "mon_dwell_samples": int(o[9]), "df_dwell_samples": int(o[10]),
                "last_route_ms": o[11],
                # each channel's own lock as the engine last read it in MON (None: not read yet)
                "mon_lock": [None if o[12 + c] < 0 else bool(o[12 + c]) for c in range(NCH)],
                "mon_slots_verified": self._mon_verified, "mon_slots_not_used": self._mon_bad}

    # --------------------------------------------------------------- status
    def get_band_lock_stats(self):
        return {f: dict(v) for f, v in self._band_stats.items()}

    def get_current(self):
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
                "pkt_ts_scale": o[10], "bursts": {"ok": int(o[14]), "missing": int(o[15])},
                "rt_priority": {1: "on", 0: "REFUSED by the OS", -1: "off"}[int(o[11])]}

    def get_burst_info(self):
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
        """Lab only: tell the calibration transmitter where to send."""
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
            print("[radio] lab tone on %.4f GHz" % (freq / 1e9))
        except Exception as e:
            print("[radio] TRANSMITTER DID NOT MOVE to %.4f GHz: %s" % (freq / 1e9, e))
