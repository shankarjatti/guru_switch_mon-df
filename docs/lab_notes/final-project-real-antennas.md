# final-project-real-antennas

_The final radar2/guru system receives real signals through antennas; the HackRF is only a bench calibration source, so design decisions must not depend on it._

Stated by the user 2026-09-28: "in our final project we are not using hackrf, we'll receive real signal through antenna."

**Why:** the HackRF tone + splitter is only the bench setup used to measure and verify the phase table.
**How to apply:**
- Don't treat transmitter retune time as a dwell limit; tx_control will be empty in the final system.
- Calibration is the open problem: the table changes every X310 power cycle ([twinrx-phase-drift-frequency-scaling](twinrx-phase-drift-frequency-scaling.md)), and antenna/cable phase is not covered by splitter calibration. Suggested: startup reference tone via RF switch/coupler.
- Dwell must be chosen from the target signal (bands are Wi-Fi bands → bursty), not only from hardware limits ([guru-known-good-sources](guru-known-good-sources.md)).
- The user plans to move this setup to an RTOS later (said 2026-09-28; which RTOS not yet known). UHD/GNU Radio run on Linux incl. PREEMPT_RT but not on VxWorks/QNX/FreeRTOS — ask which before architecture decisions. Keep timing on the radio clock and the host-side timing logic small and portable to C/C++.
- **Next test (planned 2026-09-29): over the air.** Three transmitters (HackRF, B210, an X310) each stream one band continuously from ANOTHER PC; the user handles the sender side completely — I work on the receiver side only. The receiver must receive all three bands in their dwells with antennas and show phase coherence. Work in the copy `~/radar2/guru_ota`; `~/radar2/guru57` is the frozen safe copy (RESTORE.sh puts its blocks back).
- Still unknown as of 2026-09-28: target signal type, output (DOA/MUSIC vs detection), field calibration method.
