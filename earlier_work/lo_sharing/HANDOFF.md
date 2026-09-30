# HANDOFF — USRP-2945 coherent receiver (radar2)

Written 2026-09-21. Everything below that says **measured** was measured on this
physical hardware during that session; anything else is marked as unverified.

---

## 1. Read this first — the two traps that cost the most time

### Trap 1: there are two GNU Radio installs, and only one is correct

| | version | use for |
|---|---|---|
| `~/gnuradio-3.8` | GR 3.8.5 + **UHD 3.15** | **everything on the X310 / TwinRX** |
| system (`/usr/bin`) | GR 3.10 + UHD 4.x | other projects only |

The TwinRX needs UHD 3.15. Always:

```bash
source ~/gnuradio-3.8/setup_env.sh          # before any X310 work
~/gnuradio-3.8/run_grc.sh <file>.grc        # to open a flowgraph
grc38 <file>.grc                            # same thing, alias in ~/.bashrc
```

**Opening a `.grc` in the system GRC 3.10 makes every taps block turn red.**
That is not a file error — GR 3.10 removed `firdes.WIN_HAMMING`, which these
flowgraphs use. The file is fine; the tool is wrong.

**Saving from GRC 3.10 corrupts the file for 3.8.** This already destroyed
`bhagya.grc` and `shank.grc`, and twice silently reverted committed work
(see commits `544e619`, `2abd5e7`). Check the block paths printed at startup:

- `/home/shankar/gnuradio-3.8/share/gnuradio/grc/blocks` → correct
- `/usr/share/...` or `/usr/local/share/...` → wrong, close without saving

An open GRC window is a *writer*. If a file is edited outside GRC while a
window holds it, whichever saves last wins, with no warning.

### Trap 2: the B210 uses the SYSTEM UHD, not the 3.8 one

The b2xx firmware images live under the system install. Run the transmitter in
a terminal where you have **not** sourced `setup_env.sh`.

---

## 2. Hardware

```
USRP-2945  = X310 (serial 31082D8) + 2x TwinRX 80 MHz
             addr 192.168.10.2, host NIC enp3s0 at 192.168.10.1/24
             master clock fixed at 200 MHz (TwinRX requirement)

B210       = serial 3273AC6, USB 2.0, calibration tone source

RF chain   B210 TX -> 30 dB pad -> splitter -> TwinRX RX ports
```

Channel map is fixed by `subdev_spec = "A:0 A:1 B:0 B:1"`:

```
ch0 = RF A / RX1        ch2 = RF B / RX1
ch1 = RF A / RX2        ch3 = RF B / RX2
```

### MMCX LO connectors (per TwinRX board)

| connector | signal | direction | level |
|---|---|---|---|
| J3 | LO1 export | **OUT** | 5 dBm |
| J4 | LO1 input | **IN** | −5 dBm, **10 dBm damage** |
| J1 | LO2 export | **OUT** | 3 dBm |
| J2 | LO2 input | **IN** | 2 dBm, 20 dBm damage |

Odd = output, even = input. **Never wire output to output** — J4 tolerates only
10 dBm and J3 emits 5 dBm. Cables run crisscross in both directions so either
board can be the exporter without re-cabling.

TwinRX is dual-conversion (RF → LO1 → IF → LO2 → baseband), so sharing an LO
means sharing **both** LO1 and LO2 — two cables per direction.

---

## 3. LO configuration

Current, and the only direction that works on this unit:

```python
lo_sources     = ['external', 'external', 'internal', 'companion']
lo_export_chan = 2
```

| channel | source | meaning |
|---|---|---|
| ch2 | `internal` + export | the single master synthesiser |
| ch3 | `companion` | ch2's LO over an on-board PCB trace |
| ch0 | `external` | LO arrives via the MMCX jumpers |
| ch1 | `external` | LO arrives via the MMCX jumpers |

**Measured: the A→B jumpers on this unit pass no LO.** Setting ch0 as exporter
kills ch2/ch3 (tone +1.2 / −1.1 dB). B→A works. Tested twice, hours apart.

Valid sources: `internal`, `companion`, `external`, `reimport`, `disabled`.
Driver rules: a channel on `external` may not export; only one channel per
board may export. `reimport` exists but is unused here.

### How to check what the hardware actually accepted

The flowgraph prints a readback at startup — trust this over the file:

```
ch0  source=external   export=False
ch1  source=external   export=False
ch2  source=internal   export=True
ch3  source=companion  export=False
```

Or from Python: `get_lo_source(uhd.ALL_LOS, ch)` and
`get_lo_export_enabled(uhd.ALL_LOS, ch)`.

---

## 4. Measured results

### Phase coherence — PASS

ch1 vs ch0 across three full retunes, shared LO:

```
-59.19°   -59.12°   -59.09°      spread 0.11°, residual 0.18°
```

Independent synthesisers would scatter by tens or hundreds of degrees, because
each powers up in a random phase. 0.11° is only possible from one shared
oscillator. The −59.13° offset itself is fixed cable/trace delay.

**A single scope snapshot cannot show coherence.** Coherent and non-coherent
both look like two clean sines with an offset. The difference only appears
across retunes, or as slow sliding over time.

### Amplitude imbalance — RF A board is faulty

Same cables, same splitter, same transmitter, moved between boards:

| ports | imbalance |
|---|---|
| RF B (ch2 / ch3) | **0.6 dB** — normal |
| RF A (ch0 / ch1) | **15.4 dB** — faulty |

A healthy 2-way splitter gives under 1 dB. This rules out cables and splitter:
**the fault is on the RF A daughterboard**, with RF A/RX1 (ch0) the weak port.
RF A is still usable for phase work — it measured the *best* coherence — but
not for anything needing matched amplitude.

### The tone does not arrive where it is transmitted

B210 transmits at 2400.200 MHz; the X310 receives it at **~2400.2039 MHz**.
The two radios have independent clock references (~1.6 ppm at 2.4 GHz). The
offset is roughly fixed in Hz, set by the carrier, not the tone offset.

**This caused a real failure.** A 4 kHz-wide band-pass centred on 200 kHz
rejected the tone entirely, and the display showed pure noise at exactly
52.0% ripple — the Rayleigh signature. `disp_bw` is 20 kHz for this reason;
do not narrow it.

### DC / LO leakage

A spike always appears at exactly the tuned centre frequency. It is the
receiver's own LO self-mixing, not WiFi — it tracks the tuning, an external
signal would not.

| stage | ch2 DC level |
|---|---|
| nothing | +58.8 dB |
| hardware `set_auto_dc_offset` | +58.4 dB (barely helps) |
| **+ DC Blocker block** | **−34.1 dB** |

The block does the work; the hardware call is a cheap extra. The 200 kHz tone
offset exists so the tone never sits under this spike.

### AGC was removed — it made things worse

| | with AGC | without |
|---|---|---|
| ch2 ripple | 1.0% | **0.65%** |
| ch3 ripple | 0.9% | **0.54%** |

An AGC sets level, not shape — it cannot reduce ripple, and reacting to the
instantaneous envelope added its own. A fixed `disp_gain = 25` replaced it,
which also preserves true relative amplitude between channels.

### TX amplitude 0.8 — measured, not guessed

| amplitude | ch2 tone/floor | ch2 worst spur | headroom |
|---|---|---|---|
| 0.5 | +43.5 dB | −29.3 dBc | 6 dB |
| **0.8** | **+47.1 dB** | **−34.7 dBc** | ~2 dB |
| 1.0 | +50.1 dB | −36.3 dBc | 0 dB |

Spurs *improve* as amplitude rises — the worst one sits at a fixed +5.9 kHz
offset, not at the IQ image or a harmonic, so a louder tone buries it. The
old help text claiming full scale raises spurs is wrong on this hardware.
Digital headroom, not spurs, sets the ceiling.

`--amplitude` is a fraction of DAC full scale, **not volts**. At 0.8 the real
levels are 9.2 mV rms at the B210 SMA and 145 µV rms at each RX port — 74 dB
below the TwinRX +10 dBm damage threshold. True 1 V rms (+13 dBm) exceeds what
a B210 can produce.

---

## 5. How to run

**Terminal 1 — transmitter.** Do *not* source the 3.8 environment here:

```bash
python3 ~/radar2/b210_tone_source.py --freq 2.4e9 --gain 55 --pad 30
```

Wait for `transmitting ...`. If it fails with
`load_fpga: cannot write bitstream to FX3 (LIBUSB_ERROR_CODE -1)`, just run it
again — the second attempt usually works. If not, replug the USB cable. The
B210 re-enumerates often on USB 2.0; a USB 3.0 port would be more reliable.

**Terminal 2 — receiver:**

```bash
cd ~/radar2/guru && ./run_guru.sh
```

`guru.py` auto-starts its own B210 if none is running and kills that one on
exit, with output to `/dev/null`. Starting it yourself keeps underruns visible.

**Command-line checks:**

```bash
source ~/gnuradio-3.8/setup_env.sh
python3 ~/radar2/twinrx_lo_check.py --freq 2.4e9 --trials 3          # coherence
python3 ~/radar2/twinrx_lo_check.py --freq 2.4e9 --port-scan --no-save  # which ports are fed
python3 ~/radar2/twinrx_band_check.py --freqs 2.4e9 --monitor --settle 11  # live connector mapping
```

`--monitor` is the authoritative way to map physical connectors to channels:
unplug one cable, see which column collapses.

---

## 6. Flowgraph structure

Per channel, all four identical:

```
source -> DC Blocker(1024) -> band-pass(disp_taps_bp) -> rational resampler -> Complex to Real -> time sink
                                    `-> |x|^2 -> moving avg -> 10log10 -> decimate -> level meter (dB)
source -> QT GUI Frequency Sink (raw, ahead of DC blocker, so leakage is visible)
```

Key variables:

```
lo_sources     = ['external','external','internal','companion']
lo_export_chan = 2
disp_bw        = 20e3     # MUST cover the ~4 kHz clock offset
disp_gain      = 25       # fixed display gain, replaced the AGC
tx_disp_gain   = 10       # TX reference trace only, not radiated power
tone_offset    = 200e3
samp_rate      = 1e6      # X310 decimates 200 MHz / 200
```

Time sink: autoscale **off**, y = −0.6…0.6. Autoscale must stay off — it
latches onto startup transients and flattens real signals to an invisible line.

Frequency sink: `fc = center_freq` (real RF axis, follows the slider),
4096-pt FFT.

The resampler interpolates 1 → 20 Msps purely for display smoothness
(98 samples/cycle instead of 4.9). Its taps also carry the display gain —
remove the resampler and amplitude drops 500×, and the time axis reads 20×
wrong because the sink is configured for `time_srate`.

**No phase alignment is applied.** The old hardcoded rotations were removed
(`071a1a2`): they were stale versus `twinrx_lo_cal.json`, only valid at
2.4 GHz, and the LO divider comes up in a random quadrant on every power
cycle, so any frozen correction goes wrong. The scope shows true phase.

---

## 7. Repository

```
guru/       guru.grc, guru.py, run_guru.sh + support files   <- main bundle
guru2/      identical copy, guru2.* naming                   <- backup
*.py        twinrx_lo_check.py, twinrx_band_check.py, b210_tone_source.py
*.md        RUNBOOK.md, TWINRX_LO_NOTES.md, BLOCK_DIAGRAM.md, SESSION_LOG.md
```

`TWINRX_LO_NOTES.md` is the deepest reference — LO theory, connector tables,
the switch diagram, failure modes.

Recovery point:

```bash
git checkout known-good-2026-09-21 -- guru.grc guru.py guru/ guru2/
```

Root-level `guru.grc`/`guru.py` are kept byte-identical to the `guru/` copies.
Three copies of `b210_tone_source.py` exist (root, guru/, guru2/) and have
drifted before — `run_guru.sh` spawns the **root** one by absolute path.

---

## 8. Open items

1. **RF A/RX1 is ~15 dB down.** Reseat the connector; if it persists it is a
   board-level fault. RF B is the good pair.
2. **The TwinRX USRP Source block** (gr-doa) is now used in `guru.grc`. Its
   `doa/__init__.py` does `from gnuradio.doa import *`, which does not exist
   under 3.8, so the block YAML at
   `~/.local/share/gnuradio/grc/blocks/twinrx_usrp_source.block.yml` was
   patched to import the pure-Python module directly. Original at `*.bak`.
   The block hard-codes the Rx B routing and does a **single** timed tune —
   it lacks the double-tune that beats the 16-deep X310 command FIFO.
3. **A dead `RX Gain` slider** may still be on the canvas, left over from the
   old UHD source. Real gain comes from the `gainn` slider.
4. `twinrx_lo_cal.json` is **not read by anything** any more.
5. Untracked and unreviewed: `bhagya.grc`, `shank.grc` (both 3.10-corrupted,
   safe to delete), `grc_doa_flowgraphs/` (a copy of `~/gr-doa/apps`),
   `run_all.sh`, several demo `.grc` files.

---

## 9. Things that were concluded and later proved wrong

Kept deliberately, so they are not re-derived:

- **"ch0 is a dead port."** Wrong. It read ~1 dB for hours and survived an
  own-LO test and a cable swap, but with different cabling it reads 29 dB and
  tracks a 10 dB TX step by −11 dB. The fault was the feed, not the port.
- **"Full-scale TX raises spurs."** Wrong on this hardware — measured, spurs
  improve with amplitude.
- **"The gr-doa block hard-codes Rx A master."** Wrong for the installed copy,
  which has been customised for this unit and does Rx B, with A as fallback.
- **A flat, steady scope trace means a channel is receiving.** No. Crosstalk
  is coherent and looks perfectly stable. Gate on tone presence, and confirm
  with a 10 dB TX gain step: real signal moves, crosstalk does not.
