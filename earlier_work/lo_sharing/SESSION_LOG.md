# USRP-2945 LO sharing — session log

**18–19 September 2026.** What was asked for, what was built, what went wrong,
and what the hardware is actually doing now.

`TWINRX_LO_NOTES.md` is the technical reference. This file is the record of how
we got there, including the wrong turns, because several of them were expensive
and are easy to repeat.

---

## The ask

Starting point: the Ettus knowledge-base article *Direction Finding with the
USRP X-Series and TwinRX*, applied to a **USRP-2945** (X310 + 2× TwinRX Rev B,
4 RX channels), on **GNU Radio 3.8.5 + UHD 3.15.0**. The goal was LO
configuration for phase-coherent operation, a GRC flowgraph to test it, and an
explanation of the mechanism.

The KB article itself could not be read — kb.ettus.com sits behind a bot check
that blocked every attempt. Everything below is grounded instead in the UHD
3.15 driver source (`twinrx_experts.cpp`, `twinrx_ctrl.cpp`), the 3.15 manual,
the `twinrx_freq_hopping.cpp` example, and measurements on the hardware.

---

## What exists now

| File | Purpose |
|---|---|
| `twinrx_lo_check.py` | CLI verifier: LO routing, coherent tuning, phase measurement, per-channel tone presence, cross-session calibration diff |
| `b210_tone_source.py` | CW calibration source on a B210, with a gain ceiling and a level budget against the TwinRX damage limit |
| `twinrx_band_check.py` | Drives both radios together across frequency; `--monitor` gives a live per-channel display |
| `twinrx_lo_coherence.grc` / `.py` | GRC flowgraph: LO config in Python Snippets, live phase and reception display |
| `twinrx_lo_cal.json` | Measured phase offsets, tagged by method and RX gain |
| `TWINRX_LO_NOTES.md` | Technical reference |

Twelve commits, `2d804e5` … `c6ccb5d`.

---

## Findings that matter

### LO routing

The five source strings UHD accepts are `internal`, `companion`, `external`,
`reimport`, `disabled`. Two rules the driver enforces: a channel on `external`
may not export, and only one channel per board may export.

On the slave board **both** channels take `external` — its LO IN is split
internally. Setting the second one to `companion` makes UHD program a second
synthesiser, which silently defeats the whole point.

### Tuning must be timed, and issued twice

A TwinRX tune is a long SPI burst that overflows the X310's 16-deep command
FIFO on a cold tune, so part of it executes untimed. The driver caches state
along the way, so an immediately repeated identical burst fits and lands
atomically on all channels.

### The validated configuration on this unit

```
ch0  A:0   external
ch1  A:1   external
ch2  B:0   internal   export = True
ch3  B:1   companion
```

Note **Rx B** is the exporter, not Rx A. Measured with a real CW source:

| configuration | ch0 | ch1 | ch2 | ch3 | result |
|---|---|---|---|---|---|
| own LO each board | 13.5 | 23.4 | 11.6 | 12.6 | all receive, phase repeats **179.4°** |
| A internal+export → B external | 15.6 | 23.9 | 1.4 | 0.4 | only 2/4 |
| **B internal+export → A external** | **13.5** | **24.2** | **10.1** | **11.4** | **all 4, phase repeats 1.5°** |
| A reimport+export → B external | −0.6 | 23.4 | 1.9 | −1.7 | only 1/4 |
| B reimport+export → A external | 15.0 | 24.2 | −0.7 | 11.6 | only 3/4 |

179.4° against 1.5° is the proof that sharing is real.

### Health at the end

```
  mboard        : X310   serial 31082D8      master clock 200.000000 MHz
  ch0/ch1       : TwinRX Rev B  dbserial 3104B3C   (Rx A)
  ch2/ch3       : TwinRX Rev B  dbserial 31050CD   (Rx B)
  ref_locked    : True
  stream errors : 0
```

`lo_locked` reads **True on channels that demonstrably have no LO**, because it
reports on the synthesiser and an `external` channel has none. It is not
evidence of sharing.

---

## The wrong turns

Worth reading before trusting any measurement on this rig.

### Three false PASS results

The tool reported **PASS at 0.57°, 2.07° and 0.37°** on channels that were
receiving nothing at all. A channel with no antenna signal still correlates
against the reference through **internal crosstalk**, which is coherent and
therefore perfectly steady.

**Phase stability alone does not mean a channel works.** The verdict is now
gated on measured tone presence, not stability.

### The phase estimator was broken

An FFT cross-spectrum accumulator disagreed with itself by tens to hundreds of
degrees between back-to-back captures of an unchanged signal, while a plain
mix-to-DC average of the same data held to under a degree:

```
   cap    FFT: ch1    ch2     ch3   |  mix: ch1   ch2     ch3
    0        +71.2  +93.7   -75.7   |      +7.2  -2.6  +117.6
    3        +81.3 -169.1  -155.2   |      +6.1  -3.2  +116.8
```

Conclusions drawn before this was found are withdrawn — in particular the claim
that the slave board's two channels re-roll their LO quadrant together, and the
claim that the quadrant re-rolls on every tune. Neither survived a real signal.

### Four attempts at "is this channel receiving?"

Recorded in the code so they are not repeated:

1. **Peak-pick each channel's own 8192-bin FFT** — far less sensitive than the
   real measurement; reported NO SIGNAL on channels tracking phase to 2°.
2. **Mix to the tone and average the whole capture** — a few Hz of residual
   frequency error rotates a 100 ms mean to zero, so a 41 dB tone read as
   nothing. The phase measurement escapes this only because its cross-product
   against ch0 cancels the common error.
3. **Coherent block power over total power** — LO self-mixing leakage at DC
   inflates the total, so a weak tone on big leakage reads *below* the noise
   floor.
4. **Coherent power at the tone over an off-tone reference** — immune to both,
   gives +26 dB where (3) gave −35 dB, and ~0 dB on a genuinely empty channel.
   This is what ships.

The port scan had a further flaw: it put all four channels on one connector,
which on TwinRX engages an internal resistive divider between the two channels
of a board. That measures the divider, not the cabling. It now compares native
against swapped, both divider-free.

### Diagnosing the RF path when the fault was the LO

The symptom was ch2/ch3 dead at every frequency from 100 MHz to 2.4 GHz, on
both antenna connectors, with a noise floor that would not respond to RX gain.
That was read as broken RF cabling, and led to two rounds of reseating
connectors and a full hardware rebuild — of a path that was never at fault.

A channel on `external` has **no LO of its own**. If the LO jumpers are not
delivering, its mixers produce nothing whatever RF arrives, which looks exactly
like a dead RF path. The one-command discriminator:

```bash
python3 twinrx_lo_check.py --freq 2.4e9 \
    --lo-sources internal,companion,internal,companion
```

Receiving that way means the RF is fine and the LO cabling is the fault. The
tool now prints this advice itself before suggesting anything about RF cables.

### A GUI label that misled directly

The flowgraph showed *"Tone power per channel (dB) — all four should be close"*,
fed from band-pass output power. On a dead channel that is almost entirely
noise, but it still displays a number only ~8 dB below a live channel:

```
    ch0  -73.8 dBFS  tone +24.3 dB   receiving
    ch2  -76.6 dBFS  tone  -0.1 dB   NOT receiving
```

Read as reception. It is now retitled to say it is mostly noise, and the
trustworthy meter — **"IS THIS CHANNEL RECEIVING? above 6 dB = YES"** — was
moved from below the fold to directly under the controls.

### The cal file was destroyed once

`save_cal` opened the real file with `"w"`, truncating the previous calibration
before writing a byte. A Ctrl-C partway through `json.dump` left 214 bytes of
corrupt JSON and lost the old data. It now serialises fully, writes a sibling
`.tmp`, fsyncs and renames.

---

## Calibration is never permanent

Phase offsets on this rig depend on:

- **RX gain** — switched attenuators, each state with its own phase
- **frequency band** — TwinRX has 8; offsets do not interpolate across an edge
- **cable handling** — reseating anything changes them

So they must be re-measured at the start of a session and after touching
hardware. `twinrx_lo_check.py` stores each entry with its method and gain, and
refuses to diff against one that is not comparable.

---

## Standing orders

- **The 2945 must run under UHD 3.15 / GNU Radio 3.8** (`source
  ~/gnuradio-3.8/setup_env.sh`). Its FPGA is compat 36; the system UHD 4.x will
  demand a reflash. **Do not reflash** — it would break the working setup.
- **The B210 is version-agnostic** and runs under the *system* UHD, which is
  where the b2xx firmware images live. Two terminals, two environments.
- **Keep the 30 dB pad** on the B210 TX. TwinRX damage is +10 dBm and its ADC
  hits full scale at −20 dBm; without the pad, full TX gain puts +3 dBm on every
  port.

---

## Outstanding

1. **The A→B LO jumpers pass no LO.** B→A works, so this is not blocking, but
   fix it for redundancy and as a prerequisite for `reimport`. LO export must
   reach LO *input*: `J3 → J4` for LO1, `J1 → J2` for LO2.
2. **`reimport` needs a splitter**, not plain crisscross wiring. It makes the
   exporting channel take its LO back through its own LO IN, which on crisscross
   wiring is fed by the other board.
3. **Per-band calibration sweep** — drive the B210 and the 2945 together across
   bands to get constants for `gr-aoa`. `twinrx_band_check.py` already drives
   both radios; extending it to record phase per band is the remaining step.
4. **gr-aoa block definitions exist in three places**, with
   `~/.local/share/gnuradio/grc/blocks` winning. Worth resolving before
   building the MUSIC flowgraph.
5. **Channel level imbalance** — ch1 runs ~10 dB hotter than the others because
   Rx A's feed passes one splitter while Rx B's passes two. A single 4-way split
   would even this out.

---

## Verifying it is real

The measurements can be checked end to end by killing the transmitter mid-run:

```
  TX ON    tone bin  +204.1 kHz   ch0 14.5  ch1 23.7  ch2 12.1  ch3 12.3
  TX OFF   tone bin  +131.7 kHz   ch0  0.1  ch1  1.4  ch2  1.3  ch3  3.2
```

All four follow the transmitter, and with it off the detector falls back to a
random noise bin. Synthetic numpy signals were used in this work, but only to
validate estimator maths offline — every hardware number came from the USRPs.
