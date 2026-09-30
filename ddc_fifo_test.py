#!/usr/bin/env python3
"""Does the DDC command FIFO still fill up?

The stall is a count, not a time: the radio died after 70, 72 and 74 hops
across three runs, because every timed tune stranded one command in DDC_0's
command FIFO, which holds CMD_FIFO_SIZE / MAX_CMD_PKT_SIZE = 256/3 = 85. A
DDC accepts a timestamped command but has no clock that ever reaches the
timestamp, so the command is queued and never retires.

Waiting for that through the flowgraph takes about thirteen minutes, because
each hop dwells. Nothing about the failure needs the dwell -- or a
transmitter, or even a running stream -- so this just tunes as fast as the
radio will accept it. The same 85 commands then take seconds.

    source ~/gnuradio-3.8/setup_env.sh
    ./ddc_fifo_test.py                 # 400 tunes, ~5x the old budget

PASS means the budget does not exist any more. A failure prints the tune
number it happened on: if that is near 85 the fix did not take, and if it is
much larger the leak was slowed rather than stopped -- a different bug.

A failure leaves the X310 needing a power cycle, exactly as the real fault
does. That is the nature of the fault, not something this test adds.
"""
import argparse
import sys
import time

from gnuradio import gr
import doa


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tunes", type=int, default=400)
    ap.add_argument("--freqs", default="2.4e9,5.2e9,5.8e9")
    ap.add_argument("--rate", type=float, default=1e6)
    ap.add_argument("--gain", type=float, default=46)
    a = ap.parse_args()

    freqs = [float(f) for f in a.freqs.split(",")]
    budget = 256 // 3

    print("opening the X310 ...", flush=True)
    src = doa.twinrx_usrp_source(
        samp_rate=a.rate, center_freq=freqs[0], gain=a.gain, sources=4,
        addresses="type=x300", lo_export_direction="B")
    print("open. tuning %d times across %s"
          % (a.tunes, ", ".join("%.1f GHz" % (f / 1e9) for f in freqs)),
          flush=True)
    print("the old budget was %d commands; failure used to arrive at ~72 hops\n"
          % budget, flush=True)

    t0 = time.time()
    for i in range(1, a.tunes + 1):
        f = freqs[i % len(freqs)]
        try:
            src.set_center_freq(int(f), 4)
        except Exception as e:
            dt = time.time() - t0
            print("\nFAIL on tune %d of %d after %.1f s\n  %s"
                  % (i, a.tunes, dt, e), flush=True)
            if i <= budget + 10:
                print("\nThat is the old budget (%d). The DDC is still being "
                      "given timestamped\ncommands -- the fix did not take."
                      % budget)
            else:
                print("\nThat is well past the old budget (%d), so the leak "
                      "was slowed rather\nthan stopped. Something else is "
                      "still stranding commands." % budget)
            print("The X310 will need a power cycle before the next run.")
            return 1
        if i % 50 == 0:
            print("  %3d tunes clean  (%.1f s)" % (i, time.time() - t0),
                  flush=True)

    dt = time.time() - t0
    print("\nPASS -- %d tunes, no failure, %.1f s" % (a.tunes, dt))
    print("That is %.1fx the old %d-command budget. Nothing is accumulating."
          % (a.tunes / float(budget), budget))
    return 0


if __name__ == "__main__":
    sys.exit(main())
