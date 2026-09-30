#!/usr/bin/env python3
"""
twinrx_lo_check.py -- USRP-2945 (X310 + 2x TwinRX) LO configuration & phase
coherence verifier.  Pure UHD 3.15 Python API, no GNU Radio needed.

Run it BEFORE the GRC flowgraph.  It answers three questions:

  1. Is the LO sharing hardware actually there?      (LO source enumeration)
  2. Does UHD accept my LO routing?                  (set + readback)
  3. Do the four channels stay phase-locked?         (measured phase offsets
                                                      over repeated retunes)

Feed a CW tone, split 4 ways with equal-length cables, into RX1/RX2 of both
TwinRX modules.  Offset the tone a little from the centre frequency (the
default is +200 kHz) so it does not sit in the DC notch.

  source ~/gnuradio-3.8/setup_env.sh
  python3 twinrx_lo_check.py --freq 2.4e9
  python3 twinrx_lo_check.py --freq 2.4e9 --sweep 1e9,2e9,3e9,4e9 --trials 5
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import uhd

ALL_LOS = "all"          # UHD 3.15 python does not export uhd.usrp.ALL_LOS
NCH = 4


def check_environment():
    """Refuse to run against the system UHD.

    The X310's FPGA image is built for UHD 3.15 (compat 36).  The system
    UHD 4.x on the default PATH wants compat 38 and bails out with a
    message telling you to reflash the FPGA.  Do NOT do that -- it would
    break the working 3.15 setup.  Source the isolated environment
    instead.
    """
    want = os.environ.get("UHD315_DIR")
    if want and os.path.abspath(uhd.__file__).startswith(os.path.abspath(want)):
        return
    sys.stderr.write(
        "\n"
        "ERROR: wrong UHD loaded.\n"
        "  imported uhd from : %s\n"
        "  expected under    : %s\n"
        "\n"
        "This machine has UHD 4.x on the default PATH.  Your X310 runs an\n"
        "FPGA image for UHD 3.15, so 4.x will demand you reflash it.\n"
        "Do not reflash.  Source the isolated environment first:\n"
        "\n"
        "  source ~/gnuradio-3.8/setup_env.sh\n"
        "\n" % (uhd.__file__, want or "~/uhd-3.15"))
    sys.exit(2)


# ----------------------------------------------------------------------------
# argument parsing
# ----------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="TwinRX / USRP-2945 LO configuration and phase-coherence check",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--args", default="type=x300",
                   help="UHD device args")
    p.add_argument("--subdev", default="A:0 A:1 B:0 B:1",
                   help="RX subdev spec (DB-A = ch0/ch1, DB-B = ch2/ch3)")
    p.add_argument("--freq", type=float, default=2.4e9,
                   help="RF centre frequency (Hz)")
    p.add_argument("--sweep", default="",
                   help="comma separated frequency list; retunes between trials "
                        "to prove the phase offset is repeatable")
    p.add_argument("--rate", type=float, default=1e6,
                   help="sample rate per channel (Sps)")
    p.add_argument("--gain", type=float, default=30.0,
                   help="RX gain, dB (TwinRX range is 0..93)")
    p.add_argument("--nsamps", type=int, default=100000,
                   help="samples per measurement")
    p.add_argument("--trials", type=int, default=3,
                   help="how many times to retune and re-measure")
    p.add_argument("--export-chan", type=int, default=2,
                   help="channel whose synthesiser is exported (0 or 2)")
    p.add_argument("--lo-sources", default="external,external,internal,companion",
                   help="per-channel LO source, ch0..ch3. "
                        "Valid: internal, companion, external, reimport, disabled")
    p.add_argument("--cmd-lead", type=float, default=0.1,
                   help="how far ahead timed commands are scheduled (s)")
    p.add_argument("--no-dsp-manual", action="store_true",
                   help="let UHD use the DDC; by default every DDC is pinned to "
                        "0 Hz so only the shared LO sets the phase")
    p.add_argument("--tone-guard", type=float, default=20e3,
                   help="exclude +/- this many Hz around DC when hunting for the "
                        "tone, so LO self-mixing at 0 Hz cannot be mistaken for "
                        "your signal")
    p.add_argument("--broadband", action="store_true",
                   help="average the whole band instead of picking the tone bin. "
                        "Only valid with a broadband noise source, and it lets "
                        "the DC offset contribute")
    p.add_argument("--min-snr", type=float, default=10.0,
                   help="warn if the detected tone is weaker than this (dB)")
    p.add_argument("--cal-file", default="~/radar2/twinrx_lo_cal.json",
                   help="where measured offsets are stored and compared against")
    p.add_argument("--no-save", action="store_true",
                   help="measure and compare, but do not update the cal file")
    p.add_argument("--port-scan", action="store_true",
                   help="measure tone SNR with every channel on RX1 and then on "
                        "RX2, to find which antenna connectors are actually fed. "
                        "A channel weak on BOTH ports has no cable; a channel "
                        "much stronger on the other port is plugged in wrong")
    p.add_argument("--no-retune", action="store_true",
                   help="tune once, then repeat the measurement without "
                        "reprogramming the LO. Separates 'the divider re-rolls "
                        "on every tune' from 'the phase drifts continuously'")
    p.add_argument("--single-tune", action="store_true",
                   help="tune once instead of twice (expect FIFO overflow on a "
                        "cold tune -- this switch exists to demonstrate the bug)")
    return p.parse_args()


# ----------------------------------------------------------------------------
# step 1 -- what does the hardware say it can do?
# ----------------------------------------------------------------------------
def report_capabilities(usrp):
    print("")
    print("=" * 72)
    print("STEP 1  Hardware / LO capability report")
    print("=" * 72)
    info = usrp.get_usrp_rx_info(0)
    print("  motherboard  : %s" % info.get("mboard_id", "?"))
    print("  daughterboard: %s" % info.get("rx_id", "?"))
    print("  master clock : %.6f MHz  (TwinRX requires 200 MHz)"
          % (usrp.get_master_clock_rate() / 1e6))
    print("  rx channels  : %d" % usrp.get_rx_num_channels())

    if "TwinRX" not in str(info.get("rx_id", "")):
        print("  !! rx_id does not mention TwinRX -- LO sharing will not work.")

    for ch in range(NCH):
        names = list(usrp.get_rx_lo_names(ch))
        srcs = list(usrp.get_rx_lo_sources(ALL_LOS, ch))
        print("  ch%d  LOs=%-14s sources=%s" % (ch, names, srcs))
        if "external" not in srcs:
            print("       !! this channel cannot take an external LO")
    print("")
    print("  Expect LOs = ['LO1', 'LO2'] and sources to include")
    print("  internal / external / companion / reimport / disabled.")
    print("  If the list is empty or just ['internal'], the daughterboard is")
    print("  not a TwinRX, or UHD did not probe it as one.")


# ----------------------------------------------------------------------------
# step 2 -- program the LO routing.  Order matters.
# ----------------------------------------------------------------------------
def configure_lo(usrp, lo_sources, export_chan):
    print("")
    print("=" * 72)
    print("STEP 2  LO routing")
    print("=" * 72)

    # (a) clear every export first.  UHD throws "Cannot export LOs for both
    #     channels" if two channels on one board ever export at once, even
    #     transiently, so never re-assert on top of an unknown state.
    for ch in range(NCH):
        usrp.set_rx_lo_export_enabled(False, ALL_LOS, ch)

    # (b) set the source of every channel.  Do this BEFORE enabling the
    #     export: UHD refuses "external" + export ("Cannot export an
    #     external LO for channel N").
    for ch in range(NCH):
        usrp.set_rx_lo_source(lo_sources[ch], ALL_LOS, ch)

    # (c) exactly one exporter drives the whole system.
    usrp.set_rx_lo_export_enabled(True, ALL_LOS, export_chan)

    ok = True
    for ch in range(NCH):
        got = usrp.get_rx_lo_source(ALL_LOS, ch)
        exp = usrp.get_rx_lo_export_enabled(ALL_LOS, ch)
        want_exp = (ch == export_chan)
        flag = "" if (got == lo_sources[ch] and exp == want_exp) else "   <-- MISMATCH"
        ok = ok and not flag
        print("  ch%d  want=%-10s got=%-10s export=%-5s%s"
              % (ch, lo_sources[ch], got, exp, flag))
    if not ok:
        print("  !! readback differs from request -- check cabling and subdev spec")
    return ok


# ----------------------------------------------------------------------------
# step 3 -- coherent, timed tuning
# ----------------------------------------------------------------------------
def coherent_tune(usrp, freq, cmd_lead, dsp_manual, passes):
    """Land every channel's LO write on the same clock edge.

    A cold TwinRX tune emits more SPI transactions than the X310 command
    FIFO (16 entries) can hold, so part of the first timed burst executes
    untimed.  The driver caches band, filter and synthesiser state, so an
    immediately repeated, identical burst is short enough to fit and lands
    atomically.  That is why the default is two passes.
    """
    tr = uhd.types.TuneRequest(float(freq))
    if dsp_manual:
        # Pin every DDC to 0 Hz.  Then the digital stage contributes no
        # per-channel phase and any offset you measure is purely RF.
        tr.rf_freq_policy = uhd.types.TuneRequestPolicy.auto
        tr.dsp_freq_policy = uhd.types.TuneRequestPolicy.manual
        tr.dsp_freq = 0.0

    for _ in range(passes):
        usrp.set_command_time(usrp.get_time_now() + uhd.types.TimeSpec(cmd_lead))
        for ch in range(NCH):
            usrp.set_rx_freq(tr, ch)
        usrp.clear_command_time()
        time.sleep(cmd_lead + 0.05)

    return [usrp.get_rx_freq(ch) for ch in range(NCH)]


# ----------------------------------------------------------------------------
# step 4 -- capture and measure
# ----------------------------------------------------------------------------
def capture(usrp, streamer, nsamps):
    """Timed, aligned burst on all four channels."""
    spb = streamer.get_max_num_samps()
    buf = np.zeros((NCH, spb), dtype=np.complex64)
    out = np.zeros((NCH, nsamps), dtype=np.complex64)
    md = uhd.types.RXMetadata()

    cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_done)
    cmd.num_samps = nsamps
    cmd.stream_now = False
    cmd.time_spec = usrp.get_time_now() + uhd.types.TimeSpec(0.1)
    streamer.issue_stream_cmd(cmd)

    got = 0
    while got < nsamps:
        n = streamer.recv(buf, md, 1.0)
        if md.error_code != uhd.types.RXMetadataErrorCode.none:
            raise RuntimeError("streamer error: %s" % md.strerror())
        if n == 0:
            raise RuntimeError("streamer timed out")
        take = min(n, nsamps - got)
        out[:, got:got + take] = buf[:, :take]
        got += take
    return out


def wrap180(deg):
    """Fold a degree difference into (-180, 180]."""
    return (float(deg) + 180.0) % 360.0 - 180.0


def load_cal(path):
    try:
        with open(os.path.expanduser(path)) as fh:
            return json.load(fh)
    except (IOError, OSError, ValueError):
        return {}


def save_cal(path, means, lo_sources, export_chan, method="tone", gain=None):
    """Write the cal file atomically.

    Never open the real file with "w": that truncates the previous
    calibration the instant it is called, so a Ctrl-C part way through
    json.dump leaves a half-written file and the old data is gone.
    Serialise first, write to a sibling temp file, then rename -- rename
    is atomic on POSIX, so the file on disk is always either the old
    complete version or the new complete version.
    """
    path = os.path.expanduser(path)
    data = load_cal(path)
    for freq, offs in means.items():
        entry = {
            "measured": time.strftime("%Y-%m-%d %H:%M:%S"),
            "offsets": [round(o, 3) for o in offs],
            "lo_sources": lo_sources,
            "export_chan": export_chan,
            "method": method,
        }
        if gain is not None:
            entry["gain_db"] = gain
        data["%.0f" % freq] = entry

    blob = json.dumps(data, indent=2, sort_keys=True) + "\n"
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as fh:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def tone_presence(samples, rate, f_tone, nblk=2048):
    """Per-channel dB of coherent power at f_tone over an off-tone reference.

    Roughly 0 dB means the channel is not receiving the tone.  A channel can
    still show a rock-steady phase with no tone at all, by correlating against
    the reference channel through internal crosstalk, so the phase verdict
    must be gated on this rather than on stability alone.
    """
    t = np.arange(samples.shape[1]) / rate
    nb = samples.shape[1] // nblk
    f_ref = f_tone + 53e3
    if abs(f_ref) > 0.45 * rate:
        f_ref = f_tone - 53e3

    def coh(ch, fq):
        m = samples[ch] * np.exp(-2j * np.pi * fq * t)
        return (np.abs(m[:nb * nblk].reshape(nb, nblk).mean(axis=1)) ** 2).mean()

    return [10 * np.log10(coh(c, f_tone) / max(coh(c, f_ref), 1e-30))
            for c in range(samples.shape[0])]



def measure_phases(samples, rate, guard_hz, broadband=False, nfft=8192):
    """Phase of each channel relative to ch0, in degrees.

    Default mode is TONE SELECTIVE: find the strongest bin in the averaged
    spectrum, excluding a guard band around DC, and take the cross-spectrum
    phase in that bin only.

    The DC guard matters.  Averaging the whole band instead (--broadband)
    lets the DC offset dominate: LO self-mixing puts a large term at 0 Hz
    in every channel, it is present at every tuned frequency whether or
    not a signal is connected, and its phase tracks the LO.  That produces
    a confident, stable, LO-coherent-looking number measured on leakage
    rather than on your signal -- true as a proof of LO sharing, useless
    as an RF path calibration.

    Returns (results, tone_offset_hz, tone_snr_db) where results is a list
    of (phase_deg, coherence, level_dbfs) per channel.
    """
    if broadband:
        ref = samples[0]
        res = []
        for ch in range(NCH):
            prod = samples[ch] * np.conj(ref)
            mean = prod.mean()
            norm = np.abs(mean) / (np.abs(prod).mean() + 1e-30)
            res.append((np.degrees(np.angle(mean)), norm,
                        20 * np.log10(np.abs(samples[ch]).mean() + 1e-30)))
        return res, float("nan"), float("nan")

    nfft = min(nfft, samples.shape[1])
    nseg = max(1, samples.shape[1] // nfft)
    win = np.hanning(nfft)

    # --- stage 1: LOCATE the tone (averaged power spectrum, DC guarded) ---
    power = np.zeros(nfft)
    for s in range(nseg):
        blk = samples[:, s * nfft:(s + 1) * nfft] * win
        power += (np.abs(np.fft.fft(blk, axis=1)) ** 2).sum(axis=0)
    power /= nseg

    freqs = np.fft.fftfreq(nfft, 1.0 / rate)
    usable = np.abs(freqs) > guard_hz
    if not usable.any():
        usable = np.ones(nfft, dtype=bool)
        usable[0] = False
    k = int(np.argmax(np.where(usable, power, 0.0)))
    snr_db = 10 * np.log10(power[k] / (np.median(power[usable]) + 1e-30))

    # Refine off-bin by parabolic interpolation on the log spectrum, so the
    # mixer below lands on the true tone rather than the nearest bin centre.
    km1, kp1 = (k - 1) % nfft, (k + 1) % nfft
    y0, y1, y2 = (np.log(power[km1] + 1e-30), np.log(power[k] + 1e-30),
                  np.log(power[kp1] + 1e-30))
    denom = y0 - 2 * y1 + y2
    delta = 0.5 * (y0 - y2) / denom if abs(denom) > 1e-30 else 0.0
    delta = float(np.clip(delta, -0.5, 0.5))
    f_tone = float(freqs[k] + delta * rate / nfft)

    # --- stage 2: MEASURE, by mixing the tone to DC and averaging ---
    #
    # The previous version accumulated cross-spectra F*conj(F[0]) across
    # segments and read the phase at bin k.  On real captures that was
    # unstable by tens to hundreds of degrees between back-to-back captures
    # of an unchanged signal, while this mix-and-average gave the same
    # answer to under a degree.  Measured side by side on the same data:
    #
    #     cap    FFT: ch1    ch2     ch3   |  mix: ch1   ch2     ch3
    #      0        +71.2  +93.7   -75.7   |      +7.2  -2.6  +117.6
    #      3        +81.3 -169.1  -155.2   |      +6.1  -3.2  +116.8
    #      5        +73.3 +105.9  -161.5   |      +5.8  -3.3  +116.7
    #
    # The FFT stays for locating the tone, which it does reliably.
    t = np.arange(samples.shape[1]) / rate
    mixed = samples * np.exp(-2j * np.pi * f_tone * t)

    ref = mixed[0]
    res = []
    for ch in range(NCH):
        prod = mixed[ch] * np.conj(ref)
        mean = prod.mean()
        coh = np.abs(mean) / (np.abs(prod).mean() + 1e-30)
        res.append((np.degrees(np.angle(mean)), min(1.0, coh),
                    10 * np.log10(samples[ch].var() + 1e-30)))
    return res, f_tone, float(snr_db)


# ----------------------------------------------------------------------------
def main():
    check_environment()
    args = parse_args()

    lo_sources = [s.strip() for s in args.lo_sources.split(",")]
    if len(lo_sources) != NCH:
        print("--lo-sources needs exactly %d comma separated entries" % NCH)
        return 1
    if lo_sources[args.export_chan] == "external":
        print("channel %d cannot both source 'external' and export"
              % args.export_chan)
        return 1

    freqs = ([float(f) for f in args.sweep.split(",")]
             if args.sweep else [args.freq])

    print("Opening %s ..." % args.args)
    usrp = uhd.usrp.MultiUSRP(args.args)
    usrp.set_rx_subdev_spec(uhd.usrp.SubdevSpec(args.subdev))
    usrp.set_clock_source("internal")
    usrp.set_time_source("internal")
    usrp.set_rx_rate(args.rate)
    for ch in range(NCH):
        usrp.set_rx_gain(args.gain, ch)
        usrp.set_rx_antenna("RX1" if ch % 2 == 0 else "RX2", ch)

    report_capabilities(usrp)
    configure_lo(usrp, lo_sources, args.export_chan)

    usrp.set_time_now(uhd.types.TimeSpec(0.0))

    st_args = uhd.usrp.StreamArgs("fc32", "sc16")
    st_args.channels = list(range(NCH))
    streamer = usrp.get_rx_stream(st_args)

    if args.port_scan:
        print("")
        print("=" * 72)
        print("PORT SCAN  which antenna connectors are actually fed?")
        print("=" * 72)
        coherent_tune(usrp, freqs[0], args.cmd_lead, not args.no_dsp_manual,
                      1 if args.single_tune else 2)
        rows = {}
        # NATIVE (ch0->RX1, ch1->RX2) versus SWAPPED (ch0->RX2, ch1->RX1).
        #
        # Do NOT scan by putting every channel on the same connector.
        # On TwinRX both channels of one board sharing an antenna engages
        # an internal resistive divider -- the manual warns of attenuation
        # and unpredictable gain -- so that measures the divider, not the
        # cabling, and it reported NO SIGNAL on channels that were tracking
        # phase to 1 degree. Native and swapped are both divider-free.
        for name, mapping in (("native ", ("RX1", "RX2", "RX1", "RX2")),
                              ("swapped", ("RX2", "RX1", "RX2", "RX1"))):
            for ch in range(NCH):
                usrp.set_rx_antenna(mapping[ch], ch)
            time.sleep(0.4)
            x = capture(usrp, streamer, args.nsamps)
            # Measure coherent power at the tone, and at an off-tone
            # reference frequency in the same band, and take the ratio.
            #
            # Three earlier metrics were wrong here and are worth
            # recording. Peak-picking each channel's own FFT was far less
            # sensitive than the real measurement. Mixing and averaging
            # the whole capture fails because a few Hz of residual
            # frequency error rotates a 100 ms mean to zero. Dividing the
            # coherent block power by the channel's TOTAL power fails
            # because LO self-mixing leakage at DC inflates the total: a
            # weak tone on big leakage then reads BELOW the noise floor,
            # which is how a channel tracking phase to 1 degree got
            # labelled "no signal". Offline, that case reads -35 dB by
            # that metric and +26 dB by this one, while a genuinely empty
            # channel reads about 0 dB either way.
            _, f_tone, _ = measure_phases(x, args.rate, args.tone_guard,
                                          args.broadband)
            tt = np.arange(x.shape[1]) / args.rate
            nblk = 2048
            nb = x.shape[1] // nblk

            def _coh_at(ch, fq):
                m = x[ch] * np.exp(-2j * np.pi * fq * tt)
                return (np.abs(m[:nb * nblk].reshape(nb, nblk)
                               .mean(axis=1)) ** 2).mean()

            # reference sits well off the tone but inside the passband
            f_ref = f_tone + 53e3
            if abs(f_ref) > 0.45 * args.rate:
                f_ref = f_tone - 53e3
            snrs = [10 * np.log10(_coh_at(ch, f_tone)
                                  / max(_coh_at(ch, f_ref), 1e-30))
                    for ch in range(NCH)]
            rows[name] = snrs
            print("    %s  " % name + "  ".join(
                "ch%d(%s) %6.1f dB" % (c, mapping[c], snrs[c])
                for c in range(NCH)))

        print("")
        for ch in range(NCH):
            a, b = rows["native "][ch], rows["swapped"][ch]
            nat = "RX1" if ch % 2 == 0 else "RX2"
            swp = "RX2" if ch % 2 == 0 else "RX1"
            if max(a, b) < 6:
                verdict = "nothing on either connector -- cable off?"
            elif b > a + 8:
                verdict = "STRONGER on %s -- your cable is on the wrong port" % swp
            else:
                verdict = "fed correctly on %s" % nat
            print("      ch%d  native(%s) %6.1f   swapped(%s) %6.1f   %s"
                  % (ch, nat, a, swp, b, verdict))
        # restore the normal mapping
        for ch in range(NCH):
            usrp.set_rx_antenna("RX1" if ch % 2 == 0 else "RX2", ch)
        time.sleep(0.3)

    print("")
    print("=" * 72)
    print("STEP 3/4  Coherent tune + phase measurement")
    print("=" * 72)
    print("  %d sample(s) per measurement, %.3f Msps, gain %.1f dB"
          % (args.nsamps, args.rate / 1e6, args.gain))

    passes = 1 if args.single_tune else 2
    history = {}
    presence = {}
    weak_tone = [False]

    for freq in freqs:
        for trial in range(args.trials):
            if trial == 0 or not args.no_retune:
                actual = coherent_tune(usrp, freq, args.cmd_lead,
                                       not args.no_dsp_manual, passes)
            samples = capture(usrp, streamer, args.nsamps)
            res, tone_hz, tone_snr = measure_phases(
                samples, args.rate, args.tone_guard, args.broadband)
            pres = tone_presence(samples, args.rate, tone_hz)
            presence.setdefault(freq, []).append(pres)

            print("")
            print("  f = %.6f MHz   trial %d/%d   (ch0 actual %.6f MHz)"
                  % (freq / 1e6, trial + 1, args.trials, actual[0] / 1e6))
            if args.broadband:
                print("    BROADBAND mode: whole band averaged, DC offset included")
            else:
                warn = "   <-- WEAK, see note below" if tone_snr < args.min_snr else ""
                print("    tone at %+9.1f kHz from centre, %5.1f dB above floor%s"
                      % (tone_hz / 1e3, tone_snr, warn))
                weak_tone[0] = weak_tone[0] or (tone_snr < args.min_snr)
            for ch in range(NCH):
                deg, conf, pwr = res[ch]
                print("    ch%d  phase vs ch0 = %+8.2f deg   coherence = %.3f"
                      "   level = %6.1f dBFS   tone %+6.1f dB%s"
                      % (ch, deg, conf, pwr, pres[ch],
                         "  <-- NO TONE" if pres[ch] < 6 else ""))
            history.setdefault(freq, []).append([r[0] for r in res])

    # ------------------------------------------------------------------
    print("")
    print("=" * 72)
    print("VERDICT")
    print("=" * 72)
    print("  (A) WITHIN THIS SESSION -- does the offset survive a retune?")
    print("      'raw' is vs ch0.  'resid' has the per-trial common mode removed,")
    print("      so a wandering REFERENCE channel shows up as ch0 moving rather")
    print("      than as all three others moving together.")
    print("")
    worst_resid = 0.0
    worst_ref = 0.0
    means = {}
    for freq, rows in history.items():
        a = np.array(rows)                                  # trials x NCH, deg
        means[freq] = [0.0]
        # common mode = circular mean across all channels, per trial
        cm = np.angle(np.exp(1j * np.radians(a)).mean(axis=1))
        resid = np.degrees(np.angle(np.exp(1j * (np.radians(a) - cm[:, None]))))
        print("      %.3f MHz" % (freq / 1e6))
        for ch in range(NCH):
            col = np.unwrap(np.radians(a[:, ch]))
            raw = np.degrees(col.max() - col.min())
            rcol = np.unwrap(np.radians(resid[:, ch]))
            rsp = np.degrees(rcol.max() - rcol.min())
            mean = np.degrees(np.angle(np.exp(1j * col).mean()))
            if ch:
                means[freq].append(mean)
                worst_resid = max(worst_resid, rsp)
            else:
                worst_ref = max(worst_ref, rsp)
            print("          ch%d  mean %+8.2f   raw spread %6.2f   resid %6.2f%s"
                  % (ch, mean, raw, rsp,
                     "   <-- reference" if ch == 0 else ""))
    print("")
    dead = sorted({c for rows_ in presence.values() for r in rows_
                   for c in range(NCH) if r[c] < 6})
    if dead:
        print("")
        print("      NOT A VALID RESULT -- no tone on channel(s) %s."
              % ", ".join("ch%d" % c for c in dead))
        print("            Those channels still show a steady phase, but that")
        print("            is internal crosstalk from the channels that DO have")
        print("            signal: crosstalk is coherent with the reference, so")
        print("            it looks perfectly stable while telling you nothing")
        print("            about the RF path. Stability alone does not prove a")
        print("            channel is working.")
        print("")
        print("            Confirm it yourself: change the source gain by 10 dB.")
        print("            A channel with real signal moves 10 dB; one on")
        print("            crosstalk does not move at all.")
        print("")
        print("            BEFORE touching any RF cable, check the LO first.")
        print("            A channel on 'external' LO has no LO of its own: if")
        print("            the MMCX LO cables between the two TwinRX modules are")
        print("            loose, its mixers produce nothing no matter how much")
        print("            RF you feed them -- dead at every frequency, on both")
        print("            antenna ports, with a noise floor that cannot respond")
        print("            to gain. That looks exactly like a broken RF path.")
        print("")
        print("            Tell them apart in one command -- give every board its")
        print("            own LO, so no LO cable is needed:")
        print("")
        print("              python3 ~/radar2/twinrx_lo_check.py --freq %g \\"
              % freqs[0])
        print("                  --lo-sources internal,companion,internal,companion")
        print("")
        print("            If the channels receive that way, your RF cabling is")
        print("            fine and the LO cables are the fault: reconnect them")
        print("            crisscross, J1<->J2 and J3<->J4, between the modules.")
        print("            If they stay dead, then it really is the RF path.")
    elif not args.broadband and weak_tone[0]:
        # No coherent signal on the ports means the phase numbers above are
        # noise.  Saying FAIL here would send the user off checking LO cables
        # that are not the problem.
        print("      MEASUREMENT INVALID -- no tone was present.")
        print("            Differential spread came out %.2f deg, but that is"
              % worst_resid)
        print("            measured on noise, so it says nothing about the LO.")
        print("            Every trial locked onto a different random bin.")
        print("")
        print("            This is NOT evidence of an LO fault. It means no")
        print("            coherent signal reached the antenna ports. Start the")
        print("            calibration source and run this again:")
        print("")
        print("              python3 ~/radar2/b210_tone_source.py \\")
        print("                  --freq %g --gain 40 --pad <your pad dB>" % freqs[0])
        print("")
        print("            If earlier runs looked coherent and this one does not,")
        print("            those runs were measuring LO self-mixing leakage at DC,")
        print("            which this build now excludes on purpose.")
    elif worst_resid < 5.0:
        print("      PASS  channels hold %.2f deg against each other. LO is shared."
              % worst_resid)
    elif worst_resid < 300.0 and min(abs(worst_resid - k)
                                     for k in (90, 180, 270)) < 25:
        print("      MARGINAL  differential spread %.2f deg, near a multiple of 90."
              % worst_resid)
        print("            The LO IS shared; a receiving board is re-rolling its")
        print("            divider quadrant between tunes. See (B).")
    else:
        print("      FAIL  differential spread %.2f deg. The channels are moving"
              % worst_resid)
        print("            independently, so they are on separate synthesisers.")
        print("            Check: LO cables J1<->J2 and J3<->J4 crisscrossed")
        print("            between the two TwinRX modules, the subdev spec, and")
        print("            that the slave board has BOTH channels on 'external'.")

    if worst_ref > 5.0:
        print("")
        print("      NOTE  the reference channel ch0 wandered %.2f deg by itself."
              % worst_ref)
        print("            That is not an LO fault -- the other channels stayed")
        print("            locked to each other -- but if ch0 is a real array")
        print("            element it is still %.0f deg of array error. Check its"
              % worst_ref)
        print("            RF cable, connector and source level.")

    if False:
        print("")
        print("      WARNING  at least one measurement had no strong tone.")
        print("            With nothing coherent on the antenna ports, the only")
        print("            thing correlated across channels is LO self-mixing")
        print("            leakage at DC. That still proves the LO is shared, but")
        print("            it is NOT a valid RF path calibration -- do not load")
        print("            those offsets into gr-aoa. Inject a CW tone through a")
        print("            4-way splitter with equal-length cables, offset a few")
        print("            hundred kHz from the centre frequency.")

    # ------------------------------------------------------------------
    # (B) Cross-session.  The absolute phase of a board sourcing 'external'
    #     re-rolls whenever its LO is re-programmed -- across process
    #     restarts and power cycles, not just retunes.  Part (A) cannot see
    #     this because it only compares trials inside one process, so we
    #     keep a calibration file and diff against it.
    # ------------------------------------------------------------------
    print("")
    print("  (B) ACROSS SESSIONS -- is the offset the same as last time?")
    prev = load_cal(args.cal_file)
    reroll = False
    skipped = False
    for freq in sorted(means):
        key = "%.0f" % freq
        entry = prev.get(key, {})
        old = entry.get("offsets")
        if not old:
            print("      %.3f MHz  no previous measurement -- baseline saved."
                  % (freq / 1e6))
            continue
        old_method = entry.get("method", "unknown")
        old_gain = entry.get("gain_db")
        if old_method != ("broadband" if args.broadband else "tone"):
            print("      %.3f MHz  SKIPPED -- previous entry was measured by"
                  % (freq / 1e6))
            print("                  '%s', this run used '%s'. Those are not"
                  % (old_method, "broadband" if args.broadband else "tone"))
            print("                  comparable, so any delta would be noise.")
            if old_method == "broadband-legacy":
                print("                  ('broadband-legacy' predates the tone")
                print("                   estimator and was measured on DC")
                print("                   leakage. Re-measure to replace it.)")
            skipped = True
            continue
        if old_gain is not None and abs(float(old_gain) - args.gain) > 0.01:
            print("      %.3f MHz  SKIPPED -- previous entry was at %.1f dB RX"
                  % (freq / 1e6, float(old_gain)))
            print("                  gain, this run at %.1f dB. TwinRX gain is"
                  % args.gain)
            print("                  switched attenuators and each state has its")
            print("                  own phase, so the two are not comparable.")
            skipped = True
            continue
        print("      %.3f MHz   previous     now        delta" % (freq / 1e6))
        for ch in range(1, NCH):
            d = wrap180(means[freq][ch] - old[ch])
            near = min((abs(abs(d) - k), k) for k in (90, 180, 270))
            tag = ""
            if abs(d) > 15.0:
                reroll = True
                tag = ("   <-- quadrant re-roll (~%d deg)" % near[1]
                       if near[0] < 25 else "   <-- CHANGED")
            print("          ch%d    %+8.2f  %+8.2f   %+8.2f%s"
                  % (ch, old[ch], means[freq][ch], d, tag))

    if prev and reroll:
        print("")
        print("      Offsets moved since the last run. If the movers are the")
        print("      channels sourcing 'external', and they moved TOGETHER by")
        print("      roughly the same multiple of 90 deg, that is the known")
        print("      TwinRX behaviour, not a fault: the slave board's LO divider")
        print("      comes up in a random quadrant. The lock is fine; only the")
        print("      absolute phase is arbitrary.")
        print("")
        print("      Consequence: these numbers are NOT a permanent calibration.")
        print("      Re-measure at the start of every session and apply the")
        print("      result as a per-channel correction.")
    elif prev and not reroll and not skipped:
        print("")
        print("      Offsets match the previous run. Stable across sessions.")
    elif skipped:
        print("")
        print("      Nothing comparable to diff against. This run's numbers are")
        print("      now the baseline; the next run will report a real delta.")
        print("      Note that reseating any RF cable also changes the offsets,")
        print("      so re-baseline after touching the hardware.")

    if not args.no_save:
        save_cal(args.cal_file, means, lo_sources, args.export_chan,
                 method="broadband" if args.broadband else "tone",
                 gain=args.gain)
        print("")
        print("  Calibration written to %s" % args.cal_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
