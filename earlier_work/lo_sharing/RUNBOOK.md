# Runbook — every command, in order

Copy-paste commands for the USRP-2945 four-channel coherent receiver.
Background in `TWINRX_LO_NOTES.md`; history in `SESSION_LOG.md`.

**Two environments.** The 2945 must run under UHD 3.15 / GNU Radio 3.8. The B210
runs under the *system* UHD, which is where the b2xx firmware images live. Use
two terminals and keep them straight.

**Only one process can hold the X310.** The flowgraph and `twinrx_lo_check.py`
cannot run at the same time. The B210 is a separate device and runs alongside
either.

---

## 0. Before powering on

- 30 dB attenuator on the B210 TX, then the splitter, then the four RX ports.
  The pad is a safety interlock: TwinRX damage is +10 dBm and its ADC hits full
  scale at −20 dBm. Without it, full TX gain puts +3 dBm on every port.
- All four splitter outputs connected. An unterminated output radiates.
- LO jumpers in place between the TwinRX modules, J1↔J2 and J3↔J4 crisscross.

---

## 1. Are both radios visible?

```bash
source ~/gnuradio-3.8/setup_env.sh && uhd_find_devices
```

```bash
lsusb | grep -i ettus
```

Expect the X310 (`serial 31082D8`) and `2500:0020 Ettus Research LLC USRP B210`.
No B210 on USB means a charge-only cable or a dead port.

---

## 2. Terminal 1 — start the calibration source

Leave this running. **Do not** source the 3.8 environment here.

```bash
python3 ~/radar2/b210_tone_source.py --freq 2.4e9 --gain 55 --pad 30
```

Wait for `transmitting ...`. Ctrl-C to stop.

First time at a new setup, start cold and ramp:

```bash
python3 ~/radar2/b210_tone_source.py --freq 2.4e9 --gain 0 --pad 30
```

Raise `--gain` in 10 dB steps until the tone sits 30–40 dB above the floor.
Usable range is roughly 40–60 dB; 60 is the built-in ceiling.

---

## 3. Terminal 2 — is every channel receiving?

```bash
source ~/gnuradio-3.8/setup_env.sh && python3 ~/radar2/twinrx_band_check.py --freqs 2.4e9 --settle 11
```

All four should read **above 6 dB**. Live version — unplug a cable and watch
which column collapses, which maps connectors to channels with no guesswork:

```bash
source ~/gnuradio-3.8/setup_env.sh && python3 ~/radar2/twinrx_band_check.py --freqs 2.4e9 --monitor --settle 11
```

```
   RF A/RX1 = ch0     RF A/RX2 = ch1
   RF B/RX1 = ch2     RF B/RX2 = ch3
```

---

## 4. The main check

```bash
source ~/gnuradio-3.8/setup_env.sh && python3 ~/radar2/twinrx_lo_check.py --freq 2.4e9 --trials 3
```

Defaults to the working routing: ch0/ch1 `external`, ch2 `internal` + export,
ch3 `companion` — **Rx B is the exporter**, because the A→B jumpers on this unit
pass no LO.

Want a **PASS** with every channel showing tone above 6 dB. A verdict of
`NOT A VALID RESULT` means some channel has no signal; it will not pass on
crosstalk.

Sweep several frequencies:

```bash
source ~/gnuradio-3.8/setup_env.sh && python3 ~/radar2/twinrx_lo_check.py --sweep 1e9,2e9,2.4e9,3e9 --trials 3
```

---

## 5. The GUI

```bash
~/gnuradio-3.8/run_grc.sh ~/radar2/twinrx_lo_coherence.grc
```

Press **Run** (F6). On the Control_Phase tab, top to bottom:

1. Center Freq / RX Gain sliders — moving the frequency triggers a full timed
   double-tune
2. **IS THIS CHANNEL RECEIVING?** — the meter to trust. >6 dB yes, ~0 dB no
3. Relative phase vs ch0
4. Steady-state phase offsets — your calibration constants
5. Band power — mostly noise unless meter 2 reads high. **Not** proof of signal

Read them in that order. A flat phase trace with a ~0 dB receiving meter is
crosstalk, not success.

---

## 6. Diagnostics when something is wrong

**Channels dead? Test the LO before touching RF cables.** Give each board its
own LO, so no jumper is needed:

```bash
source ~/gnuradio-3.8/setup_env.sh && python3 ~/radar2/twinrx_lo_check.py --freq 2.4e9 --no-save --lo-sources internal,companion,internal,companion
```

Receiving this way means the RF is fine and the LO cabling is at fault.

**Which antenna connector is fed?**

```bash
source ~/gnuradio-3.8/setup_env.sh && python3 ~/radar2/twinrx_lo_check.py --freq 2.4e9 --port-scan --trials 1 --no-save
```

**Dead everywhere, or only out of band?**

```bash
source ~/gnuradio-3.8/setup_env.sh && python3 ~/radar2/twinrx_band_check.py --freqs 100e6,300e6,700e6,1.2e9,1.8e9,2.4e9
```

Dead at 100 MHz too rules out an out-of-band component.

**Is the phase wandering, or is the LO re-rolling on tune?**

```bash
source ~/gnuradio-3.8/setup_env.sh && python3 ~/radar2/twinrx_lo_check.py --freq 2.4e9 --trials 5 --no-retune --no-save
```

**Are the numbers real?** Kill the transmitter mid-run and confirm every
channel follows it:

```bash
source ~/gnuradio-3.8/setup_env.sh && python3 ~/radar2/twinrx_lo_check.py --freq 2.4e9 --trials 1 --no-save
```
```bash
pkill -INT -f b210_tone_source.py
```
Re-run the check — all four should collapse to ~0 dB.

---

## 7. Useful switches

| switch | does |
|---|---|
| `--lo-sources a,b,c,d` | per-channel LO source: `internal` `companion` `external` `reimport` `disabled` |
| `--export-chan N` | which channel exports (0 = Rx A, 2 = Rx B) |
| `--port-scan` | native vs swapped antenna comparison |
| `--no-retune` | repeat the measurement without reprogramming the LO |
| `--single-tune` | tune once instead of twice, to demonstrate the FIFO overflow |
| `--broadband` | whole-band averaging, for a noise source instead of a tone |
| `--no-save` | measure without updating `twinrx_lo_cal.json` |
| `--gain` / `--rx-gain` | calibration is only valid at the gains you used |

---

## 8. Housekeeping

```bash
pkill -INT -f b210_tone_source.py
```
```bash
pkill -f twinrx_lo_coherence.py
```

X310 pings but UHD cannot find it? Something still holds it:

```bash
ps aux | grep -E "twinrx|b210_tone|gnuradio" | grep -v grep
```

Never run `uhd_image_loader` on the X310. Its FPGA is compat 36 for UHD 3.15;
reflashing for 4.x breaks this whole setup.
