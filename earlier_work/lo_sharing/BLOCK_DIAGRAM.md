# Block diagram and expected output

Every stage of the USRP-2945 four-channel coherence setup, with the value you
should see at each point. Numbers are from measurements on this rig at
2.4 GHz, TX gain 55 dB, 30 dB pad, RX gain 30 dB.

Commands in `RUNBOOK.md`. Background in `TWINRX_LO_NOTES.md`.

---

## Commands

**Terminal 1 — source.** No env sourcing; the B210 uses the system UHD.

```bash
python3 ~/radar2/b210_tone_source.py --freq 2.4e9 --gain 55 --pad 30
```

**Terminal 2 — pick one** (both need the X310, so not together):

```bash
source ~/gnuradio-3.8/setup_env.sh && python3 ~/radar2/twinrx_lo_check.py --freq 2.4e9 --trials 3
```

```bash
~/gnuradio-3.8/run_grc.sh ~/radar2/twinrx_lo_coherence.grc
```

---

## 1. RF signal chain

```
 ┌───────────────────────┐
 │      USRP B210        │   TX LO      2400.000 MHz
 │  b210_tone_source.py  │   baseband   +200 kHz CW, amplitude 0.5
 │   (SYSTEM UHD 4.x)    │   TX gain    55 dB
 └───────────┬───────────┘
             │              EXPECT: carrier at 2400.200 MHz, ~ -30.8 dBm
             ▼
      ┌──────────────┐
      │  30 dB pad   │      SAFETY INTERLOCK — not optional
      │  (fixed SMA) │      TwinRX damage +10 dBm, full scale -20 dBm
      └──────┬───────┘      EXPECT: ~ -60.8 dBm
             │              worst case at max TX gain: -27 dBm (still safe)
             ▼
   ┌─────────────────────┐
   │   power splitter    │  -6 dB split, ~-1 dB insertion
   │       4-way         │  EXPECT: ~ -67.8 dBm per port
   └──┬──────┬──────┬──┬──┘
      │      │      │  │     Noise floor in 1 MHz at NF 5.5 dB = -108.5 dBm
      │      │      │  │     EXPECT SNR: ~40 dB
      ▼      ▼      ▼  ▼
   RF A/  RF A/  RF B/  RF B/
    RX1    RX2    RX1    RX2
    ch0    ch1    ch2    ch3
```

**Expected at this stage** — run `twinrx_band_check.py --freqs 2.4e9`:

```
     frequency        ch0      ch1      ch2      ch3
    2400.000 MHz     13.5*    24.2*    10.1*    11.4*
   * = tone received (>= 6 dB)
```

All four above 6 dB. A channel near 0 dB is not receiving. The ~10 dB spread
is real: Rx A's feed passes one splitter, Rx B's passes two.

---

## 2. LO sharing inside the 2945

One synthesiser must drive all four channels. On this unit the A→B jumpers
pass no LO, so **Rx B is the exporter**.

```
   ┌──────────────── USRP-2945 (X310 31082D8) ────────────────┐
   │                                                          │
   │   Rx A  TwinRX 3104B3C          Rx B  TwinRX 31050CD     │
   │  ┌────────────────────┐        ┌────────────────────┐    │
   │  │ ch0  external ◄──┐ │        │ ch2  internal ◄─┐  │    │
   │  │                  │ │        │       + EXPORT  │  │    │
   │  │ ch1  external ◄──┤ │        │                 ├─SYNTH │
   │  │                  │ │        │ ch3  companion ◄┘  │    │
   │  │      LO IN ◄─────┘ │        │      LO OUT        │    │
   │  └──────────▲─────────┘        └─────────┬──────────┘    │
   │             │                            │               │
   │             │   J4 ◄──── LO1 ──── J3     │               │
   │             └───┤   J2 ◄──── LO2 ──── J1 ├───────────────┘
   │                        (MMCX jumpers)                     │
   └───────────────────────────────────────────────────────────┘

   LO plan at 2400 MHz RF:   LO1 = 3650 MHz     LO2 = 1400 MHz
   ONE synthesiser tuned in the whole chassis — that is the sanity check.
```

**Expected** — from `twinrx_lo_check.py`, STEP 2:

```
  ch0  want=external   got=external   export=False
  ch1  want=external   got=external   export=False
  ch2  want=internal   got=internal   export=True
  ch3  want=companion  got=companion  export=False
```

**Readback only proves UHD threw the switches.** It says nothing about whether
LO signal physically arrives. `lo_locked` also reads True on channels with no
LO at all. The only proof is that the channel downconverts — section 4.

---

## 3. Tuning

```
   set_command_time(now + 0.1 s)
        set_rx_freq(ch0)  set_rx_freq(ch1)
        set_rx_freq(ch2)  set_rx_freq(ch3)
   clear_command_time()
        │
        └──► repeat the identical burst a SECOND time
             (a cold TwinRX tune overflows the X310's 16-deep
              command FIFO; the driver caches state, so the
              second pass fits and lands atomically)
```

**Expected:** `tuned -> 2400.000000 MHz   (ch0 actual 2400.000000 MHz)`

---

## 4. DSP chain — what the flowgraph does

Per channel, then cross-correlated against ch0:

```
  UHD Source
  4 ch, 1 Msps          ┌─────────────────────────────────────────┐
  fc 2400 MHz           │ raw ch0..ch3                            │
  DDC pinned to 0 Hz    └────┬──────────────────────────────┬─────┘
                             │                              │
              ┌──────────────▼──────────────┐    ┌──────────▼──────────┐
              │ freq_xlating_fir_filter_ccc │    │  QT Frequency Sink  │
              │ centre = tone_offset 200kHz │    │  EXPECT: spike at   │
              │ low-pass  tone_bw   10 kHz  │    │  +204 kHz, 40 dB    │
              └──────────────┬──────────────┘    │  over floor; DC     │
                             │                   │  spike = LO leakage │
          ┌──────────────────┼──────────┐        └─────────────────────┘
          │                  │          │
          ▼                  ▼          ▼
   ┌─────────────┐   ┌──────────────┐  ┌──────────────────┐
   │ mag squared │   │ multiply_    │  │ 2nd xlating FIR  │
   │  -> average │   │ conjugate    │  │ at +253 kHz      │
   │  -> 10log10 │   │ chN * conj   │  │ (off-tone ref)   │
   │             │   │      (ch0)   │  │ -> mag -> dB     │
   └──────┬──────┘   └──────┬───────┘  └────────┬─────────┘
          │                 │                   │
          │                 ▼                   │
          │       ┌──────────────────┐          │
          │       │ moving_average   │          │
          │       │ avg_len = 65536  │          │
          │       │ (65 ms)          │          │
          │       └────────┬─────────┘          │
          │                ▼                    │
          │       ┌──────────────────┐          │
          │       │ complex_to_arg   │          │
          │       │ x 57.2958 -> deg │          │
          │       └────────┬─────────┘          │
          │                │                    │
          ▼                ▼                    ▼
   ┌────────────┐  ┌──────────────┐   ┌────────────────────┐
   │ Band power │  │ Phase plot + │   │ tone dB - ref dB   │
   │  (panel 5) │  │ steady-state │   │ IS THIS CHANNEL    │
   │            │  │  (panels 3,4)│   │ RECEIVING? panel 2 │
   └────────────┘  └──────────────┘   └────────────────────┘
```

Why the band-pass matters: it shifts the tone to DC and rejects the **real**
DC term, which carries LO self-mixing leakage. Without it, with leakage
comparable to the tone, a true 30° offset reads as 90°.

---

## 5. GUI panels, top to bottom — and what each should show

```
 ┌──────────────────────────────────────────────────────────────────┐
 │ 1  Center Freq / RX Gain sliders                                 │
 │    Moving frequency triggers a full timed double-tune            │
 ├──────────────────────────────────────────────────────────────────┤
 │ 2  IS THIS CHANNEL RECEIVING?   <-- READ THIS FIRST              │
 │    EXPECT  ch0 ~13   ch1 ~24   ch2 ~10   ch3 ~11  dB             │
 │    >6 dB = yes.  ~0 dB = NO, whatever panel 3 looks like         │
 ├──────────────────────────────────────────────────────────────────┤
 │ 3  Relative phase vs ch0 (degrees)                               │
 │    EXPECT  three FLAT lines at fixed offsets                     │
 │    ramping = independent synths;  hashing = no signal            │
 ├──────────────────────────────────────────────────────────────────┤
 │ 4  Steady-state phase offset                                     │
 │    EXPECT  three stable numbers — YOUR CALIBRATION CONSTANTS     │
 │    they differ from each other; that is correct                  │
 ├──────────────────────────────────────────────────────────────────┤
 │ 5  Band power (dB)                                               │
 │    Mostly NOISE unless panel 2 is high. NOT proof of signal      │
 ├──────────────────────────────────────────────────────────────────┤
 │    Spectra tab: 4 overlaid spectra, tone at +204 kHz             │
 └──────────────────────────────────────────────────────────────────┘
```

**Read panel 2 before panel 3.** A flat trace with a ~0 dB receiving meter is
internal crosstalk, not success — that produced three false passes here.

---

## 6. Expected final verdict

```
      2400.000 MHz
          ch0  mean    -0.00   raw spread   0.00   resid   0.64   <-- reference
          ch1  mean   -64.06   raw spread   1.27   resid   0.63
          ch2  mean   +11.27   raw spread   1.37   resid   0.75
          ch3  mean  -150.30   raw spread   2.00   resid   1.36

      PASS  channels hold 1.36 deg against each other. LO is shared.
```

| reading | meaning |
|---|---|
| `resid` under ~2° on all channels | **working** — LO shared |
| `resid` ~179° | each board on its own LO, not shared |
| `MEASUREMENT INVALID` | a channel has no tone; fix that before reading anything else |
| `NOT A VALID RESULT` | same, with the LO-versus-RF test printed |

The control that proves sharing is real:

```
  own LO each board                 phase repeats 179.4 deg   <- not coherent
  B internal+export -> A external   phase repeats   1.5 deg   <- coherent
```

---

## 7. Failure signatures

| symptom | cause |
|---|---|
| all four ~0 dB on panel 2 | transmitter not running |
| two channels of one board ~0 dB, at every frequency, both connectors, no response to RX gain | **LO jumpers**, not RF. Test with `--lo-sources internal,companion,internal,companion` |
| one channel ~0 dB, others fine | that RF cable or connector |
| receiving but phase hashing | signal too weak — raise TX gain in 10 dB steps |
| phase flat but panel 2 ~0 dB | crosstalk. Not working |
| offsets moved since last session | expected — gain, band and cable handling all shift them |
