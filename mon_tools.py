"""MON mode helpers for guru_mon (monitoring: every channel its own LO, own band).

Everything here is measured on the receiver. The lab transmitter is only told
which band to send on (UDP 'freq', same as guru); nothing is read back from it
except its own reply, which is shown as its reply.
"""
import socket
import time

import numpy as np

SUBDEV = "A:0 A:1 B:0 B:1"
ANTENNAS = ["RX1", "RX2", "RX1", "RX2"]
PORTS = ["A/RX1", "A/RX2", "B/RX1", "B/RX2"]


def tx_freq(freq, control="127.0.0.1:5123"):
    """Ask the lab transmitter to send on `freq`; returns its reply (or why not)."""
    host, port = control.split(":")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3.0)
    try:
        s.sendto(("freq %d" % int(freq)).encode(), (host, int(port)))
        r = s.recv(256).decode(errors="replace").strip()
        return "HackRF on %.4f GHz: %s" % (freq / 1e9, r)
    except Exception as e:
        return "HackRF NOT answering (%s) - no lab tone" % type(e).__name__
    finally:
        s.close()


def mon_setup(src, freqs, gains):
    """Put all 4 TwinRX channels in MON mode and tune each to its own band.

    The TwinRX keeps whatever LO routing the last program left (guru leaves it
    shared, ch2 exporting), and the stock USRP Source tunes before it sets the
    LO source. So, explicitly and in this order: export off everywhere, every
    channel on its own internal LO, then tune each channel (twice, as every
    guru tune) and report its own lock sensor.
    """
    from gnuradio import uhd
    n = len(freqs)
    for ch in range(n):
        src.set_lo_export_enabled(False, uhd.ALL_LOS, ch)
    for ch in range(n):
        src.set_lo_source("internal", uhd.ALL_LOS, ch)
    for _ in range(2):
        for ch in range(n):
            src.set_gain(float(gains[ch]), ch)
            src.set_center_freq(uhd.tune_request(float(freqs[ch])), ch)
    time.sleep(0.2)
    out = []
    for ch in range(n):
        out.append({"ch": ch, "freq": src.get_center_freq(ch),
                    "lo_source": src.get_lo_source(uhd.ALL_LOS, ch),
                    "export": src.get_lo_export_enabled(uhd.ALL_LOS, ch),
                    "locked": lo_locked(src, ch)})
    for r in out:
        print("[mon] ch%d %s  %.4f GHz  LO %s%s  %s" % (
            r["ch"], PORTS[r["ch"]], r["freq"] / 1e9, r["lo_source"],
            " +export" if r["export"] else "", "LOCKED" if r["locked"] else "NOT LOCKED"))
    return out


def lo_locked(src, ch):
    try:
        return bool(src.get_sensor("lo_locked", ch).to_bool())
    except Exception:
        return None


def readout(x, fs, dc_guard=20e3, tone_db=30.0):
    """Strongest line of one snapshot (outside +/- dc_guard of 0 Hz, where the
    receiver's own DC/LO leakage sits), its level over the noise median, and
    the ADC peak (full scale 1.0)."""
    N = len(x)
    w = np.hanning(N).astype(np.float32)
    S = np.abs(np.fft.fft(x * w)) ** 2
    F = np.fft.fftfreq(N, 1.0 / fs)
    k = int(np.argmax(np.where(np.abs(F) >= dc_guard, S, 0)))
    lvl = float(10 * np.log10(S[k] / (np.median(S) + 1e-30)))
    return {"f": float(F[k]), "db": lvl, "tone": lvl >= tone_db, "peak": float(np.abs(x).max())}
