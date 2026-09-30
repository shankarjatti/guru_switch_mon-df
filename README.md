# guru_DF_v1 — USRP-2945 DF: 4 phase-coherent channels, shared LO, 5 ms dwell / 7 ms switching (FROZEN)

**Frozen safe copy of the DF work, 2026-09-30.** Do not edit; work in a copy. The MON work is
`~/radar2/guru_MON_v1`. Only one of the two can use the X310 at a time; each sets its own LO routing at start.

```bash
~/radar2/guru_DF_v1/RESTORE.sh --verify     # nothing in this folder has changed
~/radar2/guru_DF_v1/RESTORE.sh              # put this copy's blocks back into ~/gnuradio-3.8
cd ~/radar2/guru_DF_v1 && ./run_hop.sh --burst     # then CALIBRATE
```

= guru0930 (blocks, `guru_burst.grc/.py` identical) + the later fixes of 2026-09-30:
`hackrf_tone_source.py` re-execs itself after 3 failed restarts (a replugged HackRF never recovers in-process;
1843 failed retries seen), `run_hop.sh` pings the X310 3 times (one lost packet had stopped a launch).
**The X310 was power-cycled on 2026-09-30 15:10 → the stored phase table is invalid: CALIBRATE first.**
Known: ch0 (A/RX1) RF path 13–16 dB low (measured in MON mode, see guru_MON_v1); TIMING LOST after ~6 min
at 2 MS/s while the PC was busy (CPU headroom work pending).

USRP-2945 (X310 + 2× TwinRX, LO shared from board B) hopping **2.4 → 5.2 → 5.8 GHz**: each band **7 ms switching
(the X310 sends nothing) + 5 ms dwell**, cycle **36 ms**, timed on the X310 clock, **2 MS/s** (dwell = **10,000 samples**).
Lab source: HackRF, plain 200 kHz tone, pure source; everything shown is measured on the RX.

## What changed since guru57 (2026-09-30)
* `hackrf_tone_source.py`: after a stall the watchdog restart comes back on the band **last asked for**; restart and
  UDP commands share one lock (a stall during 5.8 GHz had come back on 2.4 GHz).
* `run_hop.sh`: `set +u` around `setup_env.sh` — with `LD_LIBRARY_PATH` unset the launcher stopped before the receiver.
* Blocks (`oot/`, `installed_snapshot/`) and `guru_burst.grc/.py` are **identical to guru57**.
* `results/`: all measurements up to 2026-09-30 (incl. over-the-air `ota_check_*`); `earlier_work/guru_ota/` holds the
  over-the-air tone-bin meter (NOT used here) and `ota_check.py`.

## Measured 2026-09-30 (cable, real-time priority 90 granted)
| | |
|---|---|
| Channel levels (tone over noise, no trim) | 2.4 GHz 84.7 / 95.1 / 94.4 / 94.8 dB; 5.2 GHz 91.3 / 97.8 / 97.8 / 97.0; 5.8 GHz 92.7 / 96.9 / 96.8 / 96.9 (ch0 4–10 dB lower) |
| Samples per dwell | **10,000** every dwell |
| 2.4 GHz phases (stored table) | ch1/ch2/ch3 +0.05 / +0.01 / +0.02°, max dev 0.08° |
| Timing | 0 late, 0 unlocked, 0 missing bursts; HackRF 0 TIMEOUTs after its restart |
| 5.2 / 5.8 GHz | cables were reseated → press CALIBRATE (startup values not near 0°) |

## Pending
* Long run (> 11 min) of the 2 MS/s flowgraph without TIMING LOST — a 15-min watch was running when this was frozen
  (see `docs/WORK_LOG.md`).
* Over-the-air: dwell-to-dwell jitter 2.3–3.1° while hopping vs < 1° continuous (work in `~/radar2/guru_ota`).
* X310 REF OUT → HackRF CLKIN; field calibration without HackRF.

## Contents
`guru_burst.grc/.py` (this version) · `guru_fast.grc/.py` (10 ms) · `guru.grc/.py` (original) · `oot/` blocks +
`oot/engine/` C++ engine · `make_guru_fast.py` · `run_hop.sh` · `install_blocks.sh` · `hackrf_tone_source.py` ·
RX tools (`tone_freq_check.py`, `tone_level_check.py`, `fast_chain_check.py`, …) · `results/` · `docs/` (WORK_LOG,
DEVELOPMENT_LOG, lab notes, git history) · `installed_snapshot/` · `environment/` · `third_party/gr-doa/` ·
`earlier_work/` · `logs/` · `RESTORE.sh` · `SHA256SUMS`. Open in GRC: `~/gnuradio-3.8/run_grc.sh guru_burst.grc`.

---

# Guru: USRP-2945 4-Channel Coherent Receiver & Phase Alignment

A GNU Radio flowgraph for the **USRP-2945** (X310 chassis + two TwinRX daughterboards)
that hops across three RF bands, keeps all four RX channels phase-aligned to a common
reference, and displays live inter-channel phase offsets. A HackRF One (or B210)
transmits the calibration tone.

Everything in this document was verified on the actual hardware — this bench's rule is
**no fallbacks, no fabricated results**. Where a number is quoted, it was measured; where
a fix is described, it was reproduced and confirmed on the real radio, not inferred.

---

## Hardware and software stack

| | |
|---|---|
| Receiver | USRP-2945 (X310, serial `31082D8`) + 2× TwinRX |
| Transmitter | HackRF One (primary) or USRP B210 (fallback) |
| GNU Radio | **3.8.5.0**, isolated at `~/gnuradio-3.8` |
| UHD | **3.15.0.0** (`aea0e2de3`) |
| FPGA image | `usrp_x310_fpga_HG.bit`, 1 GigE, built 2021-12-02 |

This project's toolchain is deliberately **isolated from the system GNU Radio (3.10) /
UHD (4.x)** — `source ~/gnuradio-3.8/setup_env.sh` before running anything here. The
transmitter runs under the *system* GNU Radio instead (HackRF/B210 support lives there),
which is why it's driven over a UDP control channel rather than sharing a process with
the receiver.

## Running it

```bash
git clone https://github.com/shankarjatti/guru
cd guru
source ~/gnuradio-3.8/setup_env.sh   # your local GR 3.8 / UHD 3.15 install
./run_hop.sh                          # starts the transmitter, then the receiver
```

```bash
./run_hop.sh --restart   # stop whatever's running (transmitter + receiver), then start clean
./run_hop.sh --vga 60    # louder transmitter
```

`run_hop.sh` starts the transmitter first (the receiver commands it on every hop and
refuses to start without it), waits for it to answer, then starts `guru.py`. It writes
`/tmp/guru_rx.log` (receiver console) and `/tmp/guru_uhd.log` (UHD-level detail) on every
run — check these first when something looks wrong.

`--restart` sends a plain `TERM`, never `KILL`: the receiver must run its own shutdown
(the hop thread has to stop *before* the flowgraph tears down) or the X310's RFNoC
control plane gets wedged and needs a power cycle. If something won't stop within 10s,
it says so and exits rather than forcing it.

### Installing the custom blocks

The blocks in `oot/` are not stock GNU Radio — they must be installed into your
GR 3.8 tree before `guru.grc` / `guru_fast.grc` will build. One command builds the
C++ engine and installs everything (close guru first):

```bash
./install_blocks.sh
```

They're subclasses/companions of blocks from
[EttusResearch/gr-doa](https://github.com/EttusResearch/gr-doa) — `twinrx_usrp_source`
and `phase_correct_hier` are the upstream originals; `twinrx_hopping_source` and
`phase_correct_hopping` are new blocks built for this project (upstream is never
modified — everything here is additive).

---

## Architecture

```
                        (over UDP, tone freq per hop)
  hackrf_tone_source.py ────────────────────────────► HackRF One (RF out)
                                                              │
  twinrx_hopping_source ◄── hops 2.4 / 5.2 / 5.8 GHz ────────┘
   (4 channels, shared LO)
        │
        ▼
  dc_blocker → band_pass (tone filter)
        │
        ▼
  phase_correct_hopping  ◄── per-band table, switched by set_band_freq() on every hop
        │
        ├──► disp_gate → time_resamp → time-domain plot
        └──► twinrx_phase_offset_est → degrees → moving_average → phase readouts
```

`phase_correct_hopping` sits **after** the band-pass and **before** both the plot and
the phase readouts, so a single correction fixes both what you see on the scope and what
the numeric offsets report.

## guru_fast: 10 ms radio-clock hopping (added 2026-09-28)

`guru_fast.grc` hops 2.4 → 5.2 → 5.8 GHz with **10 ms switching + 10 ms dwell per
band** (50 % duty, 60 ms per cycle) and keeps all four channels phase-aligned. It is
generated from `guru.grc` by `make_guru_fast.py`; `guru.grc` (10 s dwell) is unchanged.

```bash
./run_hop.sh --fast            # HackRF tone first, then guru_fast.py
```

### How the switching works

```
radio time →  S-0.25ms  S        S+0.4 S+0.8 S+1.2  S+3      ~S+5.5   S+7       S+9.75            S+19.75
                 |      |          |     |     |     |          |        |           |                  |
           guard |  gains + ch0   ch1   ch2   ch3  2nd pass   LO      PC reads    DWELL (10 ms,     guard for
           starts|  RF tune       tune  tune  tune (all 4 ch) locked  lo_locked,  10 000 samples)   next switch
                                                                      sends next
```

* **The X310 switches by itself, on its own clock.** Each band change is one timed
  command batch: gains at S, channel c's RF tune at S + c·0.4 ms, the same RF tunes
  again at S + 3 ms. A single timed pass tunes the right frequency but leaves the
  shared LO in a *different, repeatable* phase state (errors 11–180°, depending on the
  previous band); the staggered pass plus the second pass matches guru's proven host
  tune within 0.1° (30/30 trials, `tune_method_phase_test.py`).
* **The PC never times a switch.** The batch for the next slot is sent ~13 ms early;
  the radio holds it until S. The lock is read at S + 7 ms and only *then* is the next
  batch sent — any radio read issued while a timed command waits is queued behind it.
* **Slots are counted in whole samples** from the stream start, so every dwell is
  exactly 10 000 samples and every slot exactly 20 000 (`dwell_exact_check.py`).
* **Guards on both sides of every switch** are discarded: 0.25 ms before (the old band
  is clean right up to S), 9.75 ms after (phase steady ≤ 6.25 ms after S).
* The source marks the exact samples in the stream: `hop_off` (switching) and
  `hop_on` (dwell of band X). The phase correction, the displayed band and the phase
  meter all switch on those marks.

### Safety rules

* A slot that could not be sent with 8 ms to spare (**skipped**), whose batch finished
  after S (**late**), or whose LO lock was not confirmed (**unlocked**) gets no
  `hop_on`: its samples are never used. The SCHEDULE line shows the counts.
* A stream error, a gap in the packet timestamps or a full ring buffer stops all
  marking for the rest of the run and shows **TIMING LOST** — never a guessed mapping.
* The phase meter reports only on windows where a tone stands ≥ 20 dB above the
  in-band noise on every channel; otherwise it shows **nan**, never a stale number.

### Why a C++ engine, and why not gr-uhd

* Through gr-uhd (GNU Radio's standard USRP block) the same schedule left **ch0
  exactly 180° off on 6–12 % of 5.8 GHz dwells** (`gr_flip_test.py`); through UHD's
  own API it never did (thousands of dwells). So `twinrx_radio_source` talks to UHD
  directly.
* With the scheduler in Python, the GUI's load delayed it now and then (99.5 % of
  slots used; 16–34 ms stalls). The receive loop and the scheduler now run in
  `oot/engine/libtwinrx_engine.so` (C++), which never waits for Python:
  **4 720 / 4 720 slots, 0 skipped, 0 late** in the verification run.
* The engine can run at real-time priority (`rt_priority` in the block) once the user
  is allowed to: `echo "$USER - rtprio 95" | sudo tee /etc/security/limits.d/99-sdr-rt.conf`,
  log out and in. This is also the part that moves to an RTOS later.

### Calibration and drift

* The table must be measured **through this chain**: `python3 fast_chain_check.py
  --calibrate --secs 20 --out phase_table_deg.txt`, then `--table phase_table_deg.txt`
  to verify (must print ALL BANDS WITHIN 1 DEG).
* The offsets **drift**: measured here up to ~3° in 1.5 h at 5.8 GHz on ch2/ch3 (the
  pairs that cross the board A ↔ board B LO cable; ch1 stays within 0.15°). The
  **CALIBRATE** button in guru_fast re-measures all bands on the live chain (lab tone
  parked on each band, ~15 s) and applies the new table only if every band passes
  (≥ 50 windows, a tone in every window, spread < 0.3°, no window > 1° off). The
  result is saved to `phase_table_live_deg.txt`; the startup table stays the one in
  the flowgraph, because a table from an earlier power session is never valid.

### Verified on hardware (2026-09-28)

| Test | Result |
|---|---|
| Radio-clock hopping, 10 min soak (pyuhd) | 29 992 / 29 997 slots, all failures = host-late slots |
| Phase of the timed tune vs guru's host tune | ≤ 0.13° (1 800 slots), 30/30 trials ≤ 0.1° |
| gr-uhd vs direct UHD, 5.8 GHz | 6–12 % of dwells ch0 180° off vs 0 % |
| C++ engine, 3 bands | 4 720 / 4 720 slots, 0 skipped / late / unlocked |
| Verify after calibration | residual ≤ 0.15°, worst single window ≤ 0.34°, all bands |
| guru_fast GUI band tour | all bands ≤ 0.5°, plot aligned, no join artefacts |

---

## Bugs found and fixed this session

Every one of these was reproduced on hardware before being called "fixed", and most were
confirmed with a dedicated test script (still in this repo) that isolates the failure
without needing a live transmitter or a full dwelling flowgraph.

### 1. Stream dies after ~70-72 hops, X310 needs a power cycle — **root cause: DDC given a command time**

A `DDC` block subscribes to `time/cmd` exactly like a radio does, so a timed tune command
also stamps the DDC. A radio has a timekeeper and its timed commands execute and retire;
**a DDC's time never advances**, so every timed write to it queues in the FPGA's command
FIFO and never retires. That FIFO holds `CMD_FIFO_SIZE / MAX_CMD_PKT_SIZE = 256/3 = 85`
commands; ~13 are used at startup, one is stranded per hop, and at 85 the block stops
answering:

```
[0/DDC_0] sr_write() failed: Block ctrl (CE_03_Port_60) no response packet
```

After that, every tune fails for the rest of the run, and — because the full FIFO lives
in the FPGA, not the driver — **a freshly started process inherits the fault**. Only a
power cycle clears it.

**Fix**: stamp only the RF frontend in the timed pass (`dsp_freq_policy=POLICY_NONE`).
The DSP frequency is still set, identically on all four channels, by the untimed pass
immediately before. Verified: 400 rapid tunes clean (4.7× the old 85-command budget) in
`ddc_fifo_test.py`, then an 866-hop live run with zero failures and the device still
healthy afterward.

### 2. GUI freezes ("not responding") — Qt object touched from the wrong thread

The band-follow loop ran on a Python thread and called `set_frequency_range()` on the
plot widget — a Qt call from a thread that doesn't own it. Measured: 47-90
`QCoreApplication::sendPostedEvents: Cannot send posted events for objects in another
thread` warnings per run, one per hop. Qt's documented failure modes for this include a
frozen event loop.

**Fix**: the poll is a `QTimer` owned by the GUI thread. Same 50ms period, same logic,
zero cross-thread calls.

### 3. Display was burning 5 of 12 CPU cores

The four display interpolators ran an anti-imaging filter with a needlessly tight 50kHz
transition band at 20 Msps — 963 taps, 3.85 GMAC/s across 4 channels. The signal only
needs to reach `disp_bw` (300kHz) before its first image at `samp_rate - disp_bw`
(700kHz); everything between is transition band, and narrowing it bought nothing.
Widened to match what the signal actually needs: 121 taps, 0.48 GMAC/s — an 8× cut, same
picture.

### 4. Phase correction applied to the wrong channel

`bp_1`/`bp_2`/`bp_3` don't carry channels 1/2/3 — the receiver source's own port order
permutes them (`bp_1` carries ch3, `bp_2` carries ch1, `bp_3` carries ch2). The
correction block, the readout labels, and the sign of the phase estimator all have to
agree with that permutation or a channel's correction gets applied to a *different*
channel's signal — which doesn't look broken, it looks like a bad calibration.

**Fix**: each `bp_N` now feeds the correction port for the channel it actually carries,
and the corrected output is routed back to the display path that expects it, so port N
really is channel N everywhere downstream. Also fixed: `twinrx_phase_offset_est`
computes `ch0 - chN`; every measurement and the table itself use `chN - ch0`, so the
degree conversion is negated to match.

Verified on hardware, all four channels in phase: `ch1 0.02°, ch2 0.10°, ch3 0.17°`
(measured against a table that had produced 84°-174° raw offsets before correction).

### 5. Silent fallbacks that could report success without checking

An audit pass removed every `except: pass` (or similar) that let a failed check report
as "fine" — the worst was the STREAM status label defaulting to `receiving` when it
couldn't actually read the block's state, which is exactly the failure mode this bench
exists to prevent (a frozen reading that looks like a stable measurement). Also fixed: a
transmitter watchdog that silently stopped watching on a failed rate read, teardown paths
that swallowed a failed `stop_hopping()` (which is what wedges the X310), and a `set_gain`
fallback that set the gain unclamped without saying so — gain shifts phase on this
hardware, so a silent gain mismatch would silently invalidate the calibration.

---

## Phase correction

`phase_correct_hopping` (in `oot/`) holds one row per band — offsets in **degrees**,
converted to radians internally — and switches rows via `set_band_freq()`, called by the
flowgraph on every hop. It does **not** keep its own clock: a correction block that timed
itself independently of the radio would eventually drift out of sync and apply one
band's correction while the radio sat on another — which reads as a clean, stable,
*wrong* number, the hardest kind of failure to catch on this bench. An unmatched band
gets **zero** correction and a printed warning, never the nearest row's numbers.

### The current table is session-specific — re-measure after every power cycle

**The LO dividers relock to a new phase every time the X310 is power-cycled.** A table
measured in one session is meaningless in the next. This was measured directly: after an
overnight restart, offsets that were `0.02° / 0.10° / 0.17°` the day before had drifted
to `0.20° / 1.30° / 1.54°` — small, but real, and enough to exceed a 1° tolerance on two
channels. `phase_table_deg.txt` / `phase_table_rad.cfg` in this repo are a snapshot, not
a fixture.

**The table is also tied to specific gains** (`46/60/69 dB`, `gain_trim = (0.0, -13.3,
1.5, -1.7)`). RX gain shifts phase on this hardware — change a gain, re-measure.

To re-measure (through the exact radio configuration `guru.py` runs, including the gain
trim):

```bash
source ~/gnuradio-3.8/setup_env.sh
cd guru   # wherever this repo is checked out
python3 phase_table_measure.py --cycles 10 --dwell 4 --settle 1 --depth 262144 --search 60e3
```

This is SNR-gated — a reading is discarded unless every channel sees the tone above the
threshold, so a weak or dead channel can't silently pollute the average. Paste the three
printed rows into `phase_correct_hopping`'s per-band `deg_N` fields in `guru.grc`, then
regenerate: `grcc guru.grc -o .`

`phase_table_measure.py --apply <file>` re-runs the measurement **through the live
correction block** and reports residuals instead of raw offsets — use it to verify a new
table actually zeroes out before trusting it.

---

## Known limits / open items

- **(guru.grc only)** **Retune floor is ~81ms, not the few hundred microseconds the synthesizers alone would
  need.** guru_fast does not have this limit (see above). Traced to a hardcoded `time.sleep(0.08)` at the top of `_relock_lo()` in
  `twinrx_usrp_source.py`, which runs unconditionally on every tune (not just when the
  LO-lock fallback path is actually needed). The synthesizer itself locks in under
  0.3ms once its timed command executes — confirmed by timing every sub-step of
  `set_center_freq()` individually. Not yet fixed in this repo; the fix under
  consideration is tying that sleep to `cmd_time_margin` instead of a fixed 80ms.
- **`cmd_time_margin`** (the deadline the RF frontend's timed tune is stamped with) was
  raised from 10ms to 100ms partway through the DDC investigation, then left there once
  the real fix (excluding the DDC from timed commands) was found — 100ms "cost nothing"
  against a 1s settle. Swept down to 1ms and soaked for 200 tunes with zero failures and
  zero UHD warnings, so there's real room to shrink it now that dwell times are being
  reconsidered; not yet applied to the checked-in `guru.grc`.
- **`twinrx_hop_test.py`** (referenced in some of the diagnostic scripts' docstrings)
  uses the plain `twinrx_usrp_source`, not `twinrx_hopping_source`, and does **not**
  apply `gain_trim` — a table measured with it will not match what `guru.py` actually
  runs. Use `phase_table_measure.py` for anything that has to match the live flowgraph.
- Dwell is currently 10s per band (33s per full 3-band cycle) — deliberately
  conservative while the retune-floor investigation above is still open.

---

## File manifest

| File | What it is |
|---|---|
| `guru.grc` / `guru.py` | the flowgraph; `guru.py` is generated — don't hand-edit it, edit `guru.grc` and run `grcc guru.grc -o .` |
| `run_hop.sh` | starts transmitter + receiver together, in the right order |
| `hackrf_tone_source.py` | the calibration tone transmitter (runs under system GNU Radio) |
| `oot/twinrx_hopping_source.py` | the hopping receiver source — owns LO routing, timed tuning, the stream watchdog |
| `oot/twinrx_usrp_source.py` | the underlying single-frequency 4-channel TwinRX source `twinrx_hopping_source` subclasses |
| `oot/phase_correct_hopping.py` | per-band phase correction, switched live by the radio's current band |
| `ddc_fifo_test.py` | reproduces the DDC command-FIFO stall in ~40s instead of waiting ~13 minutes for it to occur naturally |
| `chain_check.py` | runs the real signal chain (dc block → band-pass → correction → phase estimator) headless, for verifying a fix without the GUI |
| `phase_table_measure.py` | measures (or re-measures, or verifies) the phase correction table through the real flowgraph configuration |
| `phase_restart_test.py` | measures whether phase offsets survive a software restart (they do, to ~0.3°, once the DDC fix is in) |
| `stall_watch.py` | external, independent stream-stall watchdog (samples the NIC counter directly, doesn't share assumptions with the in-flowgraph one) |
| `phase_table_deg.txt` / `phase_table_rad.cfg` | the current calibration table — **session-specific, see above** |
| `twinrx_lo_cal.json` | LO routing calibration |
| `guru_fast.grc` / `guru_fast.py` | 10 ms radio-clock hopping flowgraph, generated by `make_guru_fast.py` |
| `oot/twinrx_radio_source.py` + `oot/engine/` | radio-clock source; C++ engine (receive + scheduler) |
| `oot/hop_blocks.py` | hop-mark blocks: band select, phase meter, sample-exact correction |
| `oot/hop_calibrator.py` | live re-calibration behind guru_fast's CALIBRATE button |
| `install_blocks.sh` | builds the engine and installs every block |
| `fast_chain_check.py` | calibrate / verify the table through guru_fast's own chain, no GUI |
| `dwell_exact_check.py` | proves every dwell / switch / slot is an exact sample count |
| `hop_blocks_selftest.py` | offline self-test of the hop-mark blocks (no radio) |
| `gui_band_tour.py` | runs the guru_fast GUI through each band and saves pictures |
| `sched_hop_test.py`, `tune_method_phase_test.py`, `timed_tune_test.py`, `tune_speed_test.py`, `dwell_test.py`, `grc_timing_test.py`, `gr_flip_test.py` | the measurements behind the design (results in `results/`) |
