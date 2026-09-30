#!/usr/bin/env python3
"""HackRF One CW calibration source for the USRP-2945 phase bench.

Emits a continuous tone at (centre + offset) and accepts retune commands on a
UDP socket, so the receiver can drive the hop and both sides stay in step
without either guessing from a wall clock.

This must run under the SYSTEM GNU Radio (3.10 + gr-osmosdr).  The receiver
runs under ~/gnuradio-3.8 for the TwinRX, so the two cannot share a process --
hence the socket.

  # transmitter, in its own terminal. This shell defaults to GR 3.8 for the
  # TwinRX, so the HackRF side has to go through the gr310 wrapper:
  gr310 python3 ~/radar2/hackrf_tone_source.py --freq 2.4e9 --vga 16

  # receiver drives the hopping
  source ~/gnuradio-3.8/setup_env.sh
  python3 guru/twinrx_hop_test.py --freqs 2.4e9,5.1e9,5.8e9 --tx-control 127.0.0.1:5123

Standalone hopping, if you would rather the transmitter run the schedule:
  python3 hackrf_tone_source.py --hop 2.4e9,5.1e9,5.8e9 --dwell 2

Notes on the HackRF as a calibration source, versus the B210:
  * Frequency accuracy is much worse -- the stock crystal is around +/-20 ppm
    against the B210's ~1.6 ppm.  At 5.8 GHz that is up to ~116 kHz of offset
    error, so the receiver has to search a wide window for the tone.  It does
    not affect the phase measurement itself: every channel is read at the same
    bin, so the error is common mode.
  * Output power falls off well above ~4 GHz, so 5.8 GHz will land weaker at
    the receiver than 2.4 GHz for the same gain setting.  Use --vga-map if the
    SNR difference between bands is awkward.
  * The DAC is 8-bit, so there is more quantisation noise and stronger spurs
    than the B210 produced.  Fine for a CW tone.
  * Keep the sample rate at 2 Msps or above. At 1 Msps the SoapySDR stream
    times out continuously. The rate does not have to match the receiver.
"""
import sys as _sys
try:
    # the log is a file: write each line as it happens, or a stall restart
    # stays invisible in the buffer
    _sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass
import argparse
import atexit
import os
import socket
import sys
import threading
import time

from gnuradio import analog, blocks, gr

# Two ways to reach the HackRF.  Prefer gr-soapy: SoapySDR and its HackRF
# module link only libhackrf, whereas gr-osmosdr also drags in libuhd 4.1.
# Keeping UHD out of this process matters -- the X310 runs an FPGA image built
# for UHD 3.15 and sits on a reachable network, so a stray UHD 4.1 discovery
# from here is a plausible way to upset it.
_BACKENDS = []
try:
    from gnuradio import soapy
    _BACKENDS.append("soapy")
except ImportError:
    soapy = None
try:
    import osmosdr
    _BACKENDS.append("osmosdr")
except ImportError:
    osmosdr = None

if not _BACKENDS:
    sys.exit(
        "Neither gr-soapy nor gr-osmosdr was found.\n"
        "This shell defaults to GNU Radio 3.8 (for the TwinRX), but the HackRF\n"
        "needs the system GNU Radio 3.10. Use the gr310 wrapper:\n\n"
        "    gr310 python3 ~/radar2/hackrf_tone_source.py " +
        " ".join(sys.argv[1:]) + "\n\n"
        "or simply:   hackrf --freq 2.4e9 --vga 16")

# Output power at maximum gain, very roughly, per radio. Only used for the
# startup level estimate -- an order of magnitude, not a calibration.
PMAX_DBM = {
    "hackrf": {2.4e9: 13.0, 5.1e9: 2.0, 5.8e9: 0.0},
    "b210":   {2.4e9: 10.0, 5.1e9: 5.0, 5.8e9: 4.0},
}
GAIN_MAX = {"hackrf": 47.0, "b210": 89.8}   # the HackRF figure is its TX VGA
DAC_BITS = {"hackrf": 8, "b210": 12}
PPM = {"hackrf": 20, "b210": 2}


def pmax_at(freq, radio="hackrf"):
    t = PMAX_DBM[radio]
    return t[min(t, key=lambda f: abs(f - freq))]


class ToneTX(gr.top_block):
    """CW tone out of the HackRF, with the backend chosen at construction."""

    def __init__(self, args):
        gr.top_block.__init__(self, "HackRF CW tone")
        self.a = args
        self.backend = args.backend
        self.radio = getattr(args, "radio", "hackrf")
        if self.radio == "b210":
            # The B210 is a UHD device, so this path necessarily loads libuhd.
            # Keep it off the X310's network if that ever matters.
            self.sink = osmosdr.sink(args="uhd,type=b200")
            self.sink.set_sample_rate(args.rate)
            self.sink.set_center_freq(args.freq, 0)
            self.sink.set_gain(float(args.vga), 0)
            self.sink.set_antenna("TX/RX", 0)
            self.backend = "osmosdr"
        elif self.backend == "soapy":
            self.sink = soapy.sink(f"driver=hackrf", "fc32", 1, "", "", [""], [""])
            self.sink.set_sample_rate(0, args.rate)
            self.sink.set_frequency(0, float(args.freq))
            self.sink.set_antenna(0, "TX/RX")
            self.sink.set_gain(0, "AMP", 14.0 if args.amp else 0.0)
            self.sink.set_gain(0, "VGA", float(args.vga))
        else:
            self.sink = osmosdr.sink(args=f"hackrf={args.device}")
            self.sink.set_sample_rate(args.rate)
            self.sink.set_center_freq(args.freq, 0)
            self.sink.set_gain(14 if args.amp else 0, 0)   # RF amp: 0 or 14 dB
            self.sink.set_if_gain(args.vga, 0)             # TX VGA: 0..47 dB
            self.sink.set_bb_gain(0, 0)
            self.sink.set_antenna("TX/RX", 0)
        self.src = analog.sig_source_c(args.rate, analog.GR_COS_WAVE,
                                       self._tone_offset(args.freq), args.amplitude)
        # When the Soapy stream stalls the sink stops consuming, back-pressure
        # halts the source, and this rate collapses -- which is how the
        # watchdog notices. The sink itself keeps accepting control commands
        # while dead, so asking it proves nothing.
        self.probe = blocks.probe_rate(gr.sizeof_gr_complex, 500.0, 0.15)
        self.connect(self.src, self.sink)
        self.connect(self.src, self.probe)

    def sample_rate_now(self):
        return self.probe.rate()

    # ---- runtime control -------------------------------------------------
    def _mapped_offset(self, freq):
        if not self.a.offset_map:
            return self.a.offset
        return min(self.a.offset_map, key=lambda kv: abs(kv[0] - freq))[1]

    def _tone_offset(self, freq):
        """What to generate so the tone ARRIVES at centre + offset.

        This radio's clock runs a.ppm off the receiver's; at RF that shifts
        everything by ppm * freq (-4.5 ppm = -10.9 kHz at 2.4 GHz, measured
        2026-09-29), more than a small offset itself. Generating
        offset - ppm * freq puts the tone where it was asked for.
        """
        return self._mapped_offset(freq) - self.a.ppm * 1e-6 * float(freq)

    def set_offset(self, off):
        """Move the tone within the band, without retuning the radio."""
        self.a.offset = float(off)
        self.src.set_frequency(self._tone_offset(self.get_freq()))
        return self.a.offset

    def set_ppm(self, ppm):
        """Clock-error correction, applied at once (no retune)."""
        self.a.ppm = float(ppm)
        self.src.set_frequency(self._tone_offset(self.get_freq()))
        return self.a.ppm

    def retune(self, freq):
        freq = float(freq)
        self.src.set_frequency(self._tone_offset(freq))
        if self.radio == "b210" or self.backend == "osmosdr":
            self.sink.set_center_freq(freq, 0)
            if self.a.vga_map:
                self.set_vga(self._mapped_vga(freq))
            return self.sink.get_center_freq(0)
        if self.backend == "soapy":
            self.sink.set_frequency(0, freq)
        else:
            self.sink.set_center_freq(freq, 0)
        if self.a.vga_map:
            self.set_vga(self._mapped_vga(freq))
        return self.get_freq()

    def get_freq(self):
        return (self.sink.get_frequency(0) if self.backend == "soapy"
                else self.sink.get_center_freq(0))

    def _mapped_vga(self, freq):
        best = min(self.a.vga_map, key=lambda kv: abs(kv[0] - freq))
        return best[1]

    def set_vga(self, g):
        # B210 TX gain runs 0..89.8 dB; the HackRF VGA stops at 47.
        top = 89 if self.radio == "b210" else 47
        g = max(0, min(top, int(g)))
        self.a.vga = g
        if self.radio == "b210":
            self.sink.set_gain(float(g), 0)
            return g
        if self.backend == "soapy":
            self.sink.set_gain(0, "VGA", float(g))
        else:
            self.sink.set_if_gain(g, 0)
        return g


class TimeoutTap:
    """Count the Soapy sink's TIMEOUT warnings as this process prints them.

    In one kind of HackRF stall the sink keeps consuming samples and drops
    them with "Soapy sink error: TIMEOUT", so nothing is transmitted while the
    sample rate the watchdog measures stays normal (2026-09-28: 1387 TIMEOUTs,
    no restart, NO TONE on the receiver). GNU Radio 3.10 prints that warning on
    stdout, not through anything Python can hook, so the process's own stdout
    and stderr are passed through a pipe that is read here and forwarded
    unchanged to where they went before.
    """
    PATTERN = b"Soapy sink error: TIMEOUT"

    def __init__(self, fds=(1, 2)):
        self._lock = threading.Lock()
        self._count = 0
        self.broken = None
        self._pumps = []
        for fd in fds:
            orig = os.dup(fd)
            r, w = os.pipe()
            os.dup2(w, fd)
            os.close(w)
            th = threading.Thread(target=self._pump, args=(fd, r, orig),
                                  daemon=True)
            th.start()
            self._pumps.append((fd, orig, th))
        # the pumps are daemon threads: at exit, whatever is still in a pipe
        # (the last lines printed) would be lost without this
        atexit.register(self.close)

    def close(self):
        """Put the original outputs back and forward everything still queued."""
        for f in (sys.stdout, sys.stderr):
            try:
                f.flush()
            except Exception:
                pass
        for fd, orig, th in self._pumps:
            os.dup2(orig, fd)           # closes the pipe's write end -> EOF
        for fd, orig, th in self._pumps:
            th.join(2.0)

    def _pump(self, fd, r, orig):
        keep = len(self.PATTERN) - 1        # a match may straddle two reads
        tail = b""
        try:
            while True:
                chunk = os.read(r, 65536)
                if not chunk:
                    break
                view = memoryview(chunk)
                while view:
                    view = view[os.write(orig, view):]
                data = tail + chunk
                n = data.count(self.PATTERN)
                if n:
                    with self._lock:
                        self._count += n
                    data = data[data.rfind(self.PATTERN) + len(self.PATTERN):]
                tail = data[-keep:]
        except Exception as e:
            self.broken = "%s: %s" % (type(e).__name__, e)
        finally:
            # without this reader, every later write to fd would block on a
            # full pipe; put the original back and let the watchdog say so
            os.dup2(orig, fd)
            if self.broken is None:
                self.broken = "output pipe closed"

    def take(self):
        """TIMEOUT warnings seen since the last call."""
        with self._lock:
            n, self._count = self._count, 0
        return n


# a stalled stream prints TIMEOUT continuously; one retune can print a few
TIMEOUTS_PER_S_STALLED = 3


def watchdog(make_tb, state, stop, expected_rate, tap=None):
    """Restart the flowgraph if the transmit stream dies.

    The HackRF's SoapySDR stream stalls after a few minutes of retuning and
    never recovers by itself, so the tone silently disappears while the
    process still looks healthy. It shows up in one of two ways: the sink stops
    consuming (the sample rate collapses), or it keeps consuming and drops
    everything with TIMEOUT warnings (the rate looks normal). Either one for
    two seconds in a row restarts the flowgraph, which brings the tone back.
    """
    floor = expected_rate * 0.25
    bad = 0
    time.sleep(8.0)                     # let the first start settle
    if tap is not None:
        tap.take()
    while not stop.is_set():
        time.sleep(1.0)
        tb = state.get("tb")
        if tb is None:
            continue
        timeouts = tap.take() if tap is not None else 0
        if tap is not None and tap.broken and not state.get("tap_broken_said"):
            state["tap_broken_said"] = True
            print("[watchdog] TIMEOUT counter stopped (%s) -- a stall that keeps "
                  "the sample rate normal will NOT be caught" % tap.broken)
        try:
            rate = tb.sample_rate_now()
        except Exception as e:
            # Skipping the check quietly means the watchdog stops watching and
            # nothing says so: a stalled transmitter would then read as a band
            # with no tone, and the receiver would be blamed for it.
            if not state.get("rate_read_failed"):
                state["rate_read_failed"] = True
                print("[watchdog] cannot read the transmit rate (%s: %s) -- "
                      "a stalled stream will NOT be caught from here"
                      % (type(e).__name__, e))
            rate = None
        else:
            state["rate_read_failed"] = False
        slow = rate is not None and rate < floor
        dropping = timeouts >= TIMEOUTS_PER_S_STALLED
        if slow or dropping:
            bad += 1
        else:
            bad = 0
        if bad >= 2:
            why = []
            if slow:
                why.append("%.0f Sps, expected %.0f" % (rate, expected_rate))
            if dropping:
                why.append("%d TIMEOUT warnings in the last second" % timeouts)
            print("\n[watchdog] transmit stream stalled (%s) -- restarting it"
                  % "; ".join(why))
            try:
                tb.stop(); tb.wait()
            except Exception as e:
                print("[watchdog] stopping the stalled stream failed: %s" % e)
            time.sleep(1.0)
            # keep trying until the radio is back (e.g. its USB was unplugged):
            # a failed restart must never leave a dead stream nobody watches
            attempt = 0
            while not stop.is_set():
                attempt += 1
                try:
                    # under the control lock: a 'freq' that arrives during the
                    # restart must not land in the dead flowgraph and be lost
                    # (2026-09-30: stalled during 5.8 GHz, came back on 2.4 GHz)
                    with state["lock"]:
                        new = make_tb()
                        new.start()
                        state["tb"] = new
                    print("[watchdog] transmitter restarted on %.4f GHz (attempt %d)"
                          % (new.get_freq() / 1e9, attempt))
                    break
                except Exception as e:
                    print("[watchdog] restart attempt %d failed: %s -- NOT TRANSMITTING, "
                          "retrying in 3 s" % (attempt, e))
                    if attempt >= 3:
                        # A replugged HackRF comes back as a new USB device, but
                        # this process's libusb/libhackrf state still points at
                        # the old one: every in-process retry fails "No such
                        # device" forever (2026-09-30: 1843 attempts). Start the
                        # program again as a fresh process, on the band last
                        # asked for; it keeps retrying the same way.
                        argv = [x for x in sys.argv]
                        if "--freq" in argv:
                            i = argv.index("--freq")
                            del argv[i:i + 2]
                        argv += ["--freq", "%.0f" % state["freq"]]
                        print("[watchdog] %d restarts failed in this process -- starting it again "
                              "as a new process on %.4f GHz" % (attempt, state["freq"] / 1e9), flush=True)
                        time.sleep(3.0)
                        if tap is not None:
                            tap.close()         # real stdout/stderr back, or the new
                                                # process writes into a dead pipe
                        os.execv(sys.executable, [sys.executable] + argv)
                    time.sleep(3.0)
            bad = 0
            time.sleep(8.0)
            if tap is not None:
                tap.take()              # warnings from the old stream


def level_report(a, freq):
    """Rough level at each 2945 port.  Order of magnitude only."""
    pmax = pmax_at(freq, a.radio)
    if a.radio == "b210":
        backoff = GAIN_MAX["b210"] - a.vga
    else:
        backoff = (47 - a.vga) + (0 if a.amp else 14)
    tx_out = pmax - backoff + 20 * (0 if a.amplitude <= 0 else
                                    __import__("math").log10(a.amplitude))
    at_port = tx_out - a.pad - a.split_loss
    worst = pmax - a.pad - a.split_loss
    print(f"  estimated at {freq/1e9:.3f} GHz:")
    print(f"    HackRF output      ~ {tx_out:7.1f} dBm")
    print(f"    after {a.pad:.0f} dB pad "
          f"+ {a.split_loss:.0f} dB split ~ {at_port:7.1f} dBm  <- each 2945 port")
    print(f"    TwinRX full scale  :   -20.0 dBm")
    print(f"    TwinRX damage      :   +10.0 dBm")
    if at_port > -20:
        print("    !! above TwinRX full scale -- the front end will compress.")
    if worst > 0:
        print(f"    !! at maximum gain a port would see ~{worst:+.1f} dBm.")
    if a.pad <= 0:
        print("    !! no pad declared. A fixed attenuator is the only thing")
        print("       protecting the TwinRX from a mistyped gain.")


def control_server(state, host, port, stop):
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.settimeout(0.3)
    print(f"  control socket: udp://{host}:{port}   "
          f"(commands: 'freq <hz>', 'vga <dB>', 'ppm <clock error>', 'get', 'ping', 'quit')")
    while not stop.is_set():
        try:
            data, peer = srv.recvfrom(256)
        except socket.timeout:
            continue
        cmd = data.decode(errors="ignore").strip().split()
        if not cmd:
            continue
        try:
          with state["lock"]:
            tb = state["tb"]
            if cmd[0] == "freq":
                # Retuning is what makes the HackRF's Soapy stream stall, so a
                # request for the frequency it is already on changes nothing.
                if abs(float(cmd[1]) - tb.get_freq()) < 1.0:
                    srv.sendto(f"ok {tb.get_freq():.0f}".encode(), peer)
                    print(f"    -> already on {tb.get_freq()/1e9:.4f} GHz, not retuned")
                    continue
                state["freq"] = float(cmd[1])
                actual = tb.retune(cmd[1])
                srv.sendto(f"ok {actual:.0f}".encode(), peer)
                print(f"    -> retuned to {actual/1e9:.4f} GHz  "
                      f"(vga {tb.a.vga}, tone {tb._mapped_offset(actual)/1e3:+.1f} kHz, "
                      f"generated {tb._tone_offset(actual)/1e3:+.3f} kHz for {tb.a.ppm:+.3f} ppm)")
            elif cmd[0] == "get":
                # what the transmitter is really doing now -- a measurement must
                # use this, never assume the correction from a file
                srv.sendto(("ok freq=%.0f offset=%.3f ppm=%.4f vga=%d generated=%.3f"
                            % (tb.get_freq(), tb._mapped_offset(tb.get_freq()), tb.a.ppm, tb.a.vga,
                               tb._tone_offset(tb.get_freq()))).encode(), peer)
            elif cmd[0] == "ppm":
                srv.sendto(f"ok {tb.set_ppm(cmd[1]):+.4f}".encode(), peer)
                print(f"    -> clock correction {tb.a.ppm:+.4f} ppm: generating "
                      f"{tb._tone_offset(tb.get_freq())/1e3:+.3f} kHz")
            elif cmd[0] == "vga":
                srv.sendto(f"ok {tb.set_vga(cmd[1])}".encode(), peer)
            elif cmd[0] == "ping":
                srv.sendto(b"ok", peer)
            elif cmd[0] == "quit":
                srv.sendto(b"ok", peer)
                stop.set()
            else:
                srv.sendto(b"err unknown", peer)
        except Exception as e:                      # never kill the transmitter
            srv.sendto(f"err {e}".encode(), peer)
    srv.close()


def parse_offset_map(text):
    if not text:
        return None
    out = []
    for item in text.split(","):
        f, o = item.split(":")
        out.append((float(f), float(o)))
    return out


def parse_vga_map(text):
    if not text:
        return None
    out = []
    for item in text.split(","):
        f, g = item.split(":")
        out.append((float(f), int(g)))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device", default="0", help="hackrf device index")
    p.add_argument("--radio", choices=["hackrf", "b210"], default="hackrf",
                   help="which transmitter to use. b210 goes through UHD, so "
                        "it needs the system GNU Radio too (gr310 wrapper)")
    p.add_argument("--backend", choices=["soapy", "osmosdr"], default=None,
                   help="soapy (default) keeps libuhd out of this process; "
                        "osmosdr also loads UHD 4.1")
    p.add_argument("--freq", type=float, default=2.4e9)
    p.add_argument("--offset", type=float, default=200e3,
                   help="tone offset from centre; must match the receiver")
    p.add_argument("--rate", type=float, default=2e6,
                   help="HackRF TX sample rate. Keep this at 2 Msps or above: "
                        "at 1 Msps the SoapySDR stream throws continuous "
                        "TIMEOUTs. It need not match the receiver -- the tone "
                        "sits at centre+offset either way.")
    p.add_argument("--ppm", type=float, default=0.0,
                   help="this radio's clock error vs the receiver, ppm (measure it with "
                        "tone_freq_check.py); the tone is generated so it ARRIVES at centre + offset")
    p.add_argument("--vga", type=int, default=16,
                   help="TX VGA gain 0..47 dB (start low)")
    p.add_argument("--amp", action="store_true",
                   help="enable the +14 dB RF amp (leave off unless needed)")
    p.add_argument("--offset-map", dest="offset_map_s", default=None,
                   help="per-band tone offset, e.g. 2.4e9:200e3,5.1e9:-200e3. "
                        "A band whose receive chain inverts the spectrum can "
                        "be sent a negative offset so the tone still arrives "
                        "at +200 kHz, instead of widening the receiver filter.")
    p.add_argument("--vga-map", dest="vga_map_s", default=None,
                   help="per-band gain, e.g. 2.4e9:12,5.1e9:24,5.8e9:30 -- the "
                        "HackRF puts out less power at the top of its range")
    p.add_argument("--amplitude", type=float, default=0.7,
                   help="DAC amplitude 0..1; the HackRF DAC is only 8-bit")
    p.add_argument("--pad", type=float, default=0.0,
                   help="external fixed attenuator, dB")
    p.add_argument("--split-loss", dest="split_loss", type=float, default=7.0)
    p.add_argument("--control", default="127.0.0.1:5123",
                   help="udp host:port for retune commands, or 'none'")
    p.add_argument("--hop", default=None,
                   help="run the schedule here instead: comma separated Hz")
    p.add_argument("--dwell", type=float, default=2.0)
    a = p.parse_args()

    if not 0 < a.amplitude <= 1.0:
        sys.exit("--amplitude must be in (0, 1]")
    _gmax = 89 if a.radio == "b210" else 47
    if not 0 <= a.vga <= _gmax:
        sys.exit("--vga must be 0..%d for the %s" % (_gmax, a.radio))
    a.vga_map = parse_vga_map(a.vga_map_s)
    a.offset_map = parse_offset_map(a.offset_map_s)
    if a.radio == "b210":
        if osmosdr is None:
            sys.exit("the b210 path needs gr-osmosdr (system GNU Radio 3.10)")
        a.backend = "osmosdr"
    elif a.backend is None:
        a.backend = _BACKENDS[0]
    elif a.backend not in _BACKENDS:
        sys.exit(f"backend '{a.backend}' is not available here "
                 f"(have: {', '.join(_BACKENDS)})")

    # before the sink exists, so its first warning is already counted
    tap = TimeoutTap() if a.radio == "hackrf" and a.backend == "soapy" else None
    tb = ToneTX(a)
    print("=" * 66)
    print(("B210" if a.radio == "b210" else "HackRF One") +
          " CW calibration source")
    print("=" * 66)
    print(f"  centre       : {a.freq/1e9:.4f} GHz")
    print(f"  tone         : centre + {a.offset/1e3:.1f} kHz"
          + (f"   (clock correction {a.ppm:+.3f} ppm: generated {a.offset/1e3 - a.ppm*1e-9*a.freq:+.3f} kHz here)"
             if a.ppm else ""))
    print(f"  sample rate  : {a.rate/1e6:.3f} Msps")
    if a.radio == "b210":
        print(f"  TX gain      : {a.vga} dB   of 0..{GAIN_MAX['b210']:.0f}")
    else:
        print(f"  TX VGA       : {a.vga} dB      "
              f"RF amp: {'ON (+14 dB)' if a.amp else 'off'}")
    print(f"  amplitude    : {a.amplitude:.2f} of full scale "
          f"({DAC_BITS[a.radio]}-bit DAC)")
    print(f"  radio        : {a.radio}")
    if a.offset_map:
        print("  tone offsets : " + ", ".join(
            f"{f/1e9:.2f}GHz:{o/1e3:+.0f}kHz" for f, o in a.offset_map))
    print(f"  backend      : gr-{a.backend}"
          + ("   (no libuhd in this process)" if a.backend == "soapy"
             else "   (WARNING: also loads UHD 4.1)"))
    level_report(a, a.freq)
    _ppm = PPM[a.radio]
    print(f"  NOTE: this radio's reference is ~+/-{_ppm} ppm, so the tone can sit")
    print(f"        up to ~{5.8e9 * _ppm * 1e-6 / 1e3:.0f} kHz from the nominal offset at 5.8 GHz.")
    print("        That is common mode across channels and does not affect phase.")

    stop = threading.Event()
    tb.start()

    # A restart replaces the flowgraph object, so everything reaches it
    # through this holder rather than capturing it once.
    # "freq" = the band last asked for; a restart comes back on it (the
    # stalled flowgraph's own reading cannot be trusted for that)
    state = {"tb": tb, "freq": tb.get_freq(), "lock": threading.Lock()}

    def _make():
        fresh = ToneTX(a)
        fresh.retune(state["freq"])              # come back on the band asked for
        return fresh

    threading.Thread(target=watchdog,
                     args=(_make, state, stop, a.rate, tap), daemon=True).start()

    th = None
    if a.control.lower() != "none":
        host, port = a.control.split(":")
        th = threading.Thread(target=control_server,
                              args=(state, host, int(port), stop), daemon=True)
        th.start()

    print("\ntransmitting ...  Ctrl-C to stop\n")
    try:
        if a.hop:
            seq = [float(x) for x in a.hop.split(",")]
            while not stop.is_set():
                for f in seq:
                    if stop.is_set():
                        break
                    state["tb"].retune(f)
                    print(f"  hop -> {f/1e9:.4f} GHz")
                    time.sleep(a.dwell)
        else:
            while not stop.is_set():
                time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        try:
            state["tb"].stop()
            state["tb"].wait()
        except Exception:
            pass
        print("\nstopped.")


if __name__ == "__main__":
    main()
