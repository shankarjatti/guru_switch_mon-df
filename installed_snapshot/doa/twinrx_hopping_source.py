#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# TwinRX USRP source with built-in centre-frequency hopping.
#
# This is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

"""TwinRX USRP source that cycles through a list of bands on its own.

Everything about the radio is the same as twinrx_usrp_source -- subdev map,
antenna selection, LO routing and export, the timed double tune and the
low-side LO fallback are all inherited from it, so the two blocks cannot drift
apart.  What this one adds:

  * a list of bands, each with its own centre frequency, RX gain and dwell
  * one settling time applied after every switch, during which the outputs
    are muted so the display does not draw the transition as if it were data
  * a background thread that walks the list and repeats
  * an optional UDP command to the calibration transmitter, sent before each
    tune so the tone is already in place when the receiver arrives
  * wire and host sample formats, which the original hard-codes to fc32

It deliberately does NOT modify twinrx_usrp_source.  Its own __init__ replaces
the parent's (gr.hier_block2.__init__ is called directly) so that the stream
arguments can carry cpu_format/otw_format, but every method the parent defines
is reused as-is.  The attributes those methods rely on -- uhd_usrp_source_0,
sources, gain, samp_rate, center_freq, lo_export_direction -- are all set here.

Per-band gain is worth a warning: inter-channel phase offsets shift with RX
gain on this hardware, so a phase calibration is valid for a (band, gain) pair
rather than for a band alone.  Keep each band's gain fixed once calibrated.
"""

import os
import socket
import threading
import time

import numpy as np

from gnuradio import blocks
from gnuradio import gr
from gnuradio import uhd

from .twinrx_usrp_source import twinrx_usrp_source, gen_sig_io


# cpu_format -> bytes per item, for the output signature
_CPU_ITEMSIZE = {
    "fc32": gr.sizeof_gr_complex,     # complex float32, what the rest of the
                                      # flowgraph expects
    "sc16": gr.sizeof_short * 2,      # complex int16
    "item32": gr.sizeof_int,          # raw VITA words
}


class _Lifecycle(gr.sync_block):
    """Stops the hop thread when the flowgraph stops.

    The scheduler calls stop() on every block during top_block.stop(), which
    is the only hook a hier_block2 gets at the right moment. A GRC
    "main after stop" snippet runs after tb.stop() has already returned, so
    by then the thread has spent the whole teardown tuning a device that was
    being destroyed -- which is what leaves the X310's control plane wedged.
    """

    def __init__(self, owner):
        gr.sync_block.__init__(self, name="hop lifecycle",
                               in_sig=[np.complex64], out_sig=None)
        self._owner = owner

    def work(self, input_items, output_items):
        return len(input_items[0])          # consume and discard

    def stop(self):
        try:
            self._owner.stop_hopping()
        except Exception as e:
            # Never swallow this. A hop thread still running during teardown
            # keeps issuing timed commands at a device being destroyed, which
            # is exactly what leaves the X310's control plane wedged and needing
            # a power cycle. If it failed, the next start may fail too, and the
            # reason has to be visible.
            print("[hop] COULD NOT STOP THE HOP THREAD: %s: %s\n"
                  "      The X310 may need a power cycle before the next run."
                  % (type(e).__name__, e))
        return True


def _sig_io(num_elements, itemsize):
    io = [itemsize] * num_elements
    io.append(gr.sizeof_float * num_elements)
    return io


class twinrx_hopping_source(twinrx_usrp_source):
    """TwinRX source that hops through a list of bands by itself."""

    def __init__(self, samp_rate=1000000, sources=4,
                 addresses="type=x300", lo_export_direction="B",
                 cpu_format="fc32", otw_format="",
                 bands=((2.4e9, 60.0, 10.0),),
                 settle=2.0, hop_enable=True, start_delay=2.0,
                 tx_control="", blank_during_settle=True,
                 lo_lock_fallback=False, gain_trim=(0.0, 0.0, 0.0, 0.0),
                 recv_buff_size=33554432, stream_timeout=3.0,
                 cmd_time_margin=0.1):
        if cpu_format not in _CPU_ITEMSIZE:
            raise ValueError("twinrx_hopping_source: unknown cpu_format %r "
                             "(expected one of %s)"
                             % (cpu_format, ", ".join(sorted(_CPU_ITEMSIZE))))
        itemsize = _CPU_ITEMSIZE[cpu_format]
        gr.hier_block2.__init__(
            self, "TwinRX Hopping USRP",
            gr.io_signature(0, 0, 0),
            gr.io_signaturev(sources, sources, _sig_io(sources, itemsize)),
        )

        self.bands = [tuple(b) for b in bands if b]
        if not self.bands:
            raise ValueError("twinrx_hopping_source: no bands given")
        self.settle = float(settle)
        self.hop_enable = bool(hop_enable)
        self.start_delay = float(start_delay)
        self.tx_control = tx_control or ""
        # Muting needs complex samples; the other formats pass straight through.
        self.blank_during_settle = bool(blank_during_settle) and cpu_format == "fc32"
        self._gate = []
        self._chain_head = []
        self._conj_q = []
        self._tx_failures = 0
        self._gain_range_warned = False

        # The radio can stop sending without anything in the flowgraph
        # noticing: the plot goes flat and the phase readouts freeze on their
        # last value, which reads as a measurement rather than as the absence
        # of one. These drive the watchdog that catches that; see
        # _stream_watchdog.
        self.stream_timeout = float(stream_timeout)
        self.recv_buff_size = int(recv_buff_size)
        self._watch_run = False
        self._watch_thread = None
        self._watch_iface = None
        self._stream_stalls = 0
        self._stream_restarts = 0
        self._stream_dead = False
        self._radio_lock = threading.Lock()

        # Attributes the inherited methods expect.
        self.samp_rate = samp_rate
        self.sources = sources
        self.addresses = addresses
        self.lo_export_direction = lo_export_direction
        self.lo_lock_fallback = bool(lo_lock_fallback)
        # Inherited set_center_freq reads this. It is the deadline the timed
        # tune is stamped with; a write that misses it is never acknowledged,
        # and one unacknowledged write permanently breaks the block's control
        # interface. See twinrx_usrp_source.set_center_freq.
        self.cmd_time_margin = float(cmd_time_margin)
        # Per-channel dB added to the band gain. The four RF paths are not
        # equally sensitive here -- one channel runs about 13 dB hot -- so a
        # single gain either clips that one or buries the others. This trims
        # them at the radio rather than rescaling the picture afterwards.
        self.gain_trim = [float(g) for g in gain_trim][:4]
        while len(self.gain_trim) < 4:
            self.gain_trim.append(0.0)
        self.cpu_format = cpu_format
        self.otw_format = otw_format
        self.center_freq = self.bands[0][0]
        self.gain = self.bands[0][1]

        self._hop_run = False
        self._hop_thread = None
        self._band_index = -1
        self._lock_failures = 0
        self._tune_failures = 0
        # Not settled until the first hop has finished its settle window. The
        # constructor tunes, but the transmitter and the LO need a moment, and
        # showing that stretch would be showing the transition as data.
        self._settled = False

        ##################################################
        # Radio -- same setup as twinrx_usrp_source
        ##################################################
        _stream_kwargs = dict(cpu_format=cpu_format,
                              channels=list(range(sources)))
        if otw_format:
            _stream_kwargs["otw_format"] = otw_format
        # A bigger socket buffer to ride out host-side hiccups. The radio
        # stops sending when its FIFO overruns, and a frozen GUI back-pressures
        # the flowgraph all the way to the source, so a second of stalled
        # drawing is enough to kill the stream. This buys roughly
        # recv_buff_size / (samp_rate * channels * 4) seconds of slack -- about
        # two seconds at 4 x 1 Msps. It makes the failure rarer, not
        # impossible, which is what the watchdog is for.
        _args = [self.addresses]
        if self.recv_buff_size > 0:
            _args.append("recv_buff_size=%d" % self.recv_buff_size)
        self.uhd_usrp_source_0 = uhd.usrp_source(
            ",".join(_args + [""]),
            uhd.stream_args(**_stream_kwargs),
        )

        self.uhd_usrp_source_0.set_clock_source('internal', 0)
        subdevs = 'A:0 A:1 B:0 B:1'.split(' ')
        self.uhd_usrp_source_0.set_subdev_spec(' '.join(subdevs[:sources]), 0)
        self.uhd_usrp_source_0.set_samp_rate(samp_rate)
        self.uhd_usrp_source_0.set_time_unknown_pps(uhd.time_spec())

        # A:0 -> RX1, A:1 -> RX2, B:0 -> RX1, B:1 -> RX2. A channel left on the
        # wrong port reads about 70x down and looks like a dead channel.
        for _ch in range(sources):
            self.uhd_usrp_source_0.set_antenna('RX1' if _ch % 2 == 0 else 'RX2', _ch)
        for _ch in range(sources):
            self.uhd_usrp_source_0.set_gain(self.gain, _ch)
            self.uhd_usrp_source_0.set_auto_dc_offset(True, _ch)

        # LO routing, identical to the parent. Exports are cleared first
        # because UHD refuses a state where two channels export at once.
        if sources == 4:
            for _ch in range(sources):
                try:
                    self.uhd_usrp_source_0.set_lo_export_enabled(False, uhd.ALL_LOS, _ch)
                except Exception as e:
                    # Not fatal -- a channel that never exported will refuse --
                    # but say so rather than hiding it.
                    print("[twinrx] clearing LO export on ch%d: %s" % (_ch, e))
            if self.lo_export_direction.upper() == 'A':
                _src = ['internal', 'companion', 'external', 'external']
                _exp = 0
            else:
                _src = ['external', 'external', 'internal', 'companion']
                _exp = 2
            for _ch in range(sources):
                self.uhd_usrp_source_0.set_lo_source(_src[_ch], uhd.ALL_LOS, _ch)
            self.uhd_usrp_source_0.set_lo_export_enabled(True, uhd.ALL_LOS, _exp)
        else:
            self.uhd_usrp_source_0.set_lo_export_enabled(True, uhd.ALL_LOS, 0)
            self.uhd_usrp_source_0.set_lo_source('internal', uhd.ALL_LOS, 0)
            self.uhd_usrp_source_0.set_lo_source('companion', uhd.ALL_LOS, 1)

        # Fail here rather than per hop. Without a transmitter every band is
        # measured with no tone, and the run only says so once it is under way.
        if self.tx_control and not self._transmitter_answers():
            raise RuntimeError(
                "twinrx_hopping_source: nothing is answering at %s.\n"
                "  The calibration transmitter must be running BEFORE the\n"
                "  receiver: the receiver commands it on every hop, so without\n"
                "  it no band has a tone and nothing measured here is valid.\n"
                "  Start it with:\n"
                "    gr310 python3 ~/radar2/hackrf_tone_source.py --radio b210 \\\n"
                "        --vga 55 --rate 1e6 --control %s\n"
                "  Or set tx_control to '' to drive the transmitter yourself."
                % (self.tx_control, self.tx_control))

        # Put the transmitter on the first band BEFORE tuning to it. Without
        # this the receiver starts on band 0 while the transmitter is still
        # parked wherever the last run left it, and the opening seconds show
        # an empty band until the hop thread's first iteration corrects it.
        self._retune_transmitter(self.center_freq)

        # Inherited: timed double tune, then the low-side LO lock fallback.
        self.set_center_freq(self.center_freq, sources)

        # Undo the mirroring the LO fallback causes, so every band lands at
        # centre + the same baseband offset and the transmitter never has to
        # treat one band differently. Conjugation cannot be switched on a
        # conjugate block, so it is done as multiply the Q path by -1: the
        # constant is a runtime callback.
        self._conj_q = []
        if cpu_format == "fc32":
            for source in range(sources):
                re = blocks.complex_to_real(1)
                im = blocks.complex_to_imag(1)
                sign = blocks.multiply_const_ff(1.0)
                f2c = blocks.float_to_complex(1)
                self.connect((self.uhd_usrp_source_0, source), re, (f2c, 0))
                self.connect((self.uhd_usrp_source_0, source), im, sign, (f2c, 1))
                self._conj_q.append(sign)
                self._chain_head.append(f2c)
        else:
            for source in range(sources):
                self._chain_head.append((self.uhd_usrp_source_0, source))

        if self.blank_during_settle:
            # A gate per channel, held at zero while the radio settles after a
            # hop. Without it the plot draws the transition -- half-tuned LO,
            # gain still moving -- as if it were data. Muting rather than
            # gating the stream on purpose: a block that stops producing would
            # stall the flowgraph through back-pressure, so this outputs zeros
            # and keeps the sample clock honest.
            for source in range(sources):
                g = blocks.multiply_const_cc(0.0)
                self._gate.append(g)
                self.connect(self._chain_head[source], g, (self, source))
        else:
            for source in range(sources):
                self.connect(self._chain_head[source], (self, source))

        self._apply_conjugate()

        # Gives the hop thread a shutdown hook the scheduler actually calls
        # while the flowgraph is still alive.
        if cpu_format == "fc32":
            self._lifecycle = _Lifecycle(self)
            self.connect(self._chain_head[0], self._lifecycle)

        self._start_hopping()
        self._start_watchdog()

    def _set_gate(self, open_):
        for g in self._gate:
            g.set_k(1.0 if open_ else 0.0)

    def is_settled(self):
        """False from the start of a hop until the settle window ends.

        Reports the schedule, not what this block does with it: callers gate
        their own display path on this, so it has to be meaningful whether or
        not blank_during_settle is muting here as well.
        """
        if self._stream_dead:
            return False
        if not self.hop_enable:
            return True
        return bool(self._settled)

    # ------------------------------------------------------------------
    # hopping
    # ------------------------------------------------------------------
    def _start_hopping(self):
        if not self.hop_enable or len(self.bands) < 1:
            print("[hop] disabled -- staying on %.4f GHz"
                  % (self.center_freq / 1e9))
            return
        total = sum(self.settle + b[2] for b in self.bands)
        print("[hop] %d band(s), %.1f s settle each, %.1f s per cycle"
              % (len(self.bands), self.settle, total))
        for i, (f, g, d) in enumerate(self.bands):
            print("        band %d: %8.4f GHz  gain %4.1f dB  dwell %5.1f s"
                  % (i, f / 1e9, g, d))
        self._hop_run = True
        # Daemon so it cannot keep the process alive if stop_hopping is never
        # called -- gr.hier_block2 gives no reliable stop hook to hang it on.
        self._hop_thread = threading.Thread(target=self._hopper, daemon=True)
        self._hop_thread.start()

    def stop_hopping(self):
        self._hop_run = False
        self._watch_run = False
        for t in (self._hop_thread, self._watch_thread):
            if t is not None and t.is_alive():
                t.join(timeout=2.0)

    # ------------------------------------------------------------------
    # stream watchdog
    # ------------------------------------------------------------------
    # A 4-channel run died after 21 minutes: the X310 stopped sending, the
    # host NIC went to zero with no errors, and the flowgraph carried on alive
    # with nothing to process. The plot went flat and the phase readouts held
    # their last value -- the worst failure mode there is, because a frozen
    # number looks exactly like a stable measurement.
    #
    # The signal used here is whether the radio is putting packets on the wire,
    # read from the kernel's own counter. That is deliberately not the
    # flowgraph's sample count: when a GUI sink stalls, back-pressure stops the
    # source too, and restarting the stream then would be the wrong answer to
    # the wrong question. Packets on the wire say what the radio is doing
    # regardless of what the host is doing with them.

    _IFACE_STATS = "/sys/class/net/%s/statistics/rx_bytes"

    def _expected_bytes_per_sec(self):
        """What the wire should be carrying. Over-the-wire is sc16: 4 B/sample."""
        return float(self.samp_rate) * self.sources * 4.0

    def _iface_bytes(self, iface):
        try:
            with open(self._IFACE_STATS % iface) as f:
                return int(f.read())
        except Exception:
            return None

    def _find_stream_iface(self, expect, settle=1.0):
        """Identify the interface the radio streams over, by measuring it.

        Nothing is assumed about the address or the interface name: whichever
        one is actually carrying most of the expected sample rate is the one.
        If none is, the watchdog says so and stays off rather than watching a
        counter that means nothing.
        """
        try:
            names = [n for n in os.listdir("/sys/class/net") if n != "lo"]
        except Exception:
            return None
        first = dict((n, self._iface_bytes(n)) for n in names)
        t0 = time.time()
        time.sleep(settle)
        dt = time.time() - t0
        best, best_rate = None, 0.0
        for n in names:
            a, b = first.get(n), self._iface_bytes(n)
            if a is None or b is None:
                continue
            rate = (b - a) / dt
            if rate > best_rate:
                best, best_rate = n, rate
        if best is not None and best_rate >= 0.5 * expect:
            print("[stream] watching %s -- carrying %.1f MB/s of an expected "
                  "%.1f" % (best, best_rate / 1e6, expect / 1e6))
            return best
        print("[stream] WATCHDOG OFF: no interface is carrying the expected "
              "%.1f MB/s (best was %s at %.2f). A stream that dies will not be "
              "caught, and the display will freeze on its last value."
              % (expect / 1e6, best, best_rate / 1e6))
        return None

    def _start_watchdog(self):
        if self.stream_timeout <= 0:
            print("[stream] watchdog disabled (stream_timeout=0)")
            return
        self._watch_run = True
        self._watch_thread = threading.Thread(target=self._stream_watchdog,
                                              daemon=True)
        self._watch_thread.start()

    def _restart_stream(self):
        """Re-issue the stream command, keeping the four channels aligned.

        The start has to be timed, not immediate. With one streamer over four
        channels an immediate start lets them begin on different samples, and
        a constant sample skew between channels is a constant phase error --
        it would come back looking healthy and read wrong. This is the same
        now-plus-a-moment start gr-uhd itself uses for multi-channel sources.
        """
        src = self.uhd_usrp_source_0
        stop = uhd.stream_cmd_t(uhd.stream_cmd_t.STREAM_MODE_STOP_CONTINUOUS)
        src.issue_stream_cmd(stop)
        time.sleep(0.1)
        start = uhd.stream_cmd_t(uhd.stream_cmd_t.STREAM_MODE_START_CONTINUOUS)
        if self.sources == 1:
            start.stream_now = True
        else:
            start.stream_now = False
            start.time_spec = src.get_time_now() + uhd.time_spec(0.1)
        src.issue_stream_cmd(start)

    def _stream_alive(self, iface, expect, window=1.0):
        a = self._iface_bytes(iface)
        t0 = time.time()
        time.sleep(window)
        b = self._iface_bytes(iface)
        if a is None or b is None:
            return None, 0.0
        rate = (b - a) / (time.time() - t0)
        return rate >= 0.10 * expect, rate

    def _stream_watchdog(self):
        expect = self._expected_bytes_per_sec()
        # Let the stream come up first, or the first measurement is of nothing.
        time.sleep(max(self.start_delay, 2.0) + 1.0)
        iface = self._find_stream_iface(expect)
        self._watch_iface = iface
        if iface is None:
            return

        period = 0.5
        quiet = 0.0
        last = self._iface_bytes(iface)
        while self._watch_run:
            time.sleep(period)
            now = self._iface_bytes(iface)
            if now is None:
                continue
            rate = (now - last) / period
            last = now
            if rate >= 0.10 * expect:
                if self._stream_dead:
                    print("[stream] receiving again -- %.1f MB/s" % (rate / 1e6))
                self._stream_dead = False
                quiet = 0.0
                continue

            quiet += period
            if quiet < self.stream_timeout:
                continue

            # The radio has stopped. Everything downstream is now stale, so say
            # so before trying anything: a reading taken from here until the
            # stream is back is not a measurement.
            self._stream_stalls += 1
            self._stream_dead = True
            self._settled = False
            self._set_gate(False)
            print("[stream] STOPPED -- nothing on %s for %.1f s (stall %d). "
                  "The radio is no longer sending; readings are frozen, not "
                  "stable. Restarting the stream."
                  % (iface, quiet, self._stream_stalls))

            recovered = False
            for attempt in range(1, 4):
                if not self._watch_run:
                    return
                try:
                    with self._radio_lock:
                        self._restart_stream()
                except Exception as e:
                    print("[stream] restart attempt %d could not be issued: %s"
                          % (attempt, e))
                    time.sleep(1.0)
                    continue
                alive, rate = self._stream_alive(iface, expect, window=1.5)
                if alive:
                    self._stream_restarts += 1
                    print("[stream] restarted on attempt %d -- %.1f MB/s. "
                          "Re-settling before the display is trusted again."
                          % (attempt, rate / 1e6))
                    recovered = True
                    break
                print("[stream] attempt %d did not bring it back (%.2f MB/s)"
                      % (attempt, rate / 1e6))

            if recovered:
                # Same rule as a hop: nothing is shown until the settle window
                # has passed, so the restart transient is not drawn as data.
                time.sleep(self.settle)
                alive, _ = self._stream_alive(iface, expect, window=0.5)
                if alive:
                    self._set_gate(True)
                    self._settled = True
                    self._stream_dead = False
                last = self._iface_bytes(iface)
                quiet = 0.0
            else:
                print("[stream] COULD NOT RESTART THE STREAM. The display "
                      "stays blank and nothing here is a measurement. Trying "
                      "again in 10 s; if this repeats the X310 needs a power "
                      "cycle.")
                time.sleep(10.0)
                last = self._iface_bytes(iface)
                quiet = 0.0

    def stream_is_alive(self):
        """False while the radio is not sending. Callers gate their display."""
        return not self._stream_dead

    def get_stream_stalls(self):
        return self._stream_stalls

    def get_stream_restarts(self):
        return self._stream_restarts

    def _transmitter_answers(self, timeout=2.0):
        try:
            host, port = self.tx_control.split(":")
            sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sk.settimeout(timeout)
            sk.sendto(b"ping", (host, int(port)))
            ok = bool(sk.recv(32))
            sk.close()
            return ok
        except Exception:
            return False

    def _retune_transmitter(self, freq):
        """Move the calibration source before we tune.

        The transmitter runs in its own process -- a HackRF needs the system
        GNU Radio while the TwinRX needs 3.8 -- so it is told over UDP. Doing
        it first means the tone is already there when the receiver arrives,
        rather than both ends relying on a clock. Without this the receiver
        hops alone and every band but the transmitter's own reads as noise.
        """
        if not self.tx_control:
            return True
        try:
            host, port = self.tx_control.split(":")
            sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sk.settimeout(1.0)
            sk.sendto(("freq %d" % int(freq)).encode(), (host, int(port)))
            sk.recv(64)
            sk.close()
            return True
        except Exception as e:
            self._tx_failures += 1
            print("[hop] TRANSMITTER DID NOT MOVE to %.4f GHz: %s\n"
                  "      this band has no tone -- its samples are not valid"
                  % (float(freq) / 1e9, e))
            return False

    def get_tx_failures(self):
        return self._tx_failures

    def _sleep(self, seconds):
        """Sleep in slices so stopping does not wait out a whole dwell."""
        t0 = time.time()
        while self._hop_run and time.time() - t0 < seconds:
            time.sleep(0.05)

    def _hopper(self):
        self._sleep(self.start_delay)      # let the flowgraph and GUI settle
        i = 0
        while self._hop_run:
            freq, gain, dwell = self.bands[i % len(self.bands)]
            self._band_index = i % len(self.bands)
            self._settled = False
            self._set_gate(False)          # blank the display while we move
            tx_ok = self._retune_transmitter(freq)
            try:
                # Held against the watchdog: a stream restart landing in the
                # middle of the timed double-tune would leave the channels
                # started at different points, which is a constant phase error
                # that looks perfectly healthy.
                with self._radio_lock:
                    self.set_gain(gain)
                    self.set_center_freq(int(freq), self.sources)
            except Exception as e:
                # Tuning only fails like this when the device is going away.
                # Carrying on would keep issuing timed commands at a radio
                # being torn down, which is what wedges the X310's control
                # plane, so stop the thread instead.
                print("[hop] TUNE TO %.4f GHz FAILED: %s" % (freq / 1e9, e))
                self._tune_failures += 1
                if self._tune_failures >= 2:
                    print("[hop] tuning has failed twice -- stopping the hop "
                          "thread rather than keep commanding a dying device")
                    self._hop_run = False
                    return
                tx_ok = False
            self._tune_failures = 0
            self._apply_conjugate()
            locked = self._locked()
            if locked is False:
                self._lock_failures += 1
            print("[hop] band %d  %.4f GHz  gain %.1f dB  lock=%s"
                  % (self._band_index, freq / 1e9, gain,
                     {True: "yes", False: "NO", None: "?"}[locked]))
            self._sleep(self.settle)
            # Only declare the band good when the transmitter moved and the LO
            # locked. Anything else leaves the display blank, because there is
            # nothing here worth drawing.
            good = tx_ok and (locked is not False)
            self._set_gate(good)
            self._settled = good
            if not good:
                print("[hop] band %d (%.4f GHz) NOT USABLE -- display stays "
                      "blank" % (self._band_index, freq / 1e9))
            self._sleep(dwell)
            i += 1

    def _apply_conjugate(self):
        """Mirror back if the LO fallback put us on the unplanned side."""
        want = -1.0 if getattr(self, "lo_fallback_active", False) else 1.0
        for sign in self._conj_q:
            sign.set_k(want)

    def is_spectrum_mirrored(self):
        return bool(getattr(self, "lo_fallback_active", False))

    def _locked(self):
        master = 0 if self.lo_export_direction.upper() == 'A' else 2
        try:
            return self.uhd_usrp_source_0.get_sensor('lo_locked', master).to_bool()
        except Exception as e:
            print("[twinrx] cannot read lo_locked on ch%d: %s" % (master, e))
            return None

    # ------------------------------------------------------------------
    # accessors
    # ------------------------------------------------------------------
    def get_band_index(self):
        return self._band_index

    def get_current_band(self):
        if self._band_index < 0:
            return None
        return self.bands[self._band_index]

    def get_lock_failures(self):
        return self._lock_failures

    def get_bands(self):
        return self.bands

    def set_bands(self, bands):
        """Replace the schedule. Takes effect from the next hop."""
        new = [tuple(b) for b in bands if b]
        if new:
            self.bands = new

    def get_settle(self):
        return self.settle

    def set_settle(self, settle):
        self.settle = float(settle)

    def get_hop_enable(self):
        return self.hop_enable

    def set_hop_enable(self, hop_enable):
        hop_enable = bool(hop_enable)
        if hop_enable and not self.hop_enable:
            self.hop_enable = True
            self._start_hopping()
        elif not hop_enable:
            self.hop_enable = False
            self._hop_run = False

    # Gain is per band here, so a single set_gain from GRC would be overwritten
    # on the next hop. Kept working for manual use, but the schedule wins.
    def set_gain(self, gain):
        """Band gain, plus each channel's trim, clamped to what the hardware has."""
        self.gain = gain
        for _ch in range(self.sources):
            want = gain + self.gain_trim[_ch]
            try:
                rng = self.uhd_usrp_source_0.get_gain_range(_ch)
                want = max(rng.start(), min(rng.stop(), want))
            except Exception as e:
                # Setting it unclamped is still the right thing -- UHD coerces
                # -- but the gain then may not be the one asked for, and phase
                # moves with gain here, so a calibration measured at the
                # nominal gain would no longer apply. Say so.
                if not self._gain_range_warned:
                    self._gain_range_warned = True
                    print("[twinrx] cannot read the gain range on ch%d (%s: %s)"
                          " -- gains are being set unclamped, so a phase "
                          "calibration may not match" % (_ch, type(e).__name__, e))
            self.uhd_usrp_source_0.set_gain(want, _ch)

    def get_channel_gains(self):
        """What each channel is actually set to, read back from the radio."""
        return [self.uhd_usrp_source_0.get_gain(c) for c in range(self.sources)]

    def set_center_freq(self, center_freq, sources=None):
        if sources is None:
            sources = self.sources
        self.center_freq = center_freq
        twinrx_usrp_source.set_center_freq(self, center_freq, sources)
