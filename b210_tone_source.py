#!/usr/bin/env python3
"""
b210_tone_source.py -- CW calibration source on a USRP B210, for calibrating
the four RX channels of a USRP-2945.

Emits a continuous carrier at (--freq + --offset).  Run it in one terminal,
then run twinrx_lo_check.py --freq <same --freq> in another.

  B210 TX/RX --> 30 dB pad --> 4-way splitter --> the four 2945 RX ports
                 ^^^^^^^^^^
                 not optional; see the level budget printed at startup

The tone is deliberately offset from the centre frequency.  At baseband the
2945 then sees LO self-mixing leakage at DC and the real tone at +offset,
and twinrx_lo_check.py's DC guard can tell them apart.  A tone sitting at
DC is indistinguishable from leakage and produces a confident wrong answer.

Run this under whatever UHD has b2xx images -- usually the SYSTEM one, so
do NOT source the 3.15 environment for this script.  The 2945 tooling is
the opposite: it must run under ~/uhd-3.15.

  python3 b210_tone_source.py --freq 2.4e9 --gain 0        # start cold
  python3 b210_tone_source.py --freq 2.4e9 --gain 50       # after ramping

Ctrl-C to stop.
"""

import argparse
import math
import os
import signal
import sys

import numpy as np
import uhd

# B210 output at maximum TX gain, used only for the rough level estimate
# printed at startup.  Real figure is +10..+16 dBm depending on frequency.
B210_PMAX_DBM = 10.0


def check_environment():
    """Report which UHD this is running under, and verify B210 images exist.

    Unlike the 2945, the B210 is NOT tied to UHD 3.15.  The X310's FPGA is
    built for compat 36 and UHD 4.x would demand a reflash, so
    twinrx_lo_check.py refuses anything but the 3.15 install.  The B210
    loads its firmware and FPGA over USB at every open, so whatever UHD is
    present is fine as long as it ships matching images.

    In practice that means this script runs happily under the SYSTEM UHD
    (which has b2xx images) while the 2945 tooling runs under ~/uhd-3.15
    (which does not).  Two terminals, two environments, no conflict.
    """
    where = os.path.abspath(uhd.__file__)
    isolated = os.environ.get("UHD315_DIR")
    tagged = "isolated 3.15" if (isolated and where.startswith(
        os.path.abspath(isolated))) else "system"

    # UHD looks here unless UHD_IMAGES_DIR overrides it.
    candidates = []
    if os.environ.get("UHD_IMAGES_DIR"):
        candidates.append(os.environ["UHD_IMAGES_DIR"])
    candidates += [os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(where))), "share", "uhd", "images"),
        "/usr/share/uhd/images", "/usr/local/share/uhd/images"]

    need = ["usrp_b200_fw.hex", "usrp_b210_fpga.bin"]
    found_in = None
    for d in candidates:
        if all(os.path.isfile(os.path.join(d, f)) for f in need):
            found_in = d
            break

    print("  UHD in use   : %s  (%s)" % (where, tagged))
    if found_in:
        print("  B210 images  : %s" % found_in)
        if os.environ.get("UHD_IMAGES_DIR") != found_in and \
                found_in not in candidates[:1]:
            os.environ["UHD_IMAGES_DIR"] = found_in
        return

    sys.stderr.write(
        "\nERROR: B210 firmware images not found.\n\n"
        "  Needed : %s\n"
        "  Looked : %s\n\n"
        "  The B210 loads its firmware and FPGA over USB every time it is\n"
        "  opened, so these files must exist on disk.\n\n"
        "  If a UHD on this machine already has them, run this script under\n"
        "  that UHD instead -- the B210 is not tied to any particular\n"
        "  version. Otherwise fetch them with that install's\n"
        "  uhd_images_downloader.\n\n"
        "  Do NOT reflash the X310 to make versions match; its FPGA is\n"
        "  built for UHD 3.15 and the 2945 tooling depends on that.\n\n"
        % (", ".join(need), "\n           ".join(candidates)))
    sys.exit(2)


def parse_args():
    p = argparse.ArgumentParser(
        description="CW calibration source on a B210, for the USRP-2945 RX array",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--args", default="type=b200",
                   help="UHD device args for the B210")
    p.add_argument("--freq", type=float, default=2.4e9,
                   help="TX centre frequency (Hz) -- match the 2945's --freq")
    p.add_argument("--offset", type=float, default=200e3,
                   help="baseband tone offset from centre (Hz). Keep it well "
                        "outside twinrx_lo_check.py's --tone-guard")
    p.add_argument("--rate", type=float, default=1e6,
                   help="TX sample rate (Sps)")
    p.add_argument("--gain", type=float, default=0.0,
                   help="TX gain (dB). START AT 0 and ramp in 10 dB steps")
    p.add_argument("--max-gain", type=float, default=60.0,
                   help="refuse to start above this gain, so a typo cannot "
                        "slam the TwinRX front ends")
    p.add_argument("--amplitude", type=float, default=0.8,
                   help="DAC amplitude, 0..1. 0.8 keeps ~2 dB of digital "
                        "headroom against clipping. Measured on this rig, "
                        "spurs FALL in dBc as amplitude rises (the worst one "
                        "sits at a fixed +5.9 kHz offset, not at the IQ image "
                        "or a harmonic), so headroom -- not spurs -- is what "
                        "sets the ceiling")
    p.add_argument("--ant", default="TX/RX",
                   help="B210 TX antenna port")
    p.add_argument("--chan", type=int, default=0,
                   help="B210 TX channel (0 = RF A)")
    p.add_argument("--pad", type=float, default=30.0,
                   help="fixed attenuator between the B210 and the splitter "
                        "(dB). Used for the level estimate; set to what you "
                        "physically installed")
    p.add_argument("--split-loss", type=float, default=7.0,
                   help="4-way splitter loss (dB): ~6 dB split + insertion")
    return p.parse_args()


def level_budget(args, gain_max):
    """Rough per-port level at the 2945. Order of magnitude, not calibrated."""
    backoff = max(0.0, gain_max - args.gain)
    tx_out = B210_PMAX_DBM - backoff + 20 * math.log10(max(args.amplitude, 1e-9))
    at_port = tx_out - args.pad - args.split_loss
    worst = B210_PMAX_DBM - args.pad - args.split_loss   # if gain slipped to max
    return tx_out, at_port, worst


def make_tone(rate, offset, amplitude):
    """One buffer holding a whole number of cycles, so it loops seamlessly.

    If the buffer does not contain an integer number of tone cycles there is
    a phase discontinuity at every wrap, which sprays energy across the band
    and shows up as a raised noise floor in the measurement.
    """
    r, o = int(round(rate)), int(round(abs(offset)))
    if o == 0:
        raise ValueError("--offset must not be 0: a tone at DC cannot be "
                         "distinguished from LO leakage")
    period = r // math.gcd(r, o)          # samples per whole cycle count
    n = period
    while n < 10000:                       # pad out to a sensible buffer size
        n += period
    t = np.arange(n, dtype=np.float64)
    sig = amplitude * np.exp(2j * np.pi * (offset / rate) * t)
    return sig.astype(np.complex64), n, period


def main():
    args = parse_args()

    if args.amplitude <= 0 or args.amplitude > 1.0:
        print("--amplitude must be in (0, 1]")
        return 1
    if args.gain > args.max_gain:
        print("")
        print("REFUSING TO START: --gain %.1f dB exceeds --max-gain %.1f dB."
              % (args.gain, args.max_gain))
        print("")
        print("  The TwinRX damage threshold is +10 dBm and its ADC hits full")
        print("  scale at -20 dBm even at minimum RX gain. Ramp up in 10 dB")
        print("  steps and stop when the tone is 30-40 dB above the noise")
        print("  floor. If you really need more, raise --max-gain knowingly.")
        return 1

    print("")
    check_environment()
    print("Opening B210 (%s) ..." % args.args)
    usrp = uhd.usrp.MultiUSRP(args.args)

    grange = usrp.get_tx_gain_range(args.chan)
    gain_max = grange.stop()

    usrp.set_tx_rate(args.rate, args.chan)
    usrp.set_tx_antenna(args.ant, args.chan)
    usrp.set_tx_freq(uhd.types.TuneRequest(args.freq), args.chan)
    usrp.set_tx_gain(args.gain, args.chan)

    tone, nsamps, period = make_tone(usrp.get_tx_rate(args.chan),
                                     args.offset, args.amplitude)
    tx_out, at_port, worst = level_budget(args, gain_max)

    print("")
    print("=" * 72)
    print("B210 CW calibration source")
    print("=" * 72)
    info = usrp.get_usrp_tx_info(args.chan)
    print("  device       : %s / %s" % (info.get("mboard_id", "?"),
                                        info.get("tx_id", "?")))
    print("  TX centre    : %.6f MHz  (actual %.6f MHz)"
          % (args.freq / 1e6, usrp.get_tx_freq(args.chan) / 1e6))
    print("  tone at      : centre %+.1f kHz  =  %.6f MHz"
          % (args.offset / 1e3, (usrp.get_tx_freq(args.chan) + args.offset) / 1e6))
    print("  sample rate  : %.3f Msps" % (usrp.get_tx_rate(args.chan) / 1e6))
    print("  TX gain      : %.1f dB  (range 0 .. %.1f dB, ceiling %.1f)"
          % (usrp.get_tx_gain(args.chan), gain_max, args.max_gain))
    print("  amplitude    : %.2f of full scale" % args.amplitude)
    print("  buffer       : %d samples, %d per cycle -- loops seamlessly"
          % (nsamps, period))
    print("")
    print("  Estimated levels (rough -- assumes %.0f dBm at max TX gain):"
          % B210_PMAX_DBM)
    print("    B210 output            ~ %+7.1f dBm" % tx_out)
    print("    after %.0f dB pad        ~ %+7.1f dBm" % (args.pad, tx_out - args.pad))
    print("    after %.0f dB split      ~ %+7.1f dBm   <- at each 2945 RX port"
          % (args.split_loss, at_port))
    print("")
    print("    TwinRX full scale at min RX gain : -20.0 dBm")
    print("    TwinRX damage threshold          : +10.0 dBm")
    print("    if TX gain slipped to maximum    : %+.1f dBm per port" % worst)
    if worst > -20.0:
        print("    !! WARNING: at max TX gain a port would exceed full scale.")
        print("       Fit more attenuation, or lower --max-gain.")
    if args.pad <= 0:
        print("    !! WARNING: no pad declared. Fit a fixed attenuator between")
        print("       the B210 and the splitter -- it is the only thing")
        print("       protecting the TwinRX from a mistyped gain.")
    if at_port > -20.0:
        print("    !! WARNING: estimated port level is above TwinRX full scale.")
        print("       Reduce --gain before trusting any measurement.")
    print("")
    print("  Now run, in another terminal:")
    print("    source ~/gnuradio-3.8/setup_env.sh")
    print("    python3 ~/radar2/twinrx_lo_check.py --freq %g --trials 3" % args.freq)
    print("")
    print("  Ctrl-C to stop transmitting.")
    print("=" * 72)
    print("")

    st = uhd.usrp.StreamArgs("fc32", "sc16")
    st.channels = [args.chan]
    streamer = usrp.get_tx_stream(st)

    md = uhd.types.TXMetadata()
    md.start_of_burst = True
    md.end_of_burst = False
    md.has_time_spec = False

    buf = tone.reshape(1, -1)
    running = [True]

    def stop(signum, frame):
        running[0] = False
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print("transmitting ...", flush=True)
    sent = 0
    try:
        while running[0]:
            sent += streamer.send(buf, md, 1.0)
            md.start_of_burst = False
    finally:
        md.end_of_burst = True
        try:
            streamer.send(np.zeros((1, 1), dtype=np.complex64), md, 1.0)
        except Exception:
            pass
        print("")
        print("stopped. %.1f Msamples transmitted." % (sent / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
