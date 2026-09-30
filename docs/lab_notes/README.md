# Lab notes

Short notes, one fact each, that were learned on this hardware over the whole project
(2026-09-18 → 2026-09-28) and kept up to date while working. Each says what was measured,
why it matters and how to apply it.

| Note | In one line |
|---|---|
| [sdr-toolchain-isolated-env](sdr-toolchain-isolated-env.md) | GR 3.8 + UHD 3.15 at `~/gnuradio-3.8`, not the system GR 3.10 / UHD 4.x |
| [usrp-2945-twinrx-lo-sharing](usrp-2945-twinrx-lo-sharing.md) | working LO routing (Rx B exports), double tune, why a steady phase proves nothing |
| [twinrx-phase-drift-frequency-scaling](twinrx-phase-drift-frequency-scaling.md) | drift scales with RF frequency (LO cable); offsets re-randomise every power cycle |
| [twinrx-lo1-lock-failure-5ghz](twinrx-lo1-lock-failure-5ghz.md) | cannot retune into 5.00–5.14 GHz; low-side fallback and its 180° caveat |
| [twinrx-ddc-timed-command-fifo](twinrx-ddc-timed-command-fifo.md) | never give a DDC a command time — it wedges the X310 after ~72 hops |
| [x310-rx-timestamp-2x-and-hop-timing](x310-rx-timestamp-2x-and-hop-timing.md) | radio-clock hopping rules, 2× packet timestamps, gr-uhd 180° flips, display spec |
| [guru-known-good-sources](guru-known-good-sources.md) | which copies of the code were good or stale, and the backups |
| [final-project-real-antennas](final-project-real-antennas.md) | final system uses antennas, not the HackRF; RTOS plan; open questions |
| [feedback-keep-work-log-md](feedback-keep-work-log-md.md) | every stage goes into `docs/WORK_LOG.md` as it happens |
| [feedback-permanent-real-solutions](feedback-permanent-real-solutions.md) | working rules: real measurements only, permanent fixes, stage updates |

Paths in the notes (`~/radar2/guru/...`) are where the files were on the lab PC; in this
repository they are at the top level.
