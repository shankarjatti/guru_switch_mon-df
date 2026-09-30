#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Blocks that follow twinrx_radio_source's sample-exact hop marks.

twinrx_radio_source stamps its first output stream with two tags, placed on
the exact samples computed from the radio clock:

  hop_off  (value: next band's frequency in Hz, or -1)
      from here the samples belong to a switch -- the guard before it and the
      settle after it -- and are not a measurement
  hop_on   (value: band frequency in Hz)
      from here until the next hop_off the samples are a dwell on that band

A slot that could not be scheduled safely, or whose LO lock was not
confirmed, gets no hop_on: it stays "off" and nothing downstream uses it.

Blocks here:
  hop_band_select   passes only the dwell samples of one chosen band
  hop_phase_meter   measures chN - ch0 per dwell window of one chosen band,
                    only where a tone is really present on every channel
"""
import math
import threading
import time

import numpy as np
import pmt
from gnuradio import gr

# Python blocks work on at least this many samples per call. Each call takes
# the GIL, and the radio scheduler thread needs it too; fewer, larger calls
# leave it more room. 4096 samples = 4 ms at 1 Msps.
CHUNK = 4096

TAG_OFF = "hop_off"
TAG_ON = "hop_on"
_K_OFF = pmt.intern(TAG_OFF)
_K_ON = pmt.intern(TAG_ON)


def hop_events(block, port, n):
    """(relative index, frequency or None) for hop tags in the next n items."""
    base = block.nitems_read(port)
    ev = []
    for t in block.get_tags_in_window(port, 0, n):
        if pmt.eq(t.key, _K_ON):
            ev.append((t.offset - base, float(pmt.to_double(t.value))))
        elif pmt.eq(t.key, _K_OFF):
            ev.append((t.offset - base, None))
    ev.sort(key=lambda e: e[0])
    # tags can arrive duplicated through multi-input blocks; keep one per offset
    out = []
    for e in ev:
        if out and out[-1][0] == e[0]:
            out[-1] = e
        else:
            out.append(e)
    return out


def segments(state, events, n):
    """Split [0, n) into (start, stop, band-or-None) runs; returns runs, new state."""
    runs = []
    pos = 0
    for idx, band in events:
        if idx > pos:
            runs.append((pos, idx, state))
        state = band
        pos = max(pos, idx)
    if pos < n:
        runs.append((pos, n, state))
    return runs, state


def same_band(a, b, tol=1e6):
    return a is not None and b is not None and abs(a - b) <= tol


def narrow_band(x, half_hz, fs):
    """Keep only +/- half_hz around the tone of one dwell window, all channels.

    x: [nch, L]. The tone is found on the sum of the channels' spectra and the
    SAME filter (flat to half_hz, cosine taper to 2 * half_hz) is applied to
    every channel, so the phase between channels is untouched. Zero-phase
    (FFT of the whole window), so nothing is delayed; the first and last
    ~1/half_hz of the window settle (the window is not a whole number of
    cycles). For display only -- measurements use the unfiltered samples.
    """
    L = x.shape[1]
    X = np.fft.fft(x, axis=1)
    F = np.fft.fftfreq(L, 1.0 / fs)
    k = int(np.argmax(np.sum(np.abs(X) ** 2, axis=0)))
    d = np.abs(F - F[k])
    H = np.where(d <= half_hz, 1.0,
                 np.where(d <= 2 * half_hz, 0.5 * (1 + np.cos(np.pi * (d - half_hz) / half_hz)), 0.0))
    return np.fft.ifft(X * H[None, :], axis=1).astype(np.complex64)


class hop_band_select(gr.basic_block):
    """Pass only the dwell samples of one band; drop switching and other bands.

    frame_tag: if set, a tag with this key is put frame_offset samples after
    the start of every dwell window in the output. A time plot triggered on it
    always draws from inside one window, never across the join between two
    windows (the output is windows placed end to end).

    remove_dc: hold each whole window, subtract its measured mean per channel
    (the receiver's own 0 Hz leakage), then pass it on -- one window later.
    For a tone close to 0 Hz, where no filter can separate the two inside a
    short dwell. The same operation the phase meter does with remove_dc.
    """

    def __init__(self, num_channels=4, band_freq=2.4e9, frame_tag="", frame_offset=100,
                 remove_dc=False, narrow_hz=0.0, samp_rate=1e6):
        gr.basic_block.__init__(self, name="Hop Band Select",
                                in_sig=[np.complex64] * num_channels,
                                out_sig=[np.complex64] * num_channels)
        self.set_tag_propagation_policy(gr.TPP_DONT)
        self.nch = int(num_channels)
        self.band_freq = float(band_freq)
        self._state = None
        self._frame_key = pmt.intern(frame_tag) if frame_tag else None
        self.frame_offset = int(frame_offset)
        self._active = False          # last output sample was inside a window
        self._pending = None          # samples left until this window's frame tag
        self.remove_dc = bool(remove_dc) or float(narrow_hz) > 0
        self.narrow_hz = float(narrow_hz)
        self.fs = float(samp_rate)
        self._buf = None              # remove_dc: chunks of the window being collected
        self._ready = []              # remove_dc: finished windows [nch, L], oldest first
        self._rpos = 0                # remove_dc: samples of _ready[0] already sent
        self.set_output_multiple(CHUNK)

    def set_band_freq(self, band_freq):
        self.band_freq = float(band_freq)

    def get_band_freq(self):
        return self.band_freq

    def forecast(self, noutput_items, ninput_items_required):
        for i in range(len(ninput_items_required)):
            ninput_items_required[i] = noutput_items

    def _dc_work(self, input_items, output_items, n):
        runs, self._state = segments(self._state, hop_events(self, 0, n), n)
        for a, b, band in runs:
            if not same_band(band, self.band_freq):
                if self._buf:
                    x = np.concatenate(self._buf, axis=1)
                    x = x - x.mean(axis=1, keepdims=True)
                    if self.narrow_hz > 0 and x.shape[1] >= 64:
                        x = narrow_band(x, self.narrow_hz, self.fs)
                    self._ready.append(x)
                self._buf = None
                continue
            if self._buf is None:
                self._buf = []
            self._buf.append(np.array([input_items[c][a:b] for c in range(self.nch)]))
        self.consume_each(n)
        # send finished windows, each with its frame tag
        m, room = 0, len(output_items[0])
        w0 = self.nitems_written(0)
        while self._ready and m < room:
            x = self._ready[0]
            k = min(room - m, x.shape[1] - self._rpos)
            if self._frame_key is not None and self._rpos <= self.frame_offset < self._rpos + k:
                self.add_item_tag(0, w0 + m + self.frame_offset - self._rpos, self._frame_key,
                                  pmt.PMT_T)
            for c in range(self.nch):
                output_items[c][m:m + k] = x[c, self._rpos:self._rpos + k]
            m += k
            self._rpos += k
            if self._rpos >= x.shape[1]:
                self._ready.pop(0)
                self._rpos = 0
        # a display that falls behind skips whole windows (never a part of one)
        if len(self._ready) > 8:
            keep = 1 if self._rpos else 0
            self._ready[keep:len(self._ready) - 7] = []
        return m

    def general_work(self, input_items, output_items):
        n = min(min(len(x) for x in input_items), len(output_items[0]))
        if n <= 0:
            return 0
        if self.remove_dc:
            return self._dc_work(input_items, output_items, n)
        runs, self._state = segments(self._state, hop_events(self, 0, n), n)
        m = 0
        w0 = self.nitems_written(0)
        for a, b, band in runs:
            if not same_band(band, self.band_freq):
                self._active = False
                self._pending = None
                continue
            k = b - a
            if not self._active:
                self._active = True
                self._pending = self.frame_offset
            if self._frame_key is not None and self._pending is not None and self._pending < k:
                self.add_item_tag(0, w0 + m + self._pending, self._frame_key, pmt.PMT_T)
                self._pending = None
            elif self._pending is not None:
                self._pending -= k
            for c in range(self.nch):
                output_items[c][m:m + k] = input_items[c][a:b]
            m += k
        self.consume_each(n)
        return m


class hop_dc_remove(gr.sync_block):
    """Subtract each dwell window's measured mean, on the continuous timeline.

    The receiver's own 0 Hz leakage is only 13-16 dB below the tone in every
    dwell (measured 2026-09-29), so with a tone close to 0 Hz the two beat and
    the tone's amplitude ripples. No filter can split them inside a 5 ms
    dwell; subtracting the dwell's own mean does, exactly. The mean is only
    known once the window is over, so the whole stream is delayed by `delay`
    samples (at least the longest dwell): every output sample then belongs to
    a window that has been seen completely. Switching samples pass unchanged,
    and every tag comes out on the same sample it was on, `delay` later.
    """

    def __init__(self, num_channels=4, delay=5000, narrow_hz=0.0, samp_rate=1e6):
        gr.sync_block.__init__(self, name="Hop DC Remove",
                               in_sig=[np.complex64] * num_channels,
                               out_sig=[np.complex64] * num_channels)
        self.set_tag_propagation_policy(gr.TPP_DONT)
        self.nch = int(num_channels)
        self.D = int(delay)
        self._hist = np.zeros((self.nch, self.D), dtype=np.complex64)
        self._state = None
        self._open = None             # start (input index) of the window being seen
        self._done = []               # (start, stop, processed samples [nch, L])
        self.too_long = 0             # windows longer than the delay (left as they are)
        self.narrow_hz = float(narrow_hz)
        self.fs = float(samp_rate)

    def work(self, input_items, output_items):
        n = len(output_items[0])
        i0 = self.nitems_read(0)
        x = np.array([input_items[c][:n] for c in range(self.nch)])
        full = np.concatenate([self._hist, x], axis=1)
        fbase = i0 - self.D                # input index of full[:, 0] (= output sample 0)
        runs, self._state = segments(self._state, hop_events(self, 0, n), n)
        for a, b, band in runs:
            if band is None:
                if self._open is not None:
                    s0, e0 = self._open, i0 + a
                    if e0 - s0 > self.D or s0 < fbase:
                        self.too_long += 1
                    elif e0 > s0:
                        w = full[:, s0 - fbase:e0 - fbase]
                        w = w - w.mean(axis=1, keepdims=True)
                        if self.narrow_hz > 0 and w.shape[1] >= 64:
                            w = narrow_band(w, self.narrow_hz, self.fs)
                        self._done.append((s0, e0, w))
                    self._open = None
                continue
            if self._open is None:
                self._open = i0 + a
        # output = input delayed by D; inside a window its processed samples
        y = full[:, :n].copy()
        for s0, e0, w in self._done:
            lo, hi = max(s0, fbase), min(e0, fbase + n)
            if lo < hi:
                y[:, lo - fbase:hi - fbase] = w[:, lo - s0:hi - s0]
        self._done = [d for d in self._done if d[1] > fbase + n]
        self._hist = full[:, n:]
        for c in range(self.nch):
            output_items[c][:n] = y[c]
            for t in self.get_tags_in_window(c, 0, n):
                self.add_item_tag(c, t.offset + self.D, t.key, t.value)
        return n


class hop_phase_meter(gr.basic_block):
    """Per-window chN - ch0 phase of one band, gated on a real tone.

    For every completed dwell window of the chosen band it checks, per
    channel, that a tone stands at least snr_min_db above the in-band noise
    floor (FFT over the window, peak vs median inside [f_lo, f_hi]). Only then
    does the window count. Output port c gives, once per window of the chosen
    band, the circular mean of chc - ch0 over the last avg_windows valid
    windows in degrees (port 0 is always 0), or NaN if there are none -- a
    readout never shows a number that was not measured on a real tone.

    Every report_s seconds it prints, for each band seen, how many windows
    there were, how many had a tone, the mean phase and the spread.

    For every window it also records what it measured -- its length in
    samples, the tone's frequency (FFT peak, interpolated) and so how many
    tone cycles the window held -- in last_window, for a dwell check on screen.

    remove_dc: subtract each window's mean per channel first, so the
    receiver's own 0 Hz leakage (steady and coherent, so it would pass for a
    phase) never enters the measurement -- needed when the tone sits close to
    0 Hz. dc_guard: ignore |f| below this when looking for the tone.
    """

    def __init__(self, num_channels=4, band_freq=2.4e9, samp_rate=1e6,
                 f_lo=60e3, f_hi=340e3, snr_min_db=20.0, avg_windows=10,
                 report_s=5.0, remove_dc=False, dc_guard=0.0):
        gr.basic_block.__init__(self, name="Hop Phase Meter",
                                in_sig=[np.complex64] * num_channels,
                                out_sig=[np.float32] * num_channels)
        self.set_tag_propagation_policy(gr.TPP_DONT)
        self.nch = int(num_channels)
        self.band_freq = float(band_freq)
        self.fs = float(samp_rate)
        self.f_lo, self.f_hi = float(f_lo), float(f_hi)
        self.snr_min_db = float(snr_min_db)
        self.avg_windows = int(avg_windows)
        self.report_s = float(report_s)
        self._state = None
        self._win = None            # list of per-call chunks while ON
        self._win_band = None
        self._queue = []            # rows to emit for the chosen band
        self._hist = {}             # band -> list of phase vectors (valid windows)
        self._stats = {}            # band -> counters
        self._lock = threading.Lock()
        self._t_report = time.time()
        self._t_emit = time.time()
        self.last_row = None          # last value put out (None before the first)
        self.remove_dc = bool(remove_dc)
        self.dc_guard = float(dc_guard)
        self.last_window = None       # {band, samples, tone_hz, cycles, snr_db, tone, dc_db, t}
        self.last_windows = {}        # band -> the same, per band
        self._freq_hist = {}          # band -> [(tone_hz, samples)] of windows with a tone
        self._recent_len = {}         # band -> sample counts of its last 200 windows

    def set_band_freq(self, band_freq):
        with self._lock:
            self.band_freq = float(band_freq)
            self._queue = []

    def get_stats(self):
        with self._lock:
            return {k: dict(v) for k, v in self._stats.items()}

    def recent(self, n=10):
        """Circular mean of chN - ch0 over the last n windows with a tone on
        this meter's band, or None if there are none."""
        with self._lock:
            h = []
            for k in self._hist:
                if same_band(k, self.band_freq):
                    h = list(self._hist[k][-int(n):])
        if not h:
            return None
        a = np.array(h)
        return np.degrees(np.angle(np.sum(np.exp(1j * np.radians(a)), axis=0))).tolist()

    def reset_band(self, band_freq):
        """Forget one band's history and counters (start of a calibration)."""
        with self._lock:
            for k in list(self._hist):
                if same_band(k, band_freq):
                    self._hist[k] = []
            for k in list(self._stats):
                if same_band(k, band_freq):
                    self._stats[k] = {"windows": 0, "tone": 0, "samples": 0}

    def band_summary(self, band_freq):
        """Windows seen, windows with a tone, and mean / std / max deviation
        (degrees, per channel pair) of chN - ch0 since the last reset_band."""
        with self._lock:
            h = []
            st = {"windows": 0, "tone": 0}
            for k in self._hist:
                if same_band(k, band_freq):
                    h = list(self._hist[k])
            for k in self._stats:
                if same_band(k, band_freq):
                    st = dict(self._stats[k])
        out = {"windows": st.get("windows", 0), "tone": st.get("tone", 0), "n": len(h)}
        if h:
            a = np.array(h)
            m = np.degrees(np.angle(np.sum(np.exp(1j * np.radians(a)), axis=0)))
            d = (a - m[None] + 180.0) % 360.0 - 180.0
            out.update(mean=m.tolist(), std=d.std(axis=0).tolist(),
                       max_dev=np.abs(d).max(axis=0).tolist())
        return out

    def forecast(self, noutput_items, ninput_items_required):
        for i in range(len(ninput_items_required)):
            ninput_items_required[i] = CHUNK

    def _finish_window(self):
        chunks, band = self._win, self._win_band
        self._win, self._win_band = None, None
        if not chunks:
            return
        x = np.concatenate(chunks, axis=1)
        L = x.shape[1]
        st = self._stats.setdefault(band, {"windows": 0, "tone": 0, "samples": 0})
        st["windows"] += 1
        st["samples"] += L
        nan_row = [0.0] + [float("nan")] * (self.nch - 1)
        if L < 256:
            if same_band(band, self.band_freq):
                self._queue.append(nan_row)
            return
        # 0 Hz level vs the whole window, worst channel (dB): what remove_dc removes
        mean = x.mean(axis=1, keepdims=True)
        dc_db = float(np.max(20 * np.log10(np.abs(mean[:, 0]) /
                                           (np.sqrt(np.mean(np.abs(x) ** 2, axis=1)) + 1e-30) + 1e-30)))
        if self.remove_dc:
            x = x - mean
        w = np.hanning(L).astype(np.float32)
        F = np.fft.fftfreq(L, 1.0 / self.fs)
        inband = (F >= self.f_lo) & (F <= self.f_hi)
        # The tone is the STRONGEST line of the whole band (all channels summed),
        # found without the 0 Hz guard. If that line lies inside the guard it is
        # too close to 0 Hz to measure: the window has no tone -- a weaker line
        # (e.g. the transmitter's carrier leak, ~40 dB down) is never taken instead.
        Xc = [np.fft.fft(x[c] * w) for c in range(self.nch)]
        Sc = [np.abs(X) ** 2 for X in Xc]
        S0 = Sc[0]
        Ssum = np.sum(Sc, axis=0)
        res = self.fs / L
        whole = inband & (np.abs(F) > 3 * res)
        if not np.any(whole):
            if same_band(band, self.band_freq):
                self._queue.append(nan_row)
            return
        idx_all = np.flatnonzero(whole)
        k = int(idx_all[np.argmax(Ssum[idx_all])])
        near_dc = self.dc_guard > 0 and abs(F[k]) < self.dc_guard
        if self.dc_guard > 0:
            inband &= np.abs(F) >= self.dc_guard
        # SNR of THAT line on every channel, against the band's noise floor
        snr = [10 * np.log10(Sc[c][k] / (np.median(Sc[c][inband]) + 1e-30) + 1e-30)
               for c in range(self.nch)]
        if near_dc:
            snr = [-99.0] * self.nch
        # frequency: the peak bin refined by a parabola through the log power of
        # it and its neighbours (Hann window), on the channel sum
        a, b, c3 = (np.log(Ssum[(k + d) % L] + 1e-30) for d in (-1, 0, 1))
        den = a - 2 * b + c3
        dk = 0.5 * (a - c3) / den if den != 0 else 0.0
        f_tone = float((F[k] + dk * self.fs / L))
        # cycles COUNTED on the signal itself: its rotation summed sample by
        # sample over the whole window (strongest channel). Each step is far
        # below half a turn, so nothing can be missed or double counted; noise
        # only moves the first and last sample (a few hundredths of a cycle).
        cs = int(np.argmax(np.mean(np.abs(x) ** 2, axis=1)))
        turns = float(np.sum(np.angle(x[cs, 1:] * np.conj(x[cs, :-1]))) / (2 * np.pi))
        rl = self._recent_len.setdefault(band, [])
        rl.append(int(L))
        if len(rl) > 200:
            del rl[:-200]
        self.last_window = {"band": band, "samples": int(L), "tone_hz": f_tone,
                            "cycles": f_tone * L / self.fs, "cycles_counted": turns,
                            "dwell_no": int(st["windows"]), "len_min": min(rl), "len_max": max(rl),
                            "count_ch": cs, "snr_db": float(min(snr)),
                            "tone": bool(min(snr) >= self.snr_min_db), "dc_db": dc_db,
                            "near_dc": bool(near_dc),
                            "t": time.time()}
        self.last_windows[band] = self.last_window
        if self.last_window["tone"]:
            fh = self._freq_hist.setdefault(band, [])
            fh.append((f_tone, int(L)))
            if len(fh) > 5000:
                del fh[:-5000]
        st["min_snr_db"] = float(min(min(snr), st.get("min_snr_db", 1e9)))
        if min(snr) < self.snr_min_db:
            if same_band(band, self.band_freq):
                self._queue.append(nan_row)
            return
        st["tone"] += 1
        # the phase AT THE TONE: cross-spectrum over the tone's own bins (its Hann
        # main lobe, +/-2 bins). Anything else in the band -- over the air e.g. a
        # Wi-Fi burst arriving from another direction -- no longer enters it.
        # (A correlation over the whole band mixed such bursts in: over the air
        # at 5.2 GHz 19-44 deg spread vs < 1 deg at the tone bin, 2026-09-29.)
        jj = [(k + d) % L for d in (-2, -1, 0, 1, 2)]
        C = np.array([np.sum(Xc[c][jj] * np.conj(Xc[0][jj])) for c in range(1, self.nch)])
        ph = np.degrees(np.angle(C))
        h = self._hist.setdefault(band, [])
        h.append(ph)
        if len(h) > 1000:
            del h[:-1000]
        if same_band(band, self.band_freq):
            last = np.array(h[-self.avg_windows:])
            m = np.degrees(np.angle(np.sum(np.exp(1j * np.radians(last)), axis=0)))
            self._queue.append([0.0] + list(m))

    def _report(self):
        now = time.time()
        if now - self._t_report < self.report_s:
            return
        self._t_report = now
        for band in sorted(self._stats):
            if not same_band(band, self.band_freq):
                continue            # each meter reports its own band (was: every meter every band, 3x)
            st = self._stats[band]
            h = np.array(self._hist.get(band, [])[-200:])
            if len(h):
                m = np.degrees(np.angle(np.sum(np.exp(1j * np.radians(h)), axis=0)))
                dev = np.max(np.abs((h - m + 180.0) % 360.0 - 180.0), axis=0)
                ph = "  ".join("ch%d %+7.2f (max dev %.2f)" % (c + 1, m[c], dev[c])
                               for c in range(len(m)))
            else:
                ph = "no tone"
            lw = self.last_windows.get(band)
            tone = ("tone %+.1f Hz %d samples | " % (lw["tone_hz"], lw["samples"])
                    if lw is not None and lw["tone"] else "")
            print("[meter] %s %.4f GHz  windows %d  with tone %d  worst SNR %.1f dB | %s%s"
                  % (time.strftime("%H:%M:%S"), band / 1e9, st["windows"], st["tone"],
                     st.get("min_snr_db", float("nan")), tone, ph))

    def general_work(self, input_items, output_items):
        n = min(len(x) for x in input_items)
        with self._lock:
            if n > 0:
                runs, self._state = segments(self._state, hop_events(self, 0, n), n)
                for a, b, band in runs:
                    # only this meter's band: collecting (and FFT-ing) every
                    # band's dwells in every meter cost ~2/3 of their CPU for
                    # nothing (2 MS/s run 2026-09-29: flowgraph fell behind)
                    if band is None or not same_band(band, self.band_freq):
                        if self._win is not None:
                            self._finish_window()
                        continue
                    if self._win is not None and not same_band(band, self._win_band):
                        self._finish_window()
                    if self._win is None:
                        self._win, self._win_band = [], band
                    self._win.append(np.array([input_items[c][a:b] for c in range(self.nch)]))
                self.consume_each(n)
            self._report()
            if not self._queue and time.time() - self._t_emit > 0.5:
                # nothing measured on the chosen band for 0.5 s: say so
                self._queue.append([0.0] + [float("nan")] * (self.nch - 1))
            k = min(len(self._queue), len(output_items[0]))
            if k:
                self._t_emit = time.time()
                self.last_row = list(self._queue[k - 1])
            for i in range(k):
                row = self._queue[i]
                for c in range(self.nch):
                    output_items[c][i] = row[c]
            del self._queue[:k]
        return k


class hop_tag_rotator(gr.sync_block):
    """Per-band phase correction switched on the hop tags, sample-exact.

    Channel 0 passes through, channel c is multiplied by exp(-j*offset_c) of
    the band named by the most recent hop_on. Between a hop_off and the next
    hop_on every output is zero: those samples are a switch, not a signal.
    table: [(freq_hz, [rad_ch1, rad_ch2, ...]), ...]
    """

    def __init__(self, num_channels, table, freq_tol=1e6):
        gr.sync_block.__init__(self, name="Hop Tag Rotator",
                               in_sig=[np.complex64] * num_channels,
                               out_sig=[np.complex64] * num_channels)
        self.nch = int(num_channels)
        self.freq_tol = float(freq_tol)
        self._state = None
        self._lock = threading.Lock()
        self._unknown = set()
        self.set_table(table)
        self.set_output_multiple(CHUNK)

    def set_table(self, table):
        with self._lock:
            self._table = [(float(f), np.exp(-1j * np.asarray(r, dtype=np.float64)).astype(np.complex64))
                           for f, r in table]

    def _rot(self, band):
        for f, rot in self._table:
            if abs(f - band) <= self.freq_tol:
                return rot
        if band not in self._unknown:
            self._unknown.add(band)
            print("[phasecal] NO ROW FOR %.4f GHz -- its dwell samples are passed "
                  "UNCORRECTED" % (band / 1e9))
        return None

    def work(self, input_items, output_items):
        n = len(output_items[0])
        with self._lock:
            runs, self._state = segments(self._state, hop_events(self, 0, n), n)
            for a, b, band in runs:
                if band is None:
                    for c in range(self.nch):
                        output_items[c][a:b] = 0
                    continue
                rot = self._rot(band)
                output_items[0][a:b] = input_items[0][a:b]
                for c in range(1, self.nch):
                    if rot is None:
                        output_items[c][a:b] = input_items[c][a:b]
                    else:
                        output_items[c][a:b] = input_items[c][a:b] * rot[c - 1]
        return n

