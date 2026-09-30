# guru10ms — development log (2026-09-28)

How the 10 ms hopping receiver was built, what was measured, every mistake and
its fix, and what is still open. Hardware facts learned over the whole project
are in [lab_notes/](lab_notes/README.md); the full commit history of `~/radar2`
is in [radar2_git_history.txt](radar2_git_history.txt).

## 1. Hardware and software

| Item | Value |
|---|---|
| Receiver | NI USRP-2945 = Ettus X310 (serial `31082D8`) + 2× TwinRX Rev B (`3104B3C` = Rx A, `31050CD` = Rx B), 4 coherent channels |
| Link | 1 GigE, host `enp3s0` 192.168.10.1 ↔ X310 192.168.10.2 |
| LO sharing | board B exports the LO: ch0 `external`, ch1 `external`, ch2 `internal` + export, ch3 `companion` (see lab note `usrp-2945-twinrx-lo-sharing`) |
| Lab source | HackRF One on USB → splitter → all 4 RX ports (bench only; the final system uses antennas) |
| Receiver software | GNU Radio 3.8.5.0 + UHD 3.15.0 at `~/gnuradio-3.8`, `~/uhd-3.15` ([environment/](../environment/)) |
| Transmitter software | system GNU Radio 3.10 + gr-soapy, separate process, UDP control 127.0.0.1:5123 (`freq <hz>`, `vga`, `ping`, `quit`) |
| Sample rate | 1 MS/s per channel |

## 2. The requirement (as stated by the user)

* Hop **2.4 → 5.2 → 5.8 GHz**; each band **10 ms OFF** (switching: LO relock, samples thrown away) then
  **10 ms ON** (dwell, samples used). One cycle = **60 ms**. "10 ms strictly, it should not vary."
* All 4 channels phase aligned on every band.
* Samples around each switch may be rejected on both sides.
* HackRF transmits **2.4 GHz only**; the receiver must show the tone in the 2.4 GHz dwell and
  **flat** in the 5.2 and 5.8 GHz dwells. The HackRF moves only when the LAB TONE selector is
  changed, or during CALIBRATE (all 3 bands, then back).
* Main screen like the original guru: sine plot + "chN − ch0 phase offset (deg)" numbers, with the
  lock status (which band) above. **Not three plots.**
* Defence work: nothing fake, every result measured on the hardware, permanent solutions.
* Later: the user plans an RTOS; for now Linux.

## 3. Path taken (stages)

1. **Recovery.** Earlier edits had broken the working 10 s guru. It was restored from
   `~/REPO/gr-doa/python` and commit `b3d8cce`. The installed hopping source had lost `set_samp_rate()`
   (0.82 MB/s instead of 16 MB/s). Backup `BACKUP_WORKING_2026-09-28`, tag `working-2026-09-28`.
2. **How fast can the TwinRX retune?** Measured (`tune_speed_test.py`, `timed_tune_test.py`):
   with a timed tune at T, `lo_locked` reads True **5.40–5.84 ms after T** (300 hops, none failed to
   lock; `timed_tune_20260928_122715.json`), so a 10 ms switching slot leaves > 4 ms margin.
   Stepped dwell tests 50 → 20 → 10 ms
   (`dwell_test.py`, results `dwell_50ms_*`, `dwell_10ms_*`).
3. **Host timing is not enough.** Host `sleep()` based hopping jitters by milliseconds. Decision:
   schedule every hop on the **X310's clock** with timed commands (permanent solution; also what an
   RTOS port would keep).
4. **Phase-correct timed tune.** A single timed tune gives the right frequency but a wrong, repeatable
   phase state (11–180° off). Found (`tune_method_phase_test.py`, 30/30 trials within 0.1° of guru's
   host double tune): gains at S, channel c's RF tune at S + c·0.4 ms, the same four RF tunes again at
   S + 3 ms. DDC is 0 Hz on all bands: pinned once, never commanded while hopping (lab note
   `twinrx-ddc-timed-command-fifo`).
5. **gr-uhd flips ch0 by 180°** on 6–12 % of 5.8 GHz dwells with this schedule (`gr_flip_test.py`);
   UHD used directly never does. → new source block `twinrx_radio_source` that does not use gr-uhd.
6. **Python scheduler stalls** (GIL/OS, 16–34 ms) with the GUI → ~0.5 % skipped/late slots.
   `sys.setswitchinterval` and gc tuning were measured to make it worse. → **C++ engine**
   (`oot/engine/twinrx_engine.cpp`): receive thread → lock-free ring (4 × 2²² samples) + scheduler
   thread; never waits for Python.
7. **Radio reads queue behind timed commands.** A `get_time_now`/`get_sensor` issued while a timed
   command is pending waits for it → false "late" readings and wrong clock offsets. Rule: per slot, read
   `lo_locked` at S + 7 ms, then send the next batch (~13 ms budget); never read at any other time.
8. **Exact sample counts.** RX packet time_spec steps at 2× on this X310, so it is only a gap detector;
   sample n is at start + n/fs. Slots are counted in whole samples (S = start + n_S/fs) or float rounding
   jitters the boundaries by one sample. Result: dwell = switch = 10,000 samples, period 20,000, exact.
9. **Hop tags** on stream 0 at exact samples: `rx_time`, `hop_off` (S − 0.25 ms, value = next band),
   `hop_cycle` (switch into band 0), `hop_on` (S + 9.75 ms). A slot that was skipped (< 8 ms slack),
   late, unlocked or without a lock verdict within 20 ms gets **no `hop_on`** and is never used.
10. **Flowgraph** `guru_fast.grc`, generated from `guru.grc` by `make_guru_fast.py`: per-band select
    (`hop_band_select`), sample-exact per-band phase correction (`hop_tag_rotator` in
    `phase_correct_hopping`, `follow_tags=True`), per-band tone-gated phase meters (`hop_phase_meter`,
    FFT peak ≥ 20 dB over median, else NaN), CALIBRATE (`hop_calibrator`), Switching tab with the whole
    60 ms cycle.
11. **Display rework to the user's spec** (tone on 2.4 GHz only, flat elsewhere, one sine plot, guru-style
    numbers, lock status line). The 3-plot design was dropped at the user's request.
12. **"Flat line for a few seconds"** in the GUI: the HackRF's own TX stream stalled after many retunes.
    Fixed in `hackrf_tone_source.py`: no retune onto the frequency it is already on, stall detected in
    ~2 s (watchdog `bad >= 2`), line-buffered log; the GUI shows red **NO TONE** with "Receiver OK".
13. **Fake 0.000** — the GR 3.8 number sink prints NaN as 0.000000. Replaced by Qt labels that say
    "NO TONE – nothing measured".
14. Commit `f6ff6ce`, tag `working-fast-2026-09-28`, backup `BACKUP_FAST_2026-09-28`, then this copy
    (`guru10ms`, tag `guru10ms` / `d135177`).

## 4. Measured results

| Test | Result |
|---|---|
| Slot timing (`dwell_exact_check.py`) | 2,968 / 2,968 slots exact: dwell 10,000, switch 10,000, period 20,000 samples |
| C++ engine, no GUI | 4,720/4,720 and 3,219/3,219 slots, 0 skipped / late |
| 30 min GUI soak | 90,005 / 90,008 slots used |
| LO lock | 0 unlocked in over 100,000 slots |
| Phase after CALIBRATE (`fast_chain_check.py`) | all bands, all pairs within 1° |
| Program restart | two starts 40 s apart, both ≤ 0.55° with one table |
| Thermal drift | afternoon: 4.5° then 7.8° CALIBRATE corrections within 16–18 min (board A↔B pairs) |
| Tone moved off every band | readouts show NO TONE, receiver stays OK (`gui_band_tour.py --tone-away`) |

Raw data: [results/](../results/) (JSON, pictures, `.npz` captures).

## 5. Mistakes and their fixes

| Problem | Cause | Fix |
|---|---|---|
| Edits had no effect | edited `guru/oot/`, GNU Radio runs `~/gnuradio-3.8/.../doa/` | `install_blocks.sh` copies oot → installed |
| Untracked files lost | deleted as "clutter" in an earlier session | restored from `gururaj/` where possible; rule: never delete the user's files |
| dwell_test half rate / wrong times | trusted packet time_spec (2×) | time = commanded start + n/fs |
| Wrong phases with timed tune | single timed pass | staggered tune + second pass at S + 3 ms |
| False "late", wrong clock offset | reads queued behind timed commands | read only at S + 7 ms, never while a command is pending |
| 180° flips at 5.8 GHz | gr-uhd | `twinrx_radio_source` (UHD directly) |
| 0.5 % skipped slots | Python GIL stalls | C++ engine |
| JSON dump failed | numpy bool | default serialiser |
| GR 3.8 `work()` argument error | 3.8 passes `input_items`/`output_items` by name | used those names |
| Test script killed its own shell | `pgrep -f` matched the shell | exact PIDs / `^python3` patterns |
| Switching plot empty | display gain missing; picture taken before draw | added gain; wait for trigger |
| Flat line for seconds | HackRF TX stall after retunes | no needless retunes, 2 s watchdog, NO TONE on screen |
| 0.000 shown with no signal | number sink prints NaN as 0 | Qt labels |

## 6. Open items

* **Thermal phase drift** (up to ~8° in 16 min) — cause not established; CALIBRATE every 5–10 min.
  Better (shorter, phase-stable) LO cables are the highest-value fix.
* **Real-time priority** not yet enabled (limit is 0): a few late slots are possible. Enable with
  `echo "shankar - rtprio 95" | sudo tee /etc/security/limits.d/99-sdr-rt.conf`, then Real-time
  priority = 90 in the source block.
* **Field calibration without the HackRF** (antennas, cables): not designed yet; suggested a startup
  reference tone through an RF switch/coupler.
* **Overflow recovery** untested (on overflow the stream is marked TIMING LOST; restart).
* **RTOS**: UHD needs Linux; recommended Linux PREEMPT_RT. The engine's timing logic is small C++ and portable.
* **5.00–5.14 GHz** cannot be hopped into (LO1 high-side never locks) — `make_guru_fast.py` refuses it.
