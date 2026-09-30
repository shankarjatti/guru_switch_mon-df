#!/usr/bin/env python3
"""Watch the X310's sample stream from outside the flowgraph.

The receiver can stop getting samples without saying anything: the plot goes
flat, the phase readouts freeze on their last value, and the process stays
alive spinning on a stream that has stopped. This samples the NIC counter once
a second so there is a timestamp for the moment it stopped, which can be lined
up against the receiver's own log.

It only reads /sys counters -- it never touches the radio.

    ./stall_watch.py                     # 4 channels at 1 Msps, enp3s0
    ./stall_watch.py --log /tmp/x310_stall.log
"""
import argparse, time, sys, os

ap = argparse.ArgumentParser()
ap.add_argument("--iface", default="enp3s0")
ap.add_argument("--rate", type=float, default=1e6, help="samples/s per channel")
ap.add_argument("--channels", type=int, default=4)
ap.add_argument("--log", default="")
ap.add_argument("--stall-after", type=float, default=2.0,
                help="seconds below 10%% of expected before calling it stalled")
a = ap.parse_args()

path = "/sys/class/net/%s/statistics/rx_bytes" % a.iface
if not os.path.exists(path):
    sys.exit("no such interface: %s" % a.iface)

# sc16 over the wire is 4 bytes per complex sample.
expect = a.rate * a.channels * 4.0
floor = expect * 0.10

out = open(a.log, "a", buffering=1) if a.log else None
def say(msg):
    line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    if out:
        out.write(line + "\n")

say("watching %s -- expecting %.1f MB/s (%d ch x %.0f ksps)"
    % (a.iface, expect / 1e6, a.channels, a.rate / 1e3))

rd = lambda: int(open(path).read())
prev, t_prev = rd(), time.time()
stalled = False
low_since = None
started = time.time()

try:
    while True:
        time.sleep(1.0)
        now, t_now = rd(), time.time()
        rate = (now - prev) / (t_now - t_prev)
        prev, t_prev = now, t_now

        if rate < floor:
            if low_since is None:
                low_since = t_now
            elif not stalled and (t_now - low_since) >= a.stall_after:
                stalled = True
                say("STREAM STOPPED -- %.2f MB/s, was expecting %.1f. "
                    "Ran for %s. The radio is no longer sending; the flowgraph "
                    "is still alive but has nothing to process."
                    % (rate / 1e6, expect / 1e6,
                       time.strftime("%H:%M:%S", time.gmtime(t_now - started))))
        else:
            if stalled:
                say("stream came back -- %.2f MB/s" % (rate / 1e6))
            stalled = False
            low_since = None
except KeyboardInterrupt:
    say("stopped watching")
