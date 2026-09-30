"""
Gain-dependent phase correction for the TwinRX chains.

The TwinRX variable-gain stage shifts phase as well as amplitude, and the four
chains do not do it identically, so one fixed offset per channel is only valid
at the gain it was measured at.  This reads the measured gain->offset table
produced by calibrate_phase_vs_gain.py and returns the rotation to apply at
whatever gain the flowgraph is currently set to.

Sign convention matches doa.twinrx_phase_offset_est / doa.phase_correct_hier:
theta_k = angle(ch0) - angle(ch_k), and the correction is exp(+j*theta_k).
"""

import os
import sys

import numpy

_HERE = os.path.dirname(os.path.abspath(__file__))
CAL_FILE = os.path.join(_HERE, "twinrx_phase_vs_gain.cfg")
# The LO dividers relock at a new phase every time the device is opened or
# retuned, which shifts every channel's baseline by a few degrees to tens of
# degrees.  The table above captures how phase varies WITH GAIN, which is
# stable; this file carries the one constant per channel for the current
# session.  Read the residual off guru's readout, convert to radians, put it
# here, restart.  Absent or empty means no session offset.
ZERO_FILE = os.path.join(_HERE, "twinrx_session_zero.cfg")

_table = None
_zero = None


def _load():
    """Returns (gains, thetas[3][n]) with each theta unwrapped, or None."""
    global _table
    if _table is not None:
        return _table

    gains, cols = [], [[], [], []]
    try:
        with open(CAL_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 4:
                    continue
                gains.append(float(parts[0]))
                for k in range(3):
                    cols[k].append(float(parts[k + 1]))
    except IOError:
        sys.stderr.write(
            "twinrx_gain_phase_cal: no calibration at %s -- running with no "
            "phase correction.  Run calibrate_phase_vs_gain.py.\n" % CAL_FILE)
        _table = (None, None)
        return _table

    if len(gains) < 1:
        sys.stderr.write("twinrx_gain_phase_cal: %s has no data points.\n"
                         % CAL_FILE)
        _table = (None, None)
        return _table

    g = numpy.array(gains, dtype=float)
    order = numpy.argsort(g)
    g = g[order]
    # Unwrap before interpolating: a jump across +/-pi would otherwise
    # interpolate the long way round and give a meaningless angle.
    th = [numpy.unwrap(numpy.array(cols[k], dtype=float)[order])
          for k in range(3)]
    _table = (g, th)
    return _table


def _session_zero():
    """Three constants, radians, or zeros if the file is absent."""
    global _zero
    if _zero is not None:
        return _zero
    vals = []
    try:
        with open(ZERO_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    vals.append(float(line.split()[0]))
    except IOError:
        pass
    while len(vals) < 3:
        vals.append(0.0)
    _zero = vals[:3]
    return _zero


def phase_rot(gain, channel):
    """Complex rotation to apply to `channel` (1..3) at this RX `gain`."""
    g, th = _load()
    if g is None:
        return complex(1.0, 0.0)
    theta = float(numpy.interp(float(gain), g, th[channel - 1]))
    theta += _session_zero()[channel - 1]
    return complex(numpy.exp(1j * theta))


def phase_deg(gain, channel):
    """The calibrated offset in degrees, for display/inspection."""
    g, th = _load()
    if g is None:
        return 0.0
    theta = float(numpy.interp(float(gain), g, th[channel - 1]))
    return float(numpy.degrees(theta + _session_zero()[channel - 1]))
