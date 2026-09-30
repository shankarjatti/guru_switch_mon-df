# twinrx-phase-drift-frequency-scaling

_USRP-2945 phase-offset drift scales with RF frequency (LO cable path length is the dominant error); offsets re-randomize on every power cycle, so calibration is per-session_

Measured on the hardware 2026-09-22 with a B210 CW tone, LO shared per
[usrp-2945-twinrx-lo-sharing](usrp-2945-twinrx-lo-sharing.md) (ch0/ch1 `external`, ch2 `internal`+export, ch3 `companion`).

**Drift scales linearly with RF frequency** — the dominant error term is physical
path length (`φ = 2π·ΔL·f/c`), not LO phase noise or clock instability:

| RF freq | drift over time |
|---|---|
| 2.4 GHz | ~1° |
| 5.1 GHz | ~2° (matches the 2.125× prediction) |
| 5.8 GHz | ~4° (worse than the 2.417× prediction — suspect LO drive falling off from cable loss near the 6 GHz band edge) |

**Only pairs that cross the LO cable drift.** `ch1 − ch0` stays tight because both
channels sit on board A and share the same arriving LO — the cable is common-mode and
cancels. `ch2 − ch0` and `ch3 − ch0` compare board B's local LO against board A's
cable-delivered LO, so the cable's thermal drift enters differentially.

**Absolute offsets do not survive a power cycle.** On re-lock the board-A↔board-B LO
phase settles somewhere new — observed a ~40° jump, with ch2 and ch3 moving *together*
to within 0.9° (intra-board relationships hold, inter-board does not). Within a session
they are stable to ~1°.

**Why:** this is why gr-doa ships a separate estimate-and-save app rather than hardcoding
constants — `doa.phase_correct_hier` reads `twinrx_phase_offsets.cfg` (radians, one line
per non-reference channel) **once at `__init__`**, so editing the file needs a flowgraph
restart to take effect.

**How to apply:** recalibrate after every power-up, and roughly twice as often at 5+ GHz
as at 2.4 GHz. Do not chase the residual with a live/closed-loop tracker — for DoA the
inter-channel phase *is* the signal, so continuously nulling it would null the measurement.
Better LO cabling (shorter, phase-stable coax) is the highest-value fix; a fan blowing
unevenly across the cables can make drift worse by creating gradients along them.
Estimate phase on the band-pass filtered streams, not raw wideband samples — the
narrower band cuts estimator variance substantially.
