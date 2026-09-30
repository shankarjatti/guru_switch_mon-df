# USRP-2945 / TwinRX — LO configuration and phase coherence

GNU Radio 3.8.5 + UHD 3.15.0 (the isolated install under `~/gnuradio-3.8` and
`~/uhd-3.15`).

Files here:

| File | What it is |
|---|---|
| `twinrx_lo_check.py` | Pure-UHD command-line verifier. Run this first. |
| `twinrx_lo_coherence.grc` | GRC flowgraph: LO config + live phase-coherence display. |
| `b210_tone_source.py` | CW calibration source on a B210. Runs under the SYSTEM UHD. |
| `twinrx_band_check.py` | Drives both radios across frequency; `--monitor` for a live display. |
| `twinrx_lo_cal.json` | Measured phase offsets, tagged by method and RX gain. |
| `TWINRX_LO_NOTES.md` | This file — the technical reference. |
| `SESSION_LOG.md` | How this was built, what went wrong, and what is outstanding. |
| `RUNBOOK.md` | Every command, in order. Start here. |
| `BLOCK_DIAGRAM.md` | Signal chain, LO routing and DSP, annotated with expected values. |

---

## 0. What the USRP-2945 actually is

An X310 motherboard with **two TwinRX daughterboards** in slot A and slot B.
That gives four RX channels:

```
UHD channel   subdev   daughterboard   SMA
    0          A:0      TwinRX #1      RX1
    1          A:1      TwinRX #1      RX2
    2          B:0      TwinRX #2      RX1
    3          B:1      TwinRX #2      RX2
```

Master clock rate is **fixed at 200 MHz** on TwinRX. Gain range is 0–93 dB.

---

## 1. Why LO configuration is the whole problem

Each TwinRX is a **dual-conversion** receiver: RF → LO1 → IF → LO2 → baseband.
Each board carries **two complete synthesiser sets** (one per channel), so a
bare 4-channel system has four independent LO1s and four independent LO2s.

Independent synthesisers lock to the same 10 MHz reference but each comes up in
a **random phase**. The channels are frequency-locked but not phase-locked, so
the phase difference between channels drifts and re-randomises on every tune.
Useless for direction finding, beamforming, or any interferometric radar.

The fix is to run every channel from **one physical synthesiser**. TwinRX can
export its LO1 and LO2 and take them back in:

| Connector | Signal | Level |
|---|---|---|
| J3 | LO1 export (out) | 5 dBm nominal |
| J4 | LO1 input (in) | −5 dBm nominal, 10 dBm damage |
| J1 | LO2 export (out) | 3 dBm nominal |
| J2 | LO2 input (in) | 2 dBm nominal, 20 dBm damage |

Between the two TwinRX modules the MMCX cables go **crisscross** — J1↔J2 and
J3↔J4, both directions — so either board can be the exporter.

Then one channel's synth drives all four channels, every downconversion uses the
same phase reference, and the residual phase differences are **fixed cable and
trace delays** that you calibrate out once.

---

## 2. The five LO source values UHD accepts

From `twinrx_experts.cpp` in UHD 3.15 — these are the exact strings:

| String | Meaning |
|---|---|
| `internal` | this channel's own synthesiser drives it |
| `companion` | take the **other channel's** synthesiser, same daughterboard, on-board trace |
| `external` | take the LO from the **LO IN connectors** (J4 = LO1, J2 = LO2) |
| `reimport` | run my own synth, export it, **and take it back in through LO IN** |
| `disabled` | this channel uses no LO; frees its synth for the other channel to use as a hop buffer |

Two rules the driver enforces, which is where most people's first attempt dies:

- **A channel sourcing `external` may not export.** `Cannot export an external
  LO for channel N`. Obvious once stated: there is nothing of its own to export.
- **Only one channel per board may export.** `Cannot export LOs for both
  channels`.

`reimport` is the subtle one. Switch-wise it is identical to `external` (the RF
path comes from the LO IN port), but the driver still treats it as this
channel's synthesiser for tuning purposes — so the synth gets programmed, and
export is allowed. Use it when you feed the exported LO through a **power
splitter back into the master's own LO IN**: then both boards see the same
cable, so their delays match instead of the master having a short on-board path
and the slave a long cable.

### The switch tree these strings select

Each TwinRX board holds **two channels, each with its own complete
synthesiser** — so your 2945 has four synthesisers in the chassis. Each
channel's LO input is a three-way choice built from three switches
(`twinrx_ctrl.cpp`, `set_lo1_source` / `set_lo2_source`):

```
                                  ┌── its own synth ───────────► "internal"
                                  │
   ch0's mixer ◄── SW16 ◄─────────┤
                                  │           ┌── J4 (LO IN) ──► "external"
                                  └── SW15 ◄──┤                  "reimport"
                                              │
                                              └── SW14 ◄────────► "companion"
                                                  (the OTHER channel's
                                                   synth, on this board)
```

- `SW16` picks own-synth versus everything else
- `SW15` picks the LO IN connector versus the on-board cross-feed
- `SW14` sits on the *other* channel's synth output and gates the cross-feed

And how that maps onto the four channels:

```
   DB-A (TwinRX #1)                      DB-B (TwinRX #2)
  ┌──────────────────────┐              ┌──────────────────────┐
  │ ch0  internal ◄─┐    │   LO cable   │ ch2  external ◄──┐   │
  │                 ├─ SYNTH ═══════════╪══► LO IN ────────┤   │
  │ ch1  companion ◄┘    │  (J3 → J4)   │ ch3  external ◄──┘   │
  └──────────────────────┘              └──────────────────────┘
      one synthesiser                    zero synthesisers used
      feeding both channels              both fed from the cable
```

### Why `companion` is phase-stable and `external` is not

`companion` is a **trace on the PCB**. The partner channel sees the same signal
the synth is producing, same edge, nothing in between. There is no state that
can come up wrong.

`external` leaves a connector, crosses a cable, enters another board, and passes
through a **frequency divider** in that board's LO distribution before reaching
the mixers. A divider is a counter: when enabled it starts wherever it starts,
so the output is right in frequency but ambiguous in phase by 360°/N.

The switch topology above is confirmed from the driver source. The divider is
the standard explanation for the quadrant jumps reported in the UHD issues, but
**it was not confirmed on this unit** — the evidence that looked like it came
from a broken estimator and from DC-leakage data, both withdrawn. With a real
tone the phases are stable. Treat it as a known risk to watch for, not an
established behaviour here.

---

## 3. The configuration this project uses

**On this unit, Rx B is the exporter** — the A→B LO jumpers pass no LO:

```
ch0  A:0   external    export = False
ch1  A:1   external    export = False
ch2  B:0   internal    export = True     <-- the one synthesiser
ch3  B:1   companion   export = False
```

Measured: phase repeats to **1.5°** across retunes, against 179° with each
board on its own LO. See section 6c.

The textbook form, if your A→B jumpers work, is the mirror image:

```
ch0  A:0   internal    export = True
ch1  A:1   companion   export = False
ch2  B:0   external    export = False
ch3  B:1   external    export = False
```

On the **slave** board both channels take `external` — its LO IN is split
internally. Note which board is which: above, Rx A is the slave, so ch0 and ch1
are both `external`, while on the master Rx B the partner channel ch3 is
`companion`. If you set ch3 to `companion` the driver decides slave-ch3 is being
driven by the slave board's own synthesiser and **programs a second synth** —
and you are back to two independent LOs.

Sanity check in your head: after configuration, exactly one synthesiser in the
whole chassis should be getting tuned.

To make the two boards' LO paths symmetric, change ch0 to `reimport` and add a
2-way splitter on the master's LO export, one output to the master's own LO IN,
the other to the slave's LO IN. Both files take this as a parameter.

---

## 4. The other half of the problem: tuning

Sharing the LO is necessary but not sufficient. Tuning has to be atomic too.

`set_rx_freq()` on a TwinRX is not one register write — it is a long burst of
SPI transactions (band select, preselector, amps, both synthesisers). Issue that
per channel with no timing and each channel's LO lands on a different clock
edge.

So: wrap the tune in a **timed command**.

```python
usrp.set_command_time(usrp.get_time_now() + uhd.types.TimeSpec(0.1))
for ch in range(4):
    usrp.set_rx_freq(tune_request, ch)
usrp.clear_command_time()
```

**And do it twice.** The X310's command FIFO is 16 entries deep; a cold TwinRX
tune needs more than that, so part of the first timed burst spills out and
executes untimed. The driver caches band/filter/synth state along the way, so
an immediately repeated, identical burst is short enough to fit and lands
atomically on all four channels. This also cures the "one channel drops 40–50 dB
after a timed tune" symptom that shows up on the Ettus mailing list.

Both files here tune twice by default. `twinrx_lo_check.py --single-tune` turns
it off so you can see the failure for yourself.

Last detail: the tune request pins every **DDC to 0 Hz**
(`dsp_freq_policy = manual`, `dsp_freq = 0.0`), so the digital stage contributes
no per-channel phase and anything you measure is purely RF.

---

## 5. Micro-steps

### 5.1 Hardware

1. Power off. Open the chassis lid.
2. Confirm four MMCX cables between the two TwinRX modules, crisscrossed:
   J1↔J2 and J3↔J4 in both directions. NI usually fits these at the factory on a
   2945 — verify rather than assume.
3. Route the cables **below the heatsink line** before refitting the lid.
4. Feed one CW tone into all four antenna ports through a 4-way splitter with
   **equal-length cables**. Unequal cables are a real phase offset and will make
   a working system look broken.
5. Offset the tone from your centre frequency — say centre 2.400 GHz, tone
   2.4002 GHz — so it is not sitting in the DC notch.
6. Keep the tone at least 20 dB below the TwinRX damage level; start at −40 dBm
   and 30 dB gain.

### 5.2 Environment

The default shell has **UHD 4.10 and GNU Radio 3.10** on `PATH`. You must source
the isolated env or nothing below will behave as documented:

```bash
source ~/gnuradio-3.8/setup_env.sh
```

It should print `GNU Radio v3.8.5.0` and `UHD 3.15.0`. Then confirm the device:

```bash
uhd_find_devices
```

```bash
uhd_usrp_probe --args "type=x300"
```

In the probe output you want to see **two** TwinRX daughterboards, and under
each RX frontend an `LO` section listing `LO1` and `LO2`. If the LO section is
missing, UHD did not probe the boards as TwinRX and nothing else will work.

### 5.3 Verify the LO configuration from the command line

```bash
python3 ~/radar2/twinrx_lo_check.py --freq 2.4e9 --trials 3
```

Read the output in order:

- **STEP 1** — each channel should list `LOs=['LO1', 'LO2']` and sources
  including `external`. If a channel shows no `external`, stop: bad cabling or
  bad subdev spec.
- **STEP 2** — every readback should match the request, with `export=True` on
  exactly one channel.
- **STEP 3/4** — per-trial phase of each channel vs ch0, plus a `coherence`
  number. Coherence near 1.0 means a clean stable tone; near 0 means the
  channels are sliding against each other.
- **VERDICT** — the spread of each channel's phase across repeated retunes.
  Under 5° is a pass.

Then prove the offsets are repeatable across frequency:

```bash
python3 ~/radar2/twinrx_lo_check.py --sweep 1e9,2e9,3e9,4e9,5e9 --trials 5
```

And, once, see what you are being protected from:

```bash
python3 ~/radar2/twinrx_lo_check.py --freq 2.4e9 --single-tune --trials 5
```

### 5.3b Inject a calibration tone from a B210

`twinrx_lo_check.py` receives only — it never transmits. Without a coherent
signal on all four ports the only thing correlated across channels is LO
self-mixing leakage at DC, which proves LO sharing but is **not** an RF path
calibration.

`b210_tone_source.py` provides the signal:

```
  B210 TX/RX --> 30 dB fixed pad --> 4-way splitter --> the four 2945 RX ports
                 ^^^^^^^^^^^^^^^                        (equal-length cables)
```

The pad is the safety interlock, not a nicety:

| | |
|---|---|
| TwinRX damage threshold | **+10 dBm** |
| TwinRX ADC full scale at *minimum* RX gain | **−20 dBm** |
| B210 TX at max gain, no pad, after a 4-way split | **+3 dBm** — 23 dB into saturation |
| B210 TX at max gain, **with** 30 dB pad | **−27 dBm** — below full scale |

Estimated level at each RX port (amplitude 0.5, 30 dB pad, 7 dB split loss):

| TX gain | B210 out | at each port |
|---|---|---|
| 0 dB | −85.8 dBm | −122.8 dBm (too weak) |
| 40 dB | −45.8 dBm | −82.8 dBm |
| 50 dB | −35.8 dBm | −72.8 dBm |
| 60 dB | −25.8 dBm | −62.8 dBm |

Two terminals, single frequency:

```bash
source ~/gnuradio-3.8/setup_env.sh && python3 ~/radar2/b210_tone_source.py --freq 2.4e9 --gain 0
```

```bash
source ~/gnuradio-3.8/setup_env.sh && python3 ~/radar2/twinrx_lo_check.py --freq 2.4e9 --trials 3
```

Ramp `--gain` in 10 dB steps until the checker reports the tone 30–40 dB above
the floor. Do not chase full scale. Record the TX and RX gains you settled on —
the calibration is only valid at those gains.

The tone sits at centre **+200 kHz** by design, outside the checker's ±20 kHz
`--tone-guard`, so DC leakage and the real signal can be told apart. The source
refuses `--offset 0` for that reason, and refuses to start above `--max-gain`
(default 60 dB) so a typo cannot slam the front ends.

### 5.4 Run the flowgraph

```bash
~/gnuradio-3.8/run_grc.sh ~/radar2/twinrx_lo_coherence.grc
```

Or headless:

```bash
source ~/gnuradio-3.8/setup_env.sh && python3 ~/radar2/twinrx_lo_coherence.py
```

What you get:

- **Control & Phase tab** — centre frequency and gain sliders, a time plot of
  ch1/ch2/ch3 phase relative to ch0 in degrees, and three big numbers showing
  the steady-state offsets.
- **Spectra tab** — all four channel spectra overlaid. A channel 40–50 dB down
  means its LO never locked.

Read it like this:

| What you see | What it means |
|---|---|
| Three flat lines, any constant value | LO is shared. Working. Calibrate the constants out. |
| Lines ramp / sawtooth | Channels on independent synthesisers. LO sharing is not happening. |
| Lines flat but jump by 90°/180°/270° after a retune | The known TwinRX external-LO quadrant ambiguity — see below. |
| One trace noisy, its channel low in the spectrum tab | That channel's LO is not locked, or its RF cable is bad. |

Move the **Center Freq** slider. A background thread re-runs the whole timed
double-tune sequence — this is deliberate. A normal GRC callback would call
`set_center_freq()` per channel, untimed, and destroy coherence. The console
prints each retune.

The phase values will change when you retune; that is expected, because a fixed
cable delay τ produces a phase 2πf·τ that depends on frequency. What must not
change is the value **at a given frequency, across repeated tunes to it**.

---

## 6. The 90° ambiguity

Channels sourcing `external` sometimes come up at a phase offset that is a
multiple of 90° different from last time, re-rolling on every power cycle and
sometimes on every retune. Channels sourcing `companion` do not do this.

Cause: the LO divider in the receiving board starts in a random quadrant.

It is a known, long-standing TwinRX behaviour — see
[uhd#237](https://github.com/EttusResearch/uhd/issues/237),
[uhd#670](https://github.com/EttusResearch/uhd/issues/670),
[uhd#769](https://github.com/EttusResearch/uhd/issues/769).

### Observed on this unit, 2.4 GHz

Two runs of `twinrx_lo_check.py` separated by a GRC session:

| ch | LO source | run 1 | run 2 | delta |
|---|---|---|---|---|
| 1 | `companion` | −17.58° | −19.32° | **−1.74°** |
| 2 | `external` | −19.21° | +158.46° | **+177.67°** |
| 3 | `external` | +84.39° | −89.94° | **−174.33°** |

Within each run the spread was 0.5–0.7°. The lock is solid; what moved is the
absolute phase of the slave board.

Two things to read off this:

- The `companion` channel did not move. The `external` channels did. That is
  the documented split, confirmed on this hardware.
- **ch2 and ch3 moved together**, both by ~180°. They share one LO IN port on
  DB-B, so there is one divider and one quadrant state for the whole board.
  The relative phase between the two slave channels is preserved (103.6° vs
  111.6° — the 8° residual is thermal drift plus ch3's poor SNR).

So the practical unit of uncertainty is **per daughterboard, not per channel**.

Practical responses, in order of preference:

1. **Don't retune.** Configure once, run continuously. The offset is stable for
   as long as the LO is not re-programmed.
2. **Calibrate per tune.** Inject a known reference tone, measure the four phase
   offsets, correct in software. This is what the `gr-aoa` blocks you already
   have installed expect anyway — the DF app note's array calibration step
   exists precisely for this.
3. **Stay within one daughterboard** for anything requiring 2 channels. The
   `internal` + `companion` pair on a single TwinRX is rock solid; the ambiguity
   only affects `external`.

`twinrx_lo_check.py` keeps a calibration file (`twinrx_lo_cal.json`, override
with `--cal-file`) and diffs each run against the last, so section (B) of the
verdict tells you directly whether the quadrant re-rolled since you last looked.
`--no-save` measures and compares without updating the baseline.

---

## 6b. What a measured phase offset is actually made of

```
  measured phase  =  RF cable length difference      (grows with frequency)
                  +  internal RF path for that band  (jumps at band edges)
                  +  LO divider quadrant on DB-B     (multiples of 90, re-rolls)
                  +  gain / attenuator state         (changes when you move gain)
```

Measured on this unit, 5 frequencies x 5 trials, ch0 as reference:

| f | band | ch1 | ch2 | ch3 | ch3−ch2 |
|---|---|---|---|---|---|
| 1 GHz | LOW | −14.57° | −24.35° | +84.77° | +109.1° |
| 2 GHz | HIGH | −3.65° | −4.65° | +102.57° | +107.2° |
| 3 GHz | HIGH | −30.24° | −56.18° | +53.96° | +110.1° |
| 4 GHz | HIGH | −11.97° | −18.24° | +93.87° | +112.1° |
| 5 GHz | HIGH | −27.52° | −29.74° | +83.92° | +113.7° |

Two things fall straight out:

- **ch3−ch2 is nearly constant** (109→114° over 4 GHz, i.e. 1.4°/GHz). A cable
  length difference would scale with frequency — 109° at 1 GHz would be 545° at
  5 GHz. It isn't. So the two DB-B channels are separated by a **fixed circuit
  offset** (~106° extrapolated to DC plus ~3.9 ps of real delay), not by
  propagation. Their relationship is rigid, which is why they re-roll together.
- **ch1−ch0 has no trend at all** despite both being on DB-A off one synth.
  That is the **per-band RF path**: TwinRX has 8 bands (LB1–4 below 1.8 GHz,
  HB1–4 above), each with its own preselector, amplifier chain and LO plan.

### Consequences for calibration

1. **Calibrate per band, and never interpolate across a band edge.** 1 GHz is
   low band; 2–5 GHz are high band. They share nothing.
2. **Calibrate at your operating gain.** TwinRX gain is switched attenuators and
   each attenuator state has its own phase. A calibration taken at 30 dB does
   not apply at 2 dB.
3. **Watch the reference channel.** Phases are always relative, so if ch0 itself
   wanders, every other channel appears to move. `twinrx_lo_check.py` reports a
   `resid` column with the per-trial common mode removed, which separates
   "ch0 drifted" from "the channels lost coherence". A large `raw` spread with a
   small `resid` spread means the array is fine and your reference is not.

---

## 6c. Validated setup on this unit (2026-09-19)

Verified against a real B210 CW source at 2400.2 MHz through a splitter into
all four RX ports. Health first:

```
  mboard        : X310   serial 31082D8      master clock 200.000000 MHz
  ch0/ch1       : TwinRX Rev B  dbserial 3104B3C   (Rx A)
  ch2/ch3       : TwinRX Rev B  dbserial 31050CD   (Rx B)
  ref_locked    : True
  stream errors : 0
```

Every LO configuration, measured back to back. "tone dB" is per channel,
above 6 means genuinely receiving; "phase repeats" is the spread over two
retunes:

| configuration | ch0 | ch1 | ch2 | ch3 | result |
|---|---|---|---|---|---|
| own LO each board | 13.5 | 23.4 | 11.6 | 12.6 | all receive, phase repeats **179.4°** — not coherent |
| A internal+export → B external | 15.6 | 23.9 | 1.4 | 0.4 | only 2/4 |
| **B internal+export → A external** | **13.5** | **24.2** | **10.1** | **11.4** | **all 4, phase repeats 1.5°** |
| A reimport+export → B external | −0.6 | 23.4 | 1.9 | −1.7 | only 1/4 |
| B reimport+export → A external | 15.0 | 24.2 | −0.7 | 11.6 | only 3/4 |

Two things fall out.

**The A→B jumpers do not pass LO; B→A does.** Both directions are cabled,
so that pair is either faulty, unseated, or joined out-to-out instead of
out-to-in. LO export must reach LO *input*: `J3 → J4` for LO1, `J1 → J2`
for LO2.

**So the working configuration is Rx B as exporter:**

```
ch0  A:0   external
ch1  A:1   external
ch2  B:0   internal   export = True
ch3  B:1   companion
```

The contrast between 179.4° (independent synthesisers) and 1.5° (shared)
is itself the proof that sharing is real.

### Why `reimport` fails here

`reimport` makes the exporting channel take its own LO back in through its
LO IN port, so it needs a splitter: LO OUT → splitter → one leg to its own
LO IN, the other to the far board. With plain crisscross wiring the
exporter's LO IN is fed by the *other* board, which is not generating, so
the exporter gets nothing.

The failure pattern confirms the fault independently. With B on reimport,
ch2 dies (its LO IN is fed from A, the broken direction) while ch3 keeps
working, because `companion` taps ch2's synthesiser directly rather than
going through any cable.

`reimport` is only worth using once the A→B pair is repaired and you add a
splitter, to equalise cable delay between the boards.

---

## 7. Where the LO config lives in the GRC file

The UHD Source block has `Show LO Controls` deliberately set to **False**, even
though GNU Radio 3.8 does expose per-channel `LO Source` and `LO Export`
dropdowns. Two reasons:

1. **Order.** The generated code is
   `set_center_freq(...)` … then … `set_lo_source(...)`. That tunes before the
   LO routing exists. It has to be the other way round.
2. **Missing values.** The dropdown only offers `internal / external /
   companion` — no `reimport`, no `disabled`.

So all LO work happens in the **Python Snippet** blocks:

| Block | Section | Does |
|---|---|---|
| `snippet_lo_config` | Main — After Init | clears exports, sets sources, enables the one export, resets device time, defines `twinrx_tune()`, does the first coherent tune |
| `snippet_lo_watch` | Main — After Start | background thread that re-runs `twinrx_tune()` when the slider moves |
| `snippet_lo_stop` | Main — After Stop | stops the thread |

"After Init" runs after the blocks are constructed and **before** `tb.start()`,
which is exactly the window you need.

Channel alignment itself is free: with 4 channels in one streamer, gr-uhd sets
`_stream_now = false` and issues a single timed `STREAM_MODE_START_CONTINUOUS`,
so all four DDCs start on the same tick.

To change the configuration, edit these two variables in the flowgraph:

- `lo_sources` — `['internal', 'companion', 'external', 'external']`
- `lo_export_chan` — `0` (DB-A exports) or `2` (DB-B exports)

---

## 8. Next step: direction finding

`gr-aoa` is already installed in this GNU Radio (`Correlate`,
`MUSIC Lin Array`, `rootMUSIC Linear Array`, `Calc Phase Diff`,
`Shift Phase`). Once the phase offsets in section 5.4 are stable, the DF
flowgraph is this same front end with the four channels going into
`Stream to Vector` → `Correlate` → `MUSIC Lin Array`, and the measured offsets
loaded as the array calibration.

Get the phase stable first. A MUSIC spectrum computed on channels that are not
phase-coherent produces confident, meaningless bearings.

---

## Sources

- [Direction Finding with the USRP X-Series and TwinRX — Ettus KB](https://kb.ettus.com/Direction_Finding_with_the_USRP%E2%84%A2_X-Series_and_TwinRX%E2%84%A2)
- [TwinRX Daughterboard — UHD 3.15 manual](https://files.ettus.com/manual_archive/v3.15.0.0/html/page_twinrx.html)
- [TwinRX hardware installation guide (LO cabling)](https://kb.ettus.com/images/c/cc/twinrx_hardware_installation_guide.pdf)
- [Modifying an X310 Chassis for External LO Sharing — Ettus KB](https://kb.ettus.com/Modifying_an_X310_Chassis_for_External_LO_Sharing)
- [`twinrx_experts.cpp`, UHD 3.15](https://github.com/EttusResearch/uhd/blob/v3.15.0.0/host/lib/usrp/dboard/twinrx/twinrx_experts.cpp) — LO source strings and validation rules
- [`twinrx_ctrl.cpp`, UHD 3.15](https://github.com/EttusResearch/uhd/blob/v3.15.0.0/host/lib/usrp/dboard/twinrx/twinrx_ctrl.cpp) — the actual switch settings per LO source
- [`twinrx_freq_hopping.cpp` example](https://github.com/EttusResearch/uhd/blob/v3.15.0.0/host/examples/twinrx_freq_hopping.cpp) — LO swapping and timed commands
- [USRP-users: power decrease and phase coherence on the USRP 2945](https://www.mail-archive.com/usrp-users@lists.ettus.com/msg11525.html)
- [uhd#237](https://github.com/EttusResearch/uhd/issues/237), [uhd#670](https://github.com/EttusResearch/uhd/issues/670), [uhd#769](https://github.com/EttusResearch/uhd/issues/769) — the 90° ambiguity
- [Can I Share LO Between Multiple USRP-29X5? — NI](https://knowledge.ni.com/KnowledgeArticleDetails?id=kA00Z0000004AnBSAU)
