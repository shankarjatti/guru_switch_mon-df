#!/usr/bin/env python3
"""
twinrx_band_check.py -- is a channel dead everywhere, or only high up?

Sweeps the B210 source and the 2945 receiver together and reports, per
frequency, how much tone each channel receives.  A channel that receives
fine at low frequency and falls away at high frequency is behind a
component that is out of band, not behind a loose connector.

Run under the 3.15 environment (the 2945 needs it).  The B210 is launched
as a subprocess with the isolated paths stripped, so it picks up the system
UHD, which is where the b2xx images live.

  source ~/gnuradio-3.8/setup_env.sh
  python3 twinrx_band_check.py
  python3 twinrx_band_check.py --freqs 100e6,500e6,1e9,2e9,3e9 --gain 55
"""
import argparse, os, subprocess, sys, time
import numpy as np
import uhd

ALL_LOS, NCH = "all", 4
HERE = os.path.dirname(os.path.abspath(__file__))


def parse_args():
    p = argparse.ArgumentParser(
        description="Per-band tone reception check across all 4 channels",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--freqs",
                   default="100e6,300e6,700e6,1.2e9,1.8e9,2.4e9,3.5e9,5e9",
                   help="comma separated RF frequencies to test")
    p.add_argument("--gain", type=float, default=55.0, help="B210 TX gain (dB)")
    p.add_argument("--rx-gain", type=float, default=30.0, help="2945 RX gain (dB)")
    p.add_argument("--pad", type=float, default=30.0, help="attenuator, for the budget print")
    p.add_argument("--offset", type=float, default=200e3, help="tone offset (Hz)")
    p.add_argument("--rate", type=float, default=1e6, help="sample rate (Sps)")
    p.add_argument("--nsamps", type=int, default=100000)
    p.add_argument("--monitor", action="store_true",
                   help="live mode: hold one frequency and print the four "
                        "channel levels every second, so you can unplug a "
                        "cable and watch which channel drops")
    p.add_argument("--monitor-secs", type=float, default=180.0,
                   help="how long --monitor runs before exiting")
    p.add_argument("--settle", type=float, default=12.0,
                   help="seconds to let the B210 come up at each frequency")
    return p.parse_args()


def system_env():
    """Environment with the isolated 3.15 paths removed, so the B210
    subprocess loads the system UHD (which ships b2xx images)."""
    env = dict(os.environ)
    iso = env.get("UHD315_DIR", "")
    gr = env.get("GR38_DIR", "")
    for var in ("PYTHONPATH", "LD_LIBRARY_PATH", "PATH"):
        parts = [q for q in env.get(var, "").split(":")
                 if q and not (iso and q.startswith(iso))
                 and not (gr and q.startswith(gr))]
        env[var] = ":".join(parts)
    env.pop("UHD315_DIR", None)
    return env


def start_source(freq, args):
    cmd = [sys.executable, os.path.join(HERE, "b210_tone_source.py"),
           "--freq", "%r" % float(freq), "--gain", "%r" % args.gain,
           "--pad", "%r" % args.pad, "--offset", "%r" % args.offset,
           "--rate", "%r" % args.rate]
    return subprocess.Popen(cmd, env=system_env(), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, cwd=HERE)


def tone_presence(x, rate, f_tone, nblk=2048):
    t = np.arange(x.shape[1]) / rate
    nb = x.shape[1] // nblk
    f_ref = f_tone + 53e3
    if abs(f_ref) > 0.45 * rate:
        f_ref = f_tone - 53e3

    def coh(ch, fq):
        m = x[ch] * np.exp(-2j * np.pi * fq * t)
        return (np.abs(m[:nb * nblk].reshape(nb, nblk).mean(axis=1)) ** 2).mean()

    return [10 * np.log10(coh(c, f_tone) / max(coh(c, f_ref), 1e-30))
            for c in range(NCH)]


def main():
    args = parse_args()
    freqs = [float(f) for f in args.freqs.split(",")]

    usrp = uhd.usrp.MultiUSRP("type=x300")
    usrp.set_rx_subdev_spec(uhd.usrp.SubdevSpec("A:0 A:1 B:0 B:1"))
    usrp.set_clock_source("internal"); usrp.set_time_source("internal")
    usrp.set_rx_rate(args.rate)
    for ch in range(NCH):
        usrp.set_rx_gain(args.rx_gain, ch)
        usrp.set_rx_antenna("RX1" if ch % 2 == 0 else "RX2", ch)
    for ch in range(NCH):
        usrp.set_rx_lo_export_enabled(False, ALL_LOS, ch)
    for ch, s in enumerate(["external", "external", "internal", "companion"]):
        usrp.set_rx_lo_source(s, ALL_LOS, ch)
    usrp.set_rx_lo_export_enabled(True, ALL_LOS, 2)
    usrp.set_time_now(uhd.types.TimeSpec(0.0))

    st = uhd.usrp.StreamArgs("fc32", "sc16"); st.channels = list(range(NCH))
    rx = usrp.get_rx_stream(st); spb = rx.get_max_num_samps()
    md = uhd.types.RXMetadata()

    def tune(f):
        tr = uhd.types.TuneRequest(float(f))
        tr.rf_freq_policy = uhd.types.TuneRequestPolicy.auto
        tr.dsp_freq_policy = uhd.types.TuneRequestPolicy.manual
        tr.dsp_freq = 0.0
        for _ in range(2):
            usrp.set_command_time(usrp.get_time_now() + uhd.types.TimeSpec(0.1))
            for ch in range(NCH):
                usrp.set_rx_freq(tr, ch)
            usrp.clear_command_time(); time.sleep(0.15)

    def grab():
        out = np.zeros((NCH, args.nsamps), np.complex64)
        buf = np.zeros((NCH, spb), np.complex64)
        c = uhd.types.StreamCMD(uhd.types.StreamMode.num_done)
        c.num_samps = args.nsamps; c.stream_now = False
        c.time_spec = usrp.get_time_now() + uhd.types.TimeSpec(0.15)
        rx.issue_stream_cmd(c); got = 0
        while got < args.nsamps:
            n = rx.recv(buf, md, 2.0)
            if md.error_code != uhd.types.RXMetadataErrorCode.none or n == 0:
                break
            k = min(n, args.nsamps - got); out[:, got:got + k] = buf[:, :k]; got += k
        return out[:, :got]

    if args.monitor:
        f = freqs[0]
        proc = start_source(f, args)
        time.sleep(args.settle)
        tune(f)
        print("")
        print("=" * 72)
        print("LIVE MONITOR at %.3f MHz -- unplug a cable and watch it drop"
              % (f / 1e6))
        print("=" * 72)
        print("  RF A/RX1 = ch0     RF A/RX2 = ch1")
        print("  RF B/RX1 = ch2     RF B/RX2 = ch3")
        print("")
        print("      ch0      ch1      ch2      ch3     (dB, * = receiving)")
        t_end = time.time() + args.monitor_secs
        try:
            while time.time() < t_end:
                x = grab()
                nfft = 8192; w = np.hanning(nfft); ns = x.shape[1] // nfft
                if ns < 1:
                    continue
                P = np.zeros(nfft)
                for ch in range(NCH):
                    seg = x[ch, :ns * nfft].reshape(-1, nfft) * w
                    P += (np.abs(np.fft.fft(seg, axis=1)) ** 2).mean(axis=0)
                fr = np.fft.fftfreq(nfft, 1.0 / args.rate)
                m = np.abs(fr) > 20e3
                f_tone = float(fr[int(np.argmax(np.where(m, P, 0)))])
                pres = tone_presence(x, args.rate, f_tone)
                print("   " + "  ".join("%7.1f%s" % (v, "*" if v >= 6 else " ")
                                        for v in pres), flush=True)
                time.sleep(0.6)
        except KeyboardInterrupt:
            pass
        finally:
            proc.terminate()
            try: proc.wait(timeout=8)
            except Exception: proc.kill()
        return 0

    print("")
    print("=" * 72)
    print("BAND CHECK   tone received per channel, dB over an off-tone reference")
    print("=" * 72)
    print("  A channel fine low down but dead high up sits behind an")
    print("  out-of-band component. A channel dead everywhere is unconnected.")
    print("")
    print("     frequency        ch0      ch1      ch2      ch3")
    table = {}
    for f in freqs:
        proc = start_source(f, args)
        time.sleep(args.settle)
        try:
            tune(f)
            x = grab()
            if x.shape[1] < args.nsamps // 2:
                raise RuntimeError("short capture")
            nfft = 8192; w = np.hanning(nfft); ns = x.shape[1] // nfft
            P = np.zeros(nfft)
            for ch in range(NCH):
                seg = x[ch, :ns * nfft].reshape(-1, nfft) * w
                P += (np.abs(np.fft.fft(seg, axis=1)) ** 2).mean(axis=0)
            fr = np.fft.fftfreq(nfft, 1.0 / args.rate)
            m = np.abs(fr) > 20e3
            f_tone = float(fr[int(np.argmax(np.where(m, P, 0)))])
            pres = tone_presence(x, args.rate, f_tone)
            table[f] = pres
            print("   %9.3f MHz  " % (f / 1e6) + "  ".join(
                "%7.1f%s" % (p, "*" if p >= 6 else " ") for p in pres))
        except Exception as e:
            print("   %9.3f MHz  failed: %s" % (f / 1e6, e))
        finally:
            proc.terminate()
            try: proc.wait(timeout=8)
            except Exception: proc.kill()
            time.sleep(1.5)

    print("")
    print("   * = tone received (>= 6 dB).  Summary:")
    for ch in range(NCH):
        ok = [f for f in table if table[f][ch] >= 6]
        if not ok:
            verdict = "DEAD at every frequency -- not connected"
        elif len(ok) == len(table):
            verdict = "good across the whole sweep"
        elif min(ok) > min(table):
            verdict = ("nothing below %.0f MHz, rising with frequency -- looks "
                       "like internal coupling from a fed channel on the same "
                       "board, not a cable" % (min(ok) / 1e6))
        else:
            verdict = ("received up to %.0f MHz, absent above -- out-of-band "
                       "part in this path" % (max(ok) / 1e6))
        print("     ch%d  %s" % (ch, verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
