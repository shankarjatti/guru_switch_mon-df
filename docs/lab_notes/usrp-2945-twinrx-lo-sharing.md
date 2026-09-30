# usrp-2945-twinrx-lo-sharing

_radar2 is a USRP-2945 direction-finding project; working LO routing, the double-tune rule, and why phase stability alone proves nothing_

`~/radar2` is a git repo holding the LO configuration and phase-coherence tooling for
a **USRP-2945** (X310 `31082D8`, 2x TwinRX Rev B — `3104B3C` = Rx A, `31050CD` = Rx B),
heading toward direction finding with the `gr-aoa` OOT installed in the GR 3.8 tree.
`SESSION_LOG.md` in the repo records how it was built and every wrong turn.

Verified on the hardware 2026-09-19 against a B210 CW source:

- **Working LO routing — Rx B is the exporter**: ch0 `external`, ch1 `external`,
  ch2 `internal` + export, ch3 `companion`. Phase repeats to **1.5°** across
  retunes, versus 179° with each board on its own LO.
- **The A→B LO jumpers pass no LO; B→A works.** Both are cabled, so that pair is
  faulty, unseated, or joined out-to-out. LO export must reach LO *input*:
  J3→J4 for LO1, J1→J2 for LO2. Not blocking, but fix for redundancy.
- **Connector map (both boards identical):** J1 = LO2 OUT (3 dBm), J2 = LO2 IN, J3 = LO1 OUT (5 dBm), J4 = LO1 IN (10 dBm damage). Four crisscross cables: B J3→A J4 and B J1→A J2 (work, used); A J3→B J4 and A J1→B J2 (fitted, pass no LO — which of the two, or both, is not known: tested only with ALL_LOS). Ping-pong on board B needs only the two B→A cables (export switch picks ch2's or ch3's synth onto the same J3/J1). User asked (2026-09-28) to keep this map in mind when discussing LO designs. **Decision 2026-09-29: no ping-pong; keep exactly this setup (B the only master, one synthesiser retuned per hop)** — don't propose ping-pong / 4-synth designs again unless the user reopens it.
- **`reimport` does not work here** — it needs a splitter feeding the exporter's
  own LO IN; on crisscross wiring that port is fed by the other board.
- **Tuning must be timed and issued twice** — a cold TwinRX tune overflows the
  X310's 16-deep command FIFO.

**Why phase stability alone means nothing:** a channel receiving *no signal* still
correlates against the reference through internal crosstalk, which is coherent and
therefore perfectly steady. Three PASS results were reported this way before it was
caught (0.57°, 2.07°, 0.37° — all on dead channels). `lo_locked` is also useless as
evidence: it reads True on channels with no LO at all, because it reports on a
synthesiser an `external` channel does not have.

**How to apply:** always confirm tone presence per channel before believing a phase
result — `twinrx_lo_check.py` now gates its verdict on it, needing >6 dB. A
calibration source is mandatory; the tool only receives. If channels look dead,
**test the LO before touching RF cables** (`--lo-sources internal,companion,internal,companion`):
an `external` channel with no LO looks exactly like a broken RF path, and diagnosing
it backwards cost a full hardware rebuild here. Offsets are never permanent — they
shift with RX gain, across band edges, and whenever a cable is reseated.
See [sdr-toolchain-isolated-env](sdr-toolchain-isolated-env.md) for the environment.
