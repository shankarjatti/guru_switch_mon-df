# WORK LOG — live

Updated at **every stage** of the work, so nothing is lost when a session is compacted
or restarted. Newest entry first. The finished story is in [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md);
hardware facts are in [lab_notes/](lab_notes/README.md).

**Rule for each entry:** date + time, what was asked (user's words where it matters),
what was done, what was measured (numbers, file in `results/`), what failed and why,
decisions taken, and what comes next. Only measured facts; anything not verified is marked so.

---

## CURRENT STATE (keep this block up to date)

| | |
|---|---|
| Working system | guru_burst (lab `~/radar2/guru`): 2.4 → 5.2 → 5.8 GHz, 7 ms switch + 5 ms dwell, 36 ms cycle, burst mode, 2 MS/s, 200 kHz HackRF tone (pure source). guru_fast 10/10 ms still available |
| Code on the lab PC | `~/radar2/guru10ms/` (this repo, pushed) and `~/radar2/guru/` (same code; lab git repo `~/radar2`, tag `guru10ms` = `d135177`) |
| GitHub | https://github.com/shankarjatti/guru10ms (public, branch `main`) |
| Backups | `~/radar2/guru10ms.tar.gz`, `~/radar2/BACKUP_FAST_2026-09-28/` (+ `.tar.gz`), `~/radar2/BACKUP_WORKING_2026-09-28/` (10 s guru) |
| Run | `./run_hop.sh --fast`, then CALIBRATE; every 5–10 min for < 1° |
| Radio | X310 `31082D8` at 192.168.10.2; HackRF tone on 2.4 GHz (UDP 127.0.0.1:5123) |
| Open items | thermal drift (~8°/16 min); rtprio not enabled (limit 0); CPU governor = `powersave` (not yet tested as a cause of late slots); field calibration without HackRF; overflow recovery untested; RTOS choice |
| Saved state | DF: `~/radar2/guru_DF_v1`, MON: `~/radar2/guru_MON_v1` (both frozen 2026-09-30); earlier `~/radar2/guru0930` (frozen 2026-09-30, lab tag `guru0930`) — base for the next step |
| Setup now (2026-09-30) | back to CABLE (HackRF → splitter → 4 ch); installed blocks = guru57; over-the-air work paused in `~/radar2/guru_ota` |
| Next step | user: `cd ~/radar2/guru && ./run_hop.sh --burst` + CALIBRATE; long run (> 11 min) to prove the 2 MS/s fix; rtprio needs log out/in |

---

## 2026-09-28

### 2026-09-30 18:12–18:42 — 30-min run of guru_switch: PASSED (no failure)
* User: "keep monitoring, we'll run it for 30 min; if it fails we'll check root cause". Watched every minute.
* CALIBRATE OK 18:10:15 (worst single window 0.06°). User switched MON/DF by hand 7 times (last: MON at ~18:31).
* 30 min: guru_switch running all the time, TIMING LOST 0, tracebacks 0; HackRF: 0 new TIMEOUTs, 0 watchdog
  restarts (after the fresh-process fix + fresh start).
* DF 2.4 GHz (18:13–18:32, in DF): tone +192.6..193.1 kHz, 10,000 samples per dwell every time, phases after CAL
  ch1 +0.05..+0.13°, ch2 +0.28..+0.52°, ch3 +0.26..+0.52° (slow drift ~0.2° over 20 min, max dev ≤ 0.08°).
  From 18:32 the program is in MON, so the DF meter holds its last value (expected).
* First run of the 2 MS/s DF chain past 11 min without TIMING LOST since the 09-29/09-30 failures (6 and 11 min);
  that earlier one coincided with me building a tarball — load matters, not proven fixed.

### 2026-09-30 18:08 — "not getting correct signal": HackRF stalled again (not the receiver)
* guru_switch log: every meter "no tone"; receiver healthy (locked, 0 missing, no TIMING LOST). HackRF log: 7046
  TIMEOUTs, watchdog restarting every ~1 s, each restart stalling again. HackRF USB device number 006 → 009 → 013
  over the day = it dropped off USB and came back at least 3 times (cable / port / power).
* Fix: 3 stalls within 60 s → the transmitter re-execs itself as a fresh process on the band last asked for
  (lab commit; copied to guru_switch, guru_mon, guru10ms). Fresh transmitter: 0 TIMEOUTs; guru_switch 2.4 GHz
  tone back (+192.8 kHz, 10,000 samples, phases +0.05/+0.14/+0.13°). 5.2/5.8 need CALIBRATE.
* Recommended to the user: HackRF on another USB port / shorter cable / powered hub.

### 2026-09-30 18:20 — user ran guru_switch: "ITS WORKING SUPER"
* User started `cd ~/radar2/guru_switch && ./run_hop.sh --switch` with the run instructions (CALIBRATE in DF,
  MODE selector manual only, MON tab, LAB TONE selector) and confirmed it works.
* Not yet frozen as a safe copy (guru_switch is the work copy, last commit a2a0140 + message fix).

### 2026-09-30 17:00–18:10 — switching steps 3–5: GUI, API, validation; user: MON continuous, manual mode only
* `guru_switch.grc/.py` (`make_guru_switch.py`): guru_burst's DF flowgraph unchanged on outputs 0-3 + MON tab
  (per LO spectrum / time / status) on 4-7 + MODE selector above the tabs. `./run_hop.sh --switch`.
* First GUI start: TIMING LOST at once — the Python MON meter (all 4 MON streams through Python) + 8 displays
  on top of the DF chain. Fix: MON path C++ only (probe snapshots of 8192 samples, displays thinned to whole
  4096-sample blocks, MON count from the engine). Then no TIMING LOST.
* Bugs found and fixed: MON band-stats key "MON" (string) broke the DF lock line; a repeated request (GUI
  selector following an API request) moved the request time.
* Validation (`switch_validate.py`, GUI + API, 151 switches over 566 s, then burst-mode MON):
  150/151 switches locked + used (1 not used, marked), bursts 50,720 ok / 0 missing, no TIMING LOST; DF 2.4 GHz
  phase over the whole run (guru's own meter): worst change 0.09 / 0.28 / 0.15°; request → first dwell:
  to DF mean 46.6 ms (worst 56.3), to MON 27.8 ms (worst 33.5); routing 1.0 ms mean (worst 4.0);
  555 / 50,722 slots late (1.1 %, marked, never used) = the PC's latency (see 16:20 entry).
* User: "MON work should be in continuous mode now ... don't follow burst mode there" → MON = ONE continuous
  stream (timed START_CONTINUOUS at the first MON sample; STOP at the switch back, the stream ends where it
  ends, end-of-burst gives the exact last sample); engine keeps 20 ms MON records with a lock read. DF stays burst.
* User: "don't set auto changing mode between MON and DF, that should be manually controlled" → the program never
  switched by itself (the automatic switching seen was my validation script through the API); API now OFF by
  default, mode only via the MODE selector.
* Continuous MON headless (`switch_engine_check.py`, a TEST that switches): 10 cycles: 0 missing bursts, DF phase
  after each return ≤ 0.27°, DF dwells 10,000; 1000 MON records locked; MON→DF now 20–29 ms, DF→MON 23–33 ms.
  First continuous run had bursts missing 10 (= number of switches), NOT reproduced in 3 runs since — open.
* GUI started for the user in DF (CALIBRATE first: the X310 was power-cycled).

### 2026-09-30 16:20–16:45 — switching steps 2 (engine) done, headless-verified on the radio
* `guru_switch/oot/engine/twinrx_engine.cpp` → `libtwinrx_switch.so` (separate lib; installed engine untouched):
  MON = one more band, own freq per channel, own internal LOs; mode request taken at the next planned slot;
  consecutive MON slots not retuned → MON bursts join with no gap. `switch_source.py` (local block, 8 outputs:
  0-3 DF with the old tags, 4-7 MON with mon_on / mon_bad / mon_off).
* Measured facts found on the way (route_burst_test.py):
  - timed LO routing takes effect at T (ch0 tone gone +0.12 ms after T, never before), phase back ≤ 0.16°;
  - BUT in the running engine a TIMED routing call blocks the host until T (each call reads the TwinRX back and
    the read waits behind the timed write) → tune after it went out late (all 10 switch slots late, send 30–45 ms).
    Fix: after the old mode's last dwell has ENDED, route UNTIMED (0.6–2.9 ms), then the timed tune at
    end + switch_gap (10 ms);
  - 200 burst commands at once overflow the radio's command queue (only 32 ran); the engine queues one ahead.
* Headless check (`switch_engine_check.py`, 5 cycles DF 2 s / MON 2 s, tone on 2.4 GHz):
  1558/1558 slots used, 0 late/unlocked/skipped, bursts 1557 ok / 0 missing, 10/10 switches locked;
  DF phase after each return from MON ≤ 0.26° (single-dwell std 0.06/0.11/0.09°); every DF dwell 10,000 samples,
  every MON dwell 40,000 (20 ms); MON: only ch1 (2.4 GHz) sees the tone (84.8 dB), ch0 34 dB board-mate leak,
  ch2/ch3 noise; request → first dwell of the new mode: DF→MON 24–33 ms, MON→DF 39–48 ms.
* One earlier run had 165 late DF slots with the same code (band change 4 ms instead of 1.1): a kernel worker at
  62–67 % CPU (D state), rustdesk, CPU governor `powersave`. DF-only and the next run: 0 late. PC latency, not the
  design — the performance governor needs the user (system setting).
* Next: control API + GUI (steps 3–4), then validation (step 5).

### 2026-09-30 16:05–16:17 — switching step 1 (`guru_switch/switch_check.py`): DF phase SURVIVES a trip through MON
* `~/radar2/guru_switch` = working copy of guru_DF_v1 + guru_MON_v1 (`59d2ed4`); frozen copies untouched.
* First trial tuned UNTIMED → phases after any retune jumped by exact multiples of 90° (also in the DF-only
  baseline) = the TwinRX LO divider state. Test-script error; fixed by using the engine's tune exactly
  (gains at T, ch c at T + c·0.4 ms, second pass at T + 3 ms, DDC policy NONE; lock read after the second pass).
* Full run (`results/switch_check_20260930_161434.json`): per DF band 50 MON trips (DF → MON with ch0..3 on
  0.9/2.4/5.2/5.8 GHz, each own LO, 0.2 s → DF) interleaved with 50 DF-only retune baselines:
  - phase change after a MON trip, worst of ch1/ch2/ch3: 2.4 GHz 0.33°, 5.2 GHz 0.20°, 5.8 GHz 0.22°
    (baseline retune: 0.26°, 0.14°, 0.12°); extra caused by the switch ≈ 0.03–0.11° (mean), std ≤ 0.07°.
  - MON set up correctly (all internal, all locked) 150/150; lock timeouts 0.
  - LO routing change ~2 ms (host, worst 4.7 ms); lock confirmed 4–8 ms after the timed tune (radio clock;
    includes the 3 ms second pass and sensor reads). Tune lead 30 ms was a choice, not a limit.
* Caveats: `lo_locked` on external channels (ch0/ch1 in DF) reports their own synth, so it proves nothing
  there — the phase + SNR are the proof. Between program starts the reference phase of ch2 came up 180° apart
  (+27.7° vs −152.8° at 2.4 GHz) → the start state is ambiguous: calibrate at every start (already the rule);
  within one run it is stable. MON-mode reception during the trips was not checked (only routing + locks).
* Conclusion: switching needs NO recalibration on return to DF (with the engine's tune). Next: step 2 (engine).

### 2026-09-30 15:45 — both works saved separately: `guru_DF_v1` and `guru_MON_v1`
* User: "keep both work separate and safe ... with other name ... after that we'll come to combining with switching".
* `~/radar2/guru_DF_v1` (git `b579304`, 449 files, `RESTORE.sh --verify/--check` OK, lab tag `guru_DF_v1` = `d9c5f78`,
  `guru_DF_v1.tar.gz` 245 MB): guru0930 + HackRF re-exec fix + 3-packet X310 ping. Needs CALIBRATE (X310 power-cycled).
* `~/radar2/guru_MON_v1` (git `6e975ff`, 15 files, `guru_MON_v1.tar.gz` 186 kB): MON only, standalone (stock gr-uhd,
  embedded meter, no installed doa blocks); block templates in `templates/`; regenerates the same flowgraph.
* ch0 port check (MON mode, same freq/gain): ch0 A/RX1 13–16 dB low on all 4 bands, others within ~3 dB → RF path
  of ch0, not LO sharing. Open: swap ch0/ch1 cables.
* User asked about "apk" for switching — unclear (API vs Android app); answered both. Next: MON↔DF switching plan
  (step 1 = switch_check.py measurement), only after the user's go.

### 2026-09-30 15:12 — MON step 1 (guru_mon): 4 LOs, own band each — WORKS on the cable
* Built in `~/radar2/guru_mon` (clone of guru0930; `d98421c`, `ad333a8`): `make_guru_mon.py` → `guru_mon.grc/.py`,
  `mon_tools.py`, embedded MON meter; `./run_hop.sh --mon`. Per LO: spectrum, time graph (I/Q), gain, frequency,
  status line (own `lo_locked`, every sample counted, stream breaks via rx_time tags, strongest line, ADC peak).
  MON setup at start, in order: export off → all LOs internal → tune each twice (TwinRX keeps the last routing).
* Blocked first: X310 was powered off (enp3s0 NO-CARRIER); HackRF had been replugged and its watchdog retried
  1843× in-process → fix: after 3 failed restarts it re-execs itself on the last band (lab `d9c5f78`).
* Measured (HackRF stepped 900 MHz → 2.4 → 5.2 → 5.8 GHz, 2 MS/s, gains 40/46/60/69):

| HackRF on | ch0 900 MHz | ch1 2.4 GHz | ch2 5.2 GHz | ch3 5.8 GHz |
|---|---|---|---|---|
| 900 MHz | **TONE +197.0 kHz 66.6 dB** | noise 12.0 | noise 11.5 | noise 11.6 |
| 2.4 GHz | 29.5 dB at the same +191.7 kHz | **TONE 83.4 dB** | noise 12.6 | noise 11.8 |
| 5.2 GHz | noise 12.1 | noise 12.5 | **TONE 80.1 dB** | 23.0 dB at the same +182.1 kHz |
| 5.8 GHz | noise 11.4 | noise 11.6 | 25 dB at +181.6 kHz (15:12) | **TONE 77.3–80.1 dB** |

  All 4 LOCKED all the time; each ~2.00 MS/s (counted); 1 stream break (at start, not growing); ADC peak ≤ 0.21.
* Finding: the other channel on the SAME TwinRX board sees the tone ~54–57 dB below, at the identical baseband
  offset (crosstalk after down-conversion, within a board); the other board shows nothing (> ~65 dB).
* X310 was power-cycled → DF phase table is invalid; CALIBRATE on the next DF run.

### 2026-09-30 13:30 — the user's whole work plan (discussion only, no code) — step by step
* User: "we continuously monitor all frequencies ... edge computing modules [find their] band ... send request for DOA
  ... based on the requests we make a schedule and find the target ... after that again move to monitoring".
  Scope is only BEFORE the USRP (Monitor mode, priority switching, USRP); DOA itself and everything after the USRP
  are other people's work.
* User: "this is my whole work plan, don't go directly for the full plan ... we'll do step by step".
* Plan agreed as an outline only (each step starts only when the user says so):
  0. measure: independent-LO retune time; LO mode-switch time; phase before/after a mode switch; scan speed
  1. Monitor mode (engine scans a frequency list on the radio clock, real counters)
  2. doa_request interface (frequency, priority, id, time; accepted/started/done)
  3. scheduler (priority queue, max time away from monitoring, timeout)
  4. DOA slot (mode switch if needed, coherent IQ + timestamps + calibration status)
  5. back to monitoring; end-to-end test, request-to-DOA latency measured
  6. robustness (CPU headroom; TIMING LOST after 6 min on 2026-09-30)
* Open design choice: Monitor with independent LOs (≈4× scan coverage, but a mode switch → relock, maybe recalibration)
  vs shared LO always (one freq at a time, calibration always valid, DOA from the next slot). Decide from step 0.
* Open questions to the user: "all frequencies" = 10 MHz–6 GHz or a band list; request format/transport and owner;
  DOA length per request; two requests at once; max time away from monitoring.

### 2026-09-30 12:52 — work saved as `guru0930` (user: "save this work... i need to take it in to next big step")
* `~/radar2/guru0930`: guru57 + today's fixes (`hackrf_tone_source.py`, `run_hop.sh`), all results, logs of today's run,
  WORK_LOG; own git `99d7436`; 449 files in SHA256SUMS (`RESTORE.sh --verify` OK); installed blocks = this copy
  (`--check` OK); `~/radar2/guru0930.tar.gz` (245 MB) + `.sha256`; lab tag `guru0930` = `d818647`.
* guru57 left frozen: today's 4 `tone_freq_*.json` that had been written into guru57/results moved to guru/results
  (guru57 git clean, 421 files intact).

### 2026-09-30 12:30–12:50 — cables fixed; HackRF stall; launcher bug; guru_burst running — user: "now its working correct"
* After the user reseated the cables: ch2 level with ch1/ch3 on every band (2.4 GHz 94.4 / 95.1 / 94.8 dB; ch0 84.7 dB,
  4–10 dB below the others — enough, but more than on 09-29).
* First re-check showed no tone on any channel: the HackRF's transmit stream was stalling (USB TIMEOUT, 13 watchdog
  restarts, each stalled again within ~1 s). Transmitter process restarted → 0 TIMEOUTs since.
* Bug found in the log: a stall during 5.8 GHz came back "restarted on 2.4 GHz" — a 'freq' request arriving during
  the restart went to the dead flowgraph. Fix (`hackrf_tone_source.py`): the band last asked for is kept, and the
  restart and every UDP command share one lock. Lab commit `d818647`.
* Raw radio-block capture (guru_burst settings, 2 MS/s, burst, rt 0 and rt 90): tone on all 4 channels 72–87 dB —
  real-time priority 90 is now granted ('rt_priority': 'on') and does not change reception.
* Launcher bug: `run_hop.sh` has `set -u`, `setup_env.sh` appends to `$LD_LIBRARY_PATH`; when that is unset bash stops
  before the receiver starts (exit 1, no receiver log). Fix: `set +u` around the source (guru, guru10ms, guru_ota;
  guru57 left frozen — same bug there if LD_LIBRARY_PATH is unset).
* guru_burst on the cable (12:46): 2.4 GHz tone +192.3 kHz, 10,000 samples/dwell, ch1/ch2/ch3 +0.02/−0.02/−0.01°
  (max dev 0.07°) with the stored table. 5.2/5.8 GHz still show the startup values (−64/−20/−101°, −45/+140/+30°) —
  cables were reseated, so CALIBRATE is needed on those bands.
* 15-min watch of the run started (covers the 11-min TIMING LOST problem).

### 2026-09-30 12:25–12:35 — "not getting signal from ch2" → ch2 RF input nearly disconnected (cable)
* Measured with guru57's own `tone_freq_check.py` (guru57 blocks installed, no trim, 2 MS/s, 200 kHz tone):
  tone over noise ch0/ch1/ch2/ch3 = 2.4 GHz 88.8/99.2/**66.5**/99.0 dB; 5.2 GHz 91.2/97.9/**76.9**/97.0; 5.8 GHz 92.8/97.5/**77.5**/97.5.
  Yesterday (cable, same tool): ch2 equal to ch1/ch3. LO locked on every band; ch2 phase still steady (0.05–0.2°).
* Conclusion: not software — ch2 (Rx B RX1) gets only leakage; ch0 also 5–10 dB lower than yesterday.
  Asked the user to reseat/tighten ch2 and ch0 SMAs (2945 + divider), swap ch2/ch3 cables if still weak.
* Waiting for the user; then re-measure and run guru_burst.

### 2026-09-30 12:18 — back to the CABLE setup; guru57 blocks restored
* User: "that antenna test we ll come latter.... we ll come back to old setup using cable connection".
* `~/radar2/guru57/RESTORE.sh` run: installed blocks in `~/gnuradio-3.8` = guru57 exactly (`--check`),
  all 421 files of guru57 intact (`--verify`). The OTA blocks that were installed are saved in
  `~/radar2/pre_restore_20260930_121829/`.
* `~/radar2/guru` = guru57 (same blocks, `guru_burst.py`, `run_hop.sh`, byte-compared).
* User re-connects HackRF → splitter → 4 channels. Run: `cd ~/radar2/guru && ./run_hop.sh --burst`, then CALIBRATE.

### 2026-09-29 evening — over-the-air test (paused), in the copy `~/radar2/guru_ota` only
* HackRF antenna → 4 antennas on the 2945 (same PC, UDP control). guru57 / guru untouched.
* Found: a fan made a 70 Hz phase wobble (±3°) — seen in the phase spectrum; fan off removes it.
* Found: 5.2 GHz Wi-Fi bursts pulled the whole-band phase estimate (up to 175°) → in guru_ota the meter takes
  the phase only at the tone's own bins (±2 bins). Spread at 5.2 GHz 19–44° → ~7°.
* 5.2 GHz RX gain 60 → 70 dB in guru_ota (no overload).
* Measured: continuous 2 s, nothing moving: phase spread 0.44–0.87°. Hopping: 10,000 samples/dwell, 476/476 dwells
  with the tone, 0 unlocked; but dwell-to-dwell jitter 2.3–3.1° (**unexplained, open**) and ~40°/17 s slow wander
  (movement near the antennas). CALIBRATE rejects over the air (cable rule 0.3°).
* guru_ota commits `ec124fe`, `bb4cb81`; `ota_check.py` = RX-only over-the-air check.

### 2026-09-29 — guru57 frozen copy; 2 MS/s long-run fix
* User: "its working good and save this work properly take copy name it as guru57".
* `~/radar2/guru57`: own git (`1d267be`), 421 files, SHA256SUMS, `installed_snapshot/`, RESTORE.sh, `guru57.tar.gz`;
  lab tag `guru57` = `b3673fb`.
* TIMING LOST after 11 min at 2 MS/s (host ring full: all Python blocks share one core) → each meter processes
  only its own band, no DC remover at 200 kHz (`1c7fe33`). Long run (> 11 min) after this fix: **not yet proven**.

### 2026-09-28 20:00 — run of guru10ms; HackRF stalled; watchdog blind to it
* User ran `~/radar2/guru10ms/run_hop.sh --fast --restart` (my background start exited without a message;
  `import guru_fast` works — likely no GUI from my shell). Screen: SCHEDULE 8021 slots, 8020 used, 1 late,
  0 unlocked; LO LOCK all dwells; LAB TONE 5.2 GHz → **NO TONE (0/8 dwells)**, receiver OK.
* `/tmp/hackrf_tone.log`: **1387 × `Soapy sink error: TIMEOUT`, no `[watchdog]` line.** Cause: in this
  stall the gr-soapy sink keeps consuming samples (drops them with TIMEOUT), so `probe_rate` stays
  normal and the watchdog (rate < 25 % for 2 s) never fires. Fix designed, **not applied** (user
  interrupted): tap stderr and count TIMEOUT warnings per second; ≥ 3/s for 2 s → restart the stream.
* Earlier run 17:18–18:03 (from its log): 135,007 slots, 134,992 used, **15 late** (worst send
  19.6 ms > 13 ms limit), 0 unlocked, 0 skipped, 0 overflow, rtprio off.

### 2026-09-29 17:55–18:00 — DECISION: 200 kHz tone, 2 MS/s; burst mode works on every band
* User: "use 200k only, and 2 MHz sample rate". Lab `…`: guru_burst at 2 MS/s (dwell 10,000 samples), HackRF plain
  200 kHz (pure source), close-up waveform view + autoscale.
* Measured on the radio: CAL OK (worst window 0.05°); tone +190.8 / +180.2 / +177.9 kHz on 2.4 / 5.2 / 5.8 GHz
  (HackRF −3.8 ppm); 953.8 / 901.0 / 889.3 cycles counted; **samples / dwells = 10,000.000 exactly** (every reading);
  phases ≤ 0.1°; 5,630/5,632 slots (2 late, no rtprio); 0 unlocked; 0 overflow. Pictures
  `results/gui_burst_2Msps_200k_*MHz_20260929_1758.png`.

### 2026-09-29 17:40–17:52 — every band, TX pure source: counters exact; 2.4 GHz tone lands at 0 Hz
* User run 3.6 min: 17,989/17,995 used, 0 unlocked, 2.4 GHz tone +2,102…+2,217 Hz (TX clock), 5000 samples every dwell.
* Counters: mid-burst readings were off (19,408,754 / 3,881 = 5000.97) → totals now published together per complete
  burst: 20 random readings per band = **5000.000000** exactly.
* 2.4 GHz showed −8,828 Hz = the HackRF carrier leak taken as the tone (real tone inside the ±2 kHz guard) → meter now
  takes only the strongest line; inside the guard = NOT measured. Synthetic test passes.
* Radio now: HackRF −3.8 ppm (all bands agree) → 2.4 GHz tone at **+835 Hz → NOT measured**, CAL refused; 5.2 GHz
  −9,696 Hz (48.44 cycles), 5.8 GHz −12,053 Hz (60.23 cycles). With a pure-source TX, a 10 kHz offset cannot work on
  every band without a shared clock. Options for the user: REF OUT → CLKIN cable (exact 10 kHz everywhere) or a larger
  offset (e.g. 200 kHz).

### 2026-09-29 17:50 — DECISION: TX is only a source; everything measured on the RX
* User's run: 19,400,000 samples / 3,880 dwells = 5,000; tone 9,970.2 Hz → 49.84 cycles counted (9,970.2 × 5 ms =
  49.85). Question "if the tone and cycles vary, how are the samples fixed at 5000?" → two clocks: samples = X310 ticks.
* User: "everything should be calculated from the RX side; TX side is just a source" → the HackRF clock correction
  (fed back from RX to TX) is removed (lab `…`). HackRF sends plain 10 kHz; RX measures wherever it lands (≈ +3 kHz on
  2.4 GHz, ≈ −6 kHz on 5.8 GHz at −2.8 ppm); meters search both sides of 0 Hz. 50 cycles exactly only with the
  REF OUT → CLKIN cable. Not yet run on the radio (user's GUI running).

### 2026-09-29 17:40 — counters made independent; tone + cycles back on screen
* User restarted with run_hop --burst: transmitter v2 reports `ppm=-3.2186` (measured at start by asking it) — correct.
* User: "samples and dwells … calculate independently; tone frequency and cycles need real-time update". Engine now
  keeps two separate counters (dwell samples added packet by packet, pre-roll excluded; +1 per complete burst); screen
  line 1 = those, line 2 = tone Hz + cycles counted on the last dwell (lab `…`). Not yet run on the radio (user's GUI
  was running).

### 2026-09-29 17:25–17:35 — 87.75 cycles on the user's screen = my bug; bottom line simplified
* User's run: tone 17,549 Hz = 87.75 cycles; screen said clock "now −3.271 ppm (−6.417 at start)". Cause (mine): I had
  restarted the HackRF by hand with `--ppm 0`; `run_hop` kept it, and its start-up measurement ASSUMED the correction in
  `hackrf_ppm.txt` (−3.374) was active → computed −6.417, applied it → over-corrected. Receiver measured it correctly.
* Fix (lab `9f8d77e`): transmitter answers UDP `get` (its real correction); `tone_freq_check` asks it (refuses if it
  can't); run_hop restarts an older transmitter ('v2'); screen asks the transmitter each second.
* User: "no paragraph — just total samples received and number of dwells, updating; I divide them". Bottom line is now
  only `SAMPLES RECEIVED: n   DWELLS: m` (meter counters, every dwell of every band, 10×/s).
* Not yet verified on the radio (user's old guru_burst was running).

### 2026-09-29 17:05–17:20 — live sample counts; HackRF unplugged; CLKIN not in effect yet
* DWELL CHECK now live (10×/s): dwell number, samples counted between its marks + min/max of last 200, the radio's
  own burst count (5,250 = 250 pre-roll + 5,000) with its X310 time stamp, cycles COUNTED from the signal's rotation.
  Test: a 4,990-sample window is reported as 4,990. Radio: #1394 5000 [5000..5000].
* HackRF USB was unplugged (user, for the CLKIN cable): the new watchdog saw it (10 TIMEOUT/s) but its one restart
  failed ("No such device") and it never retried → fixed: retries every 3 s. Tone source restarted with `--ppm 0`.
* Measured with no correction: HackRF **−2.810 ppm** vs X310 on all bands → not running from the X310's clock yet.
  UHD turns X310 REF OUT on by default at every open (and the engine forces it) → cable not connected yet, or HackRF
  not accepting the level. Waiting for the user.

### 2026-09-29 16:45 — user's 16-min burst run; "in long run I should get 10 kHz and 50 cycles — root cause"
* Screen: 81,756 slots, 81,751 used (4 late, 1 skipped, 0 unlocked), **5000 samples every dwell**, phases
  +0.016/+0.029/+0.075°, but tone at 5.8 GHz **6,871.9 Hz → 34.36 cycles**. Still no rtprio (limit 0).
* **Root cause: two free-running clocks.** Samples counted with the X310's reference, tone made with the HackRF's
  crystal; they drifted −3.374 → −3.913 ppm = **0.54 ppm in 16 min** (3.1 kHz at 5.8 GHz). Software cannot fix that
  without faking. **Fix: one clock — X310 REF OUT → HackRF CLKIN.** Engine now switches REF OUT on at every start
  (lab `…`); screen shows the drift in ppm; meter log has time stamps + tone Hz per band.
* To verify after the cable: `tone_freq_check.py --offset 10e3 --applied-ppm 0` must show ~0 ppm on all bands, and
  again after 20+ min.

### 2026-09-29 16:25 — "LO lock not confirmed on every dwell"
* That text appeared with **unlocked 0**: the unused dwells were **late** (PC, no rtprio), not LO failures — the
  message lumped both. Now per band: `used N/M (not used: x not locked, y late, …)` and the SHOWING line names the
  reason (lab `8739f10`). The LO lock check itself: `lo_locked` read on ch2 at 6.5 ms, before the first used sample.

### 2026-09-29 16:00–16:18 — "signal not clean, distorted" (5.8 GHz picture) → clean display
* 5.2/5.8 GHz `tone_level_check` (HackRF VGA 47…27): no clipping (peak ≤ 0.125 FS), every line ≤ −37 dBc, but a
  **flat noise floor ~22 dB below the tone** over the 300 kHz display band, constant with HackRF level, identical on
  all channels = the HackRF's transmit noise (raw dwell: `results/raw_dwell_5800_20260929.png`). And 5.8 GHz arrives
  ~16× stronger than 2.4 GHz → drawn off the fixed ±0.6 plot (looked cut/peaky).
* Fix (lab `…` "clean display"): **±10 kHz zero-phase display filter around each dwell's tone, same filter on all
  channels** (phase untouched; measurements unfiltered) + autoscale. Synthetic test: ripple 3.95 → 0.62 %, phases exact.
* On the radio: CAL OK (worst window 0.05°), 3,632/3,632 slots, 0 late, 5,000 samples every dwell, clean sine at 2.4 and
  5.8 GHz, phases ≤ 0.07° (`results/gui_burst_clean_*_20260929_1617.png`). Cycles 41.1 (5.8) / 45.9 (2.4): HackRF
  drifted since its clock was last measured (my tests do not re-measure; `run_hop.sh --burst` does at each start).

### 2026-09-29 15:52–15:58 — quick verification (user: "check and verify fast")
* Full GUI program on the radio (offscreen), right after the start-up clock measurement: **5000 samples = 5.000 ms
  exactly**, tone 9,935 → 10,047 Hz = **49.7 → 50.2 cycles**, slots 2,633/2,633 and 2,947/2,947 used, 0 late.
* Raw phases changed since 13:28 (e.g. 2.4 GHz ch1−ch0 172.2° → −45.5°) after my test tools re-opened the X310 →
  CALIBRATE after every start stays mandatory.
* CALIBRATE was REJECTED (0.64–0.77°): it started while the HackRF still sent its old buffered baseband. Calibrator
  now waits 1.5 s + 5 dwells of a steady tone (lab `…` hop_calibrator). Next run: CAL OK (worst window 0.78°).
  ch2 spread in the GUI 0.16–0.26° (ch1/ch3 0.02°) — near the 0.3° limit; not loosened.

### 2026-09-29 15:45–15:52 — "why distorted / not continuous / why more than 50 cycles"
* User's screen: zoomed plot (troughs outside the zoom box = "not continuous"), not calibrated (−59°), 51.26 cycles.
* `tone_level_check.py` (HackRF VGA 14→30 dB, signal +16 dB): SNR in the 300 kHz display band stays **~28 dB** on all
  channels → the wobble scales with the signal. Residual after an ideal sine: **coherence 0.991–0.996 between
  channels**; receiver's own noise (HackRF moved away) **31–45 dB** below the tone → the wobble is **in the HackRF's
  signal** (phase/frequency noise; 96.6 % within 1 kHz of the tone = its drift), identical on all channels, so it
  cancels in chN − ch0 (phase spread 0.03–0.1°). Receiver does not distort. VGA left at 14.
* **More than 50 cycles:** HackRF clock vs X310 drifted **−4.5 → −5.2 → −3.2 ppm** today; with a stored correction the
  10 kHz tone landed at up to 14.5 kHz (72 cycles). `run_hop.sh --burst` now measures and applies the clock error at
  every start (`tone_freq_check --set-live`): right after it 9,960 / 9,856 / 9,780 Hz = **49.8 / 49.3 / 48.9 cycles**.
  It keeps drifting afterwards (shown per dwell). Exactly 50.00 for good: **X310 REF OUT → HackRF CLKIN**.

### 2026-09-29 13:10–13:40 — 10 kHz tone in burst mode: whole 5 ms dwell on screen, DWELL CHECK
* User: "in 5 ms I should receive 5k samples ... for 10 kHz I should see 50 cycles ... not distorted ...
  everything should be real, no fake, no fallback, 100 % real". Lab commit `ce7342e`.
* User's run 13:05 (guru_burst, 200 kHz): 131/2,995 late. Their process had **Max realtime priority 0**
  (the rtprio file exists; needs a new login) — all 89 threads normal priority.
* Measured: receiver 0 Hz leakage is only **13–16 dB below the tone** in every dwell (engine DC correction on).
  With a 10 kHz tone it must be removed per dwell (synthetic test: without it phase −175° for 25° true).
  Added: meter `remove_dc`, `hop_band_select remove_dc`, new `hop_dc_remove` (one-dwell delay; tested:
  tone amplitude exactly constant, tags on exact samples). Meter reports per dwell samples / tone Hz / cycles.
* HackRF clock vs X310: −4.894 ppm at 13:24 (3 bands within 0.011 ppm), `--ppm` correction added — but it
  **drifts**: tone seen at 9,177 … 10,828 Hz during the session → **45.9 … 54.1 cycles per 5 ms**. Not forced
  to 50 by any loop (that would be fake). Exactly 50.00 needs **X310 REF OUT → HackRF CLKIN**.
* CALIBRATE at 10 kHz first REJECTED (5.2 GHz 20/111 windows no tone): HackRF sends from a ~1 s buffer, so after
  a retune the old baseband continues ~1.2 s. Calibrator now waits for 5 dwells in a row with the tone (≤ 3 s).
* Result, full GUI program on the radio (offscreen), `results/gui_burst10k_tab0_20260929_1337.png`:
  every dwell **exactly 5,000 samples**, bursts 2,629/2,629, **CAL OK, phases +0.013 / −0.014 / +0.001°**,
  one whole dwell = clean sine on 4 channels, ~52 cycles (tone 10,347.6 Hz), Switching tab flat; 1 late in 2,343
  (no rtprio).

### 2026-09-29 12:25–13:05 — HackRF fix done; burst mode 5 ms ON / 7 ms switching built and measured
* **HackRF watchdog** (`hackrf_tone_source.py`, lab commit `069cdba`): GR 3.10 prints the Soapy TIMEOUT
  warning on **stdout**; the script's stdout/stderr now pass through a pipe that counts it (and forwards
  everything, flushed at exit). ≥ 3/s for 2 s → restart. Test with the real GR logger: healthy 0 restarts,
  1/s 0 restarts, 10/s → restart after 2 s.
* **10 kHz tone tried and dropped** (user: "in continuous which method we are using follow same in burst").
  Measured (`tone_freq_check.py`, results `tone_freq_20260929_12*.json`): the HackRF runs **−4.5 ppm** vs the
  X310 (−10.9 kHz at 2.4 GHz, −26.3 kHz at 5.8 GHz), drifting 8.8 kHz while warming up → a +10 kHz tone
  landed at −0.9 kHz on 2.4 GHz, on top of the receiver's 0 Hz leakage (which is *stronger* than the tone at
  2.4 GHz). Back to 200 kHz. Real fix if 10 kHz is ever needed: X310 REF OUT → HackRF CLKIN.
* **Burst mode** (lab commit `03f222b`, `~/radar2/guru/guru_burst.grc/.py`, `./run_hop.sh --burst`): engine
  sends a timed NUM_SAMPS_AND_DONE per dwell (0.25 ms pre-roll + 5,000 samples), checks every burst's start
  sample and length, puts it on the continuous timeline (zeros in gaps). Same chain/method as guru_fast;
  lock read at 6.5 ms; averaging 20 dwells; rt_priority 90 requested. `burst=False` = old continuous mode
  (regression: generated 10 ms flowgraph identical apart from the new params).
* Measured on the radio (no rtprio, GRC + Chrome open):
  * continuous CALIBRATE → table `phase_table_20260929_cont.txt` (2468/2468 slots, spread ≤ 0.13°)
  * **burst VERIFY: 4,112/4,112 bursts exact, every dwell exactly 5,000 samples, 0 unlocked, all bands
    ≤ 0.57°**; second run 2,360/2,360 exact, ≤ 1°
  * continuous VERIFY right after: ≤ 0.80° → the burst residual is drift, burst = continuous phase
  * **late: 598/4,112 (14.5 %) and 39/2,361 (1.65 %)** — timing record: UHD tune calls stall to ~6 ms
    (typical 2.27 ms) while the budget after the 6.5 ms lock read is ~5.5 ms. PC, not radio. Needs rtprio.
* Found: `~/radar2/guru/guru_fast.grc` was overwritten 2026-09-28 20:26 by a GRC save of an older version
  (no phase meter, plots on other tabs). `guru_fast.py` unaffected; the good .grc is in git and in guru10ms.
  Left as is — user to decide.

### 2026-09-29 — DECISION: no ping-pong; keep the current hardware setup
* User: "no we'll not go with ping pong ... follow that same hardware setup, only B can be the master".
* Fixed from now on: ch0 `external`, ch1 `external`, ch2 `internal` + export (the one synthesiser),
  ch3 `companion`; cables B J3→A J4, B J1→A J2; one synthesiser retunes at every hop.
* Consequence: switching cannot be shorter than that synthesiser's lock (5.40–5.84 ms single tune; locked
  by 7 ms with our 2nd pass) → realistic minimum ~6–7 ms, to be measured. Dwell 5 ms is possible.

### 2026-09-29 — user: does it work for a circular array too?
* Yes: the receiver, hopping and ping-pong do not depend on antenna layout. What changes is the DF maths:
  circular-array (UCA) steering vector a_n(θ) = exp(j·2π·R/λ·cos(θ − 2πn/4)), per band λ; gr-doa has only
  linear-array MUSIC → write UCA MUSIC ourselves. Pilot-at-known-angle antenna calibration is general.
* 4-element UCA, neighbour spacing d = R·√2 ≤ λ/2 → R ≤ λ/(2√2): 4.42 cm (2.4), 2.04 cm (5.2),
  1.83 cm (5.8 GHz) (calculated, not measured). Gives 360° azimuth; up to 3 sources; no elevation.

### 2026-09-29 — user: "ping-pong works only for linear array, 180° search?"
* Answered: no — the linear array / 0–180° limit belongs to AN-244's MUSIC direction finding (a linear
  array cannot tell front from back). Ping-pong is only an LO/tuning method (from a different Ettus
  example, one channel, spectrum sweep) and does not depend on antenna geometry. 360° needs a circular
  array + our own steering vectors (gr-doa implements linear arrays only). With 3 bands one spacing
  cannot be λ/2 for all: λ/2 = 6.25 cm (2.4), 2.88 cm (5.2), 2.58 cm (5.8 GHz).

### 19:20 — user: can both boards A and B be master (exporter) in ping-pong?
* Today only B exports (ch0 `external`, ch1 `external`, ch2 `internal`+export, ch3 `companion`) because
  **the A→B LO jumpers pass no LO** (measured 2026-09-19, twice, hours apart: ch0 as exporter → ch2/ch3 dead,
  tone +1.2 / −1.1 dB). B→A works. Cause: that cable pair faulty, unseated, or wired out-to-out
  (must be J3 OUT → J4 IN for LO1, J1 OUT → J2 IN for LO2). Known separately: RF A board has a 15.4 dB
  amplitude imbalance (ch0 weak port), phase coherence fine.
* Basic ping-pong does **not** need A as master: both synthesisers used are on board B.
* If the A→B pair is repaired, both boards can be master → **4 synthesisers for 3 bands** → each band can
  keep its **own synthesiser locked all the time** (no retune at all). Switch = only source/export switches;
  dwell no longer limited by lock time; a synth that never retunes keeps its phase state → table per band.
  Cost: each hop flips all 4 channels' sources and both boards' export at one radio time; A→B cable drift.
  To be measured, not assumed.
* Proposed order: (1) user checks the A→B jumpers (which connectors, seated); (2) `twinrx_lo_check.py
  --lo-sources internal,companion,external,external` with ch0 exporting to confirm A→B carries LO;
  (3) ping-pong test on board B (works with today's cabling); (4) if A→B works, the 4-synth fixed-LO test.

### 19:10 — user: "we are working with shared LO ... all LOs should be synchronized"
* Ping-pong keeps the shared-LO rule: at every instant **all 4 channels use one and the same synthesiser**
  (ch0/ch1 `external` via the cable, ch2/ch3 on board B, export follows ch2's source). The spare synthesiser
  feeds no channel while it tunes; at the hop all 4 channels move to it together.
* The two synthesisers never serve at the same time, so they do not need to be phase-locked to each other;
  both run from the same reference clock. The inter-channel phase (chN − ch0) is what is measured, and the
  common LO phase cancels in it.
* What changes: the LO reaches each channel by a slightly different path from synth A (ch2's) than from
  synth B (ch3's) → a phase table per (band, synth): with 3 bands and 2 synths the pattern repeats every
  6 dwells → 6 table rows, CALIBRATE measures all 6.
* Must be verified in the test: each (band, synth) state repeats its phase; no 180° states; the spare
  synth's retuning does not leak into the active LO (spurs / phase disturbance during the dwell).

### 19:00 — user: switching must be below 5 ms — is it possible by code?
* Answer: **not by making the retune faster** (the ~5.4–5.8 ms is the TwinRX synthesiser itself: ADF5355
  VCO auto-calibration + PLL lock, plus the SPI writes at 3 MHz, all executed in the radio's command queue —
  UHD source `adf535x.cpp` waits `_wait_time_us` during autocal).
* **Yes by a different method: ping-pong LOs** — Ettus's own `host/examples/twinrx_freq_hopping.cpp`
  (default hop interval 5 ms): while one LO set receives, the spare LO set is tuned to the next band; at the
  hop only the LO **source switch** flips (`internal` ↔ `companion`).
* Our mapping: board B has two LO sets (ch2's, currently exported, and ch3's, currently idle because ch3 is
  `companion`). UHD source `twinrx_experts.cpp` l.333–345: the exported LO **follows** the exporting
  channel's source (ch2 `companion` → exports ch3's synth), so board A (`external`) follows the flip and all
  4 channels stay on one LO.
* Unknown until measured: switch time after the flip; whether the phase repeats (the 180° / wrong-state
  problem of a single timed tune may come back); whether the spare LO locks within dwell + switch
  (5 ms + 1 ms = 6 ms vs lock 5.4–5.84 ms single pass, 2nd pass unknown) → dwell 5 ms is at the edge;
  spurs from the spare synth retuning during a dwell.

### 18:45 — user: move to 5 ms, solve the open problems during that work
* User: "we need to move 1 more step like 5ms ... during that time only we'll solve these problems also".
* Facts that decide 5 ms (measured): LO lock after a **single** timed tune = 5.40–5.84 ms after T
  (`timed_tune_20260928_122715.json`, 300 hops). Our phase-correct method adds a 2nd pass at S+3 ms;
  its lock time has never been measured on its own (only "locked at S+7 ms" in > 100,000 slots).
* So: **5 ms dwell is possible; 5 ms switching is not** with this tune (the LO is still unlocked at 5 ms).
* The PC's time per slot shrinks (lock read at S+7 ms, next batch must be sent before the next S):
  10/10 → 13 ms; 5 dwell/10 switch → 8 ms (worst send seen with GUI ~9 ms). So the real-time
  settings (problem A) become required, not optional — they get solved inside the 5 ms work.
* Plan: (1) measure lock time of the exact method → shortest safe switch; (2) rtprio + CPU performance;
  (3) 5 ms dwell with that switch: exact-sample check, then 30-min GUI soak, target 0 dropped;
  (4) drift + automatic recovery along the way. guru10ms stays untouched; work in `~/radar2/guru`,
  save as `guru5ms` when verified.

### 18:35 — requirement: receiver side 100 % correct
* User: "for testing only we are using hack rf ... i need receiver side should be 100% correct".
* Already true by design and measured: a dwell is used only if its band, LO lock and exact timing are
  confirmed; everything else is discarded and counted. **No wrong number is ever shown.**
* Not yet 100 %: (A) dropped dwells, 3 / 90,008 in the 30-min GUI soak (Linux late); (B) phase accuracy
  between calibrations (drift up to ~8° / 16 min, receiver LO cable A↔B); (C) no automatic recovery
  after lost samples (untested).
* Plan proposed: Stage 1 timing (rtprio 95 + CPU `performance`, engine threads pinned to own cores;
  target 0 dropped in 30 min). Stage 2 automatic resync after sample loss, tested by forcing a stall.
  Stage 3 one-hour drift log with a fixed table → calibration interval from numbers; phase-stable LO
  cable as the permanent fix (software cannot make a cable's thermal drift zero).

### 18:25 — work log started
* User: "every time keep updating things on .md file ... some time we need to compact the session".
* Created this file. From now on every stage is written here as it happens, committed and pushed
  to `guru10ms`.

### 18:20 — repo pushed to GitHub
* User gave https://github.com/shankarjatti/guru10ms: "every small information should be there ... every related file".
* Repo was empty and **public**; asked the user — answer: **push as public**.
* Added: raw `.npz` results (110 MB) + `results/README.md` (every run with its own verdict),
  `docs/DEVELOPMENT_LOG.md`, `docs/lab_notes/`, lab git history, `third_party/gr-doa` source + patch vs
  upstream `7f982b7`, `environment/` (versions, network, `uhd_usrp_probe`), `earlier_work/lo_sharing/`,
  `logs/`, landing `README.md`.
* Checked before push: no secrets (grep for tokens/keys/passwords), 0 broken links, 366 files in SHA256SUMS.
* Pushed 2 commits (`45c7579`, `35a5bfe`). Fresh clone from GitHub: all 366 files intact.
  GitHub warned on one 85 MB file (limit is 100 MB) — uploaded complete.
* Found: `results/sched_10on_10off_20260928_122954.json` is incomplete (numpy-bool JSON bug); marked so.
* Left out on purpose: `guru2/3/4`, `guru_phase`, `guru_doa`, `gururaj` (older/stale), `BACKUP_*` (duplicates).

### 18:10 — safe copy `guru10ms` made
* User: "KEEP THIS WORK SAFE MAKE A COPY OF IT AND NAME IT AS A guru10ms".
* `run_hop.sh` changed to run the files in its own folder (commit `d135177`, tag `guru10ms` in `~/radar2`);
  from `~/radar2/guru` behaviour is unchanged.
* `~/radar2/guru10ms/`: project + `installed_snapshot/` + `RESTORE.sh` + `SHA256SUMS`.
* Verified: installed blocks = copy; engine rebuilt from the copy is byte-identical to the installed one;
  `hop_blocks_selftest.py` passed; `guru_fast.grc` regenerates the same `guru_fast.py`.

### Before 18:00 — guru_fast built and verified
* See [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md) §3–§5 (stages 1–14, all measurements, all fixes).
