# MON ↔ DF switching — how it was built and what was measured (2026-09-30)

Setup for every test: cable — HackRF One, plain 200 kHz tone, 2 MS/s, VGA 14 (900 MHz, 2.4 GHz) / 47 (5.2, 5.8 GHz)
→ power divider → the 4 TwinRX ports; X310 over Ethernet (1 Gb/s link) at 192.168.10.2; GNU Radio 3.8 +
UHD 3.15; real-time priority 90 granted. The HackRF is only a source: nothing it says is used in a measurement.

## Starting point: two separate works (both frozen)
| | DF — `guru_DF_v1` | MON — `guru_MON_v1` |
|---|---|---|
| what | shared LO, coherent hopping 2.4 → 5.2 → 5.8 GHz, 5 ms dwell + 7 ms switching, burst mode, C++ engine | each channel its own LO: ch0 900 MHz, ch1 2.4, ch2 5.2, ch3 5.8 GHz, continuous |
| proven | 10,000 samples every dwell, CALIBRATE ≤ 0.1° | only the tone band's channel sees the tone; board-mate leak 54–57 dB below |

User's plan: continuous monitoring of all bands (10 MHz–6 GHz), edge modules request DOA on a band, the receiver
schedules DF on it, then returns to monitoring — built step by step. This repo is the MON ↔ DF switch (the part
before the USRP); DOA itself is another team's work.

## Step 1 — does the DF phase survive a trip through MON? (`switch_check.py`)
pyuhd only. Per DF band: calibrate a reference, then 50 × (DF → MON with ch0..3 on 0.9/2.4/5.2/5.8 GHz for 0.2 s →
DF) interleaved with 50 × a plain DF retune (away and back) as the baseline.

* First trial tuned **untimed** → after any retune, also the baseline, the phase jumped by **exact multiples of 90°**
  = the LO divider state (THEORY §3). Test error, fixed by using the engine's timed staggered second-pass tune.
* Result (`results/switch_check_20260930_161434.json`):

| DF band | worst phase change after a MON trip | after a plain DF retune |
|---|---|---|
| 2.4 GHz | 0.33° | 0.26° |
| 5.2 GHz | 0.20° | 0.14° |
| 5.8 GHz | 0.22° | 0.12° |

  extra caused by the switch 0.03–0.11° (mean); MON set up correctly 150/150; 0 lock timeouts; routing ~2 ms;
  lock confirmed 4–8 ms after the timed tune. → **No recalibration is needed when returning to DF.**
* Caveat found: between two program starts ch2's reference came up 180° apart → calibrate at every start.

## Step 1b — two facts the engine design needs (`route_burst_test.py`)
* **Timed routing**: routing + tune scheduled at T in a running DF setup, one burst over T−3 ms … T2+15 ms:
  ch0's tone vanished **0.12 ms after T in 10/10 trips, never before**; back 6.1–6.4 ms after T2; phase back ≤ 0.16°.
* Commands run strictly **in order**: a burst for T−3 ms issued after the T/T2 commands → `LATE_COMMAND`.
* 200 burst commands at once → only 32 ran (queue depth).

## Step 2 — the engine (`oot/engine/twinrx_engine.cpp`) and the source block (`switch_source.py`)
Checked without a GUI by `switch_engine_check.py` (a TEST that switches by itself; a sink measures every DF dwell's
phase and every MON dwell's tone as it arrives).

Problems found and fixed, in order:
1. My sink's `work()` had the wrong argument names → ring full → TIMING LOST (test bug).
2. **All 10 switch slots late** (send 30–45 ms). Timing record: each timed routing call blocked the host until S —
   the routing setter reads the TwinRX back and the read waits behind the timed write — so the tune after it went
   out after its time. Fix: routing **untimed after the old dwell has ended**, timed tune `switch_gap` (10 ms) later.
3. DF "dwells" of 60,000 and MON of 90,000 samples: the old mode's last dwell ran on into the switch gap because its
   end mark came with the new slot. Fix: end marks exactly at the end of the old dwell (`hop_off` −1, `mon_off`).
4. One run had 165 late DF slots with the same code — DF band changes took 4 ms instead of 1.1: a kernel worker at
   62–67 % CPU (D state), remote desktop, CPU governor `powersave`. The DF-only baseline and the next run: 0 late.

Result (burst-mode MON, 5 cycles DF 2 s / MON 2 s, tone on 2.4 GHz): 1558/1558 slots used, 0 late / unlocked /
missing, 10/10 switches locked; DF phase after each return ≤ 0.26°; every DF dwell 10,000 samples and MON dwell
40,000; only ch1 sees the tone (84.8 dB), ch0 34 dB (board-mate leak), ch2/ch3 noise; request → first dwell
DF→MON 24–33 ms, MON→DF 39–48 ms.

## Steps 3–4 — GUI and control
`make_guru_switch.py` builds `guru_switch.grc` from the verified DF flowgraph (`guru_burst.grc`) — every DF block,
tab and snippet unchanged on outputs 0–3 — plus the MON tab, the MODE selector and a mode line.

* First start: **TIMING LOST at once** — a Python MON meter on all 4 MON streams at 2 MS/s + 8 displays on top of
  the DF chain's Python blocks (one interpreter lock). Fix: MON path C++ only (probes, thinned displays), MON count
  from the engine. After that: no TIMING LOST.
* MON band-statistics key was a string ("MON") → the DF lock line crashed every poll → key −1.0.
* A repeated request (the selector following an API request) moved the request time → a repeat is no new request.

## Step 5 — validation through the (then enabled) control API (`switch_validate.py`)
151 switches in 566 s (random 1–6 s holds), burst-mode MON (`results/switch_validate_20260930_173117.json`):
150/151 switches locked and used (1 not used, marked); bursts 50,720 ok / 0 missing; no TIMING LOST;
DF 2.4 GHz phase over the whole run (guru's own meter): worst change 0.09 / 0.28 / 0.15°;
request → first dwell to DF 46.6 ms mean (worst 56.3), to MON 27.8 ms (worst 33.5); routing 1.0 ms mean (worst 4.0);
555/50,722 slots late (1.1 %, marked, never used) — PC latency.

## User decisions (2026-09-30)
* **"MON work should be in continuous mode … don't follow burst mode there"** → MON = ONE continuous stream (timed
  start, stop at the switch back). DF stays burst.
* **"Don't set auto changing mode between MON and DF; that should be manually controlled"** → the program never
  switched by itself (the automatic switching seen was the validation script); the control API is **off by default**,
  the mode changes only with the MODE selector.

## Continuous MON — result
`switch_engine_check.py`, 10 cycles: 0 missing bursts, DF phase after each return ≤ 0.27°, every DF dwell 10,000
samples, 1000 MON records all locked, MON→DF now 20–29 ms, DF→MON 23–33 ms (the stop needs no wait for a 20 ms
burst). The last MON piece before a switch is short (~1,300 samples): the stream really ends where the stop lands.
First continuous run had 10 missing bursts (= the number of switches) — **not reproduced in 3 runs since, open**.

## 30-minute run by the user (18:12–18:42)
CALIBRATE OK (worst window 0.06°), 7 manual mode changes; TIMING LOST 0, tracebacks 0, HackRF 0 new TIMEOUTs;
DF 2.4 GHz in every reading: tone +192.6…193.1 kHz, 10,000 samples per dwell, phases after CAL ch1 +0.05…+0.13°,
ch2/ch3 +0.26…+0.52° (slow warm-up drift ~0.2° / 20 min, spread ≤ 0.08°).

## Transmitter (lab only) fixes found on the way
* A HackRF stall during 5.8 GHz came back "restarted on 2.4 GHz" — a band request during the restart went to the dead
  flowgraph → the band last asked for is kept, restart and UDP commands share a lock.
* A replugged HackRF never recovered in-process (1843 failed retries) and a stalled one stalled again after every
  in-process restart (7046 TIMEOUTs) → after 3 failed restarts or 3 stalls within 60 s the transmitter re-execs
  itself as a fresh process on the last band. Its USB device number went 006 → 009 → 013 during the day: it drops off
  USB (cable / port / power) — hardware to fix.

## Open
* ~1–2 % DF slots late when the PC is busy (marked, never used); performance governor is a user setting.
* The 10 missing bursts of the first continuous run (not reproduced).
* ch0 (A/RX1) RF path 13–16 dB low on every band (`mon_port_check.py`) — cable / divider output / port.
* MON bands are fixed at start (`make_guru_switch.py --mon`); live retuning of MON, more bands, request-driven DF
  (priority scheduler) are the next steps of the user's plan.
