# guru_fast — how to run it

USRP-2945 (X310 + 2× TwinRX) hopping **2.4 → 5.2 → 5.8 GHz**, each band
**10 ms OFF (switching, LO relocks, discarded) + 10 ms ON (dwell, used)**,
one cycle = **60 ms**, timed by the X310's own clock. HackRF One = lab tone.

## 1. Before you start

* X310 powered, Ethernet on `enp3s0` (192.168.10.1 ↔ X310 192.168.10.2), 1 GigE.
* LO cables between the two TwinRX boards in place (board B exports the LO).
* HackRF One on USB, its output through the splitter into all 4 RX ports.
* **After an X310 power cycle the phase table is invalid** — press CALIBRATE (step 4).

## 2. First time only (or after changing any block code)

```bash
cd ~/radar2/guru
./install_blocks.sh
```

Builds the C++ engine (`oot/engine/twinrx_engine.cpp` → `libtwinrx_engine.so`)
and installs every block into `~/gnuradio-3.8`. Close guru first.

## 3. Start

```bash
cd ~/radar2/guru
./run_hop.sh --fast
```

This starts the HackRF tone (on 2.4 GHz) first, then `guru_fast.py`.
Logs: `/tmp/guru_rx.log` (receiver), `/tmp/hackrf_tone.log` (transmitter).
Restart everything cleanly: `./run_hop.sh --fast --restart`.
Stop: close the window (never `kill -9`).

## 4. Calibrate

Press **CALIBRATE** (top left). For ~15 s the HackRF visits 2.4, 5.2 and 5.8 GHz,
each band's offsets are measured on its own 10 ms dwells, and the HackRF goes
back to the LAB TONE band. The new table is applied **only if every band
passes** (≥ 50 dwells, a tone in every dwell, spread < 0.3°, no dwell > 1° off);
the line next to the button says `OK ...` or `REJECTED ...` and why.

**When:** after every start, and every **5–10 minutes** if you need < 1°.
Measured today: restarts are stable (two starts ≤ 0.55°), but the offsets drift
with temperature — up to ~8° in 16 min this afternoon on the board-A↔B pairs.

## 5. What you see

**Hopping tab (main)** — like the original guru screen, plus the hopping status

| Item | Meaning |
|---|---|
| LAB TONE (HackRF) BAND | where the HackRF transmits. Default **2.4 GHz only**; it is never retuned unless you change this or press CALIBRATE. |
| SCHEDULE | slots / used / late / unlocked / skipped, typical and worst send time vs the limit (13 ms) |
| STREAM | `receiving`, or `STOPPED` / `TIMING LOST` (then nothing is a reading) |
| RECEIVING NOW | band being received now, and whether it is switching or in its 10 ms dwell |
| LO LOCK | per band: dwells with the LO lock confirmed / all dwells (a dwell without confirmed lock is never used) |
| SHOWING | which band the plot shows (the LAB TONE band) and that its LO was locked. In **red** if that band has **no tone** (the transmitter is not sending there) — the receiver is still fine. |
| RF waveforms plot | sine waves of the LAB TONE band's 10 ms dwells, all 4 channels |
| chN − ch0 phase offset (deg) | average of the last 10 dwells of that band; **NO TONE – nothing measured** when there is no tone (never a made-up 0.000) |

**Switching tab** — one plot of the whole 60 ms cycle:
0–10 ms switch, **10–20 ms 2.4 GHz**, 20–30 switch, **30–40 ms 5.2 GHz**, 40–50 switch,
**50–60 ms 5.8 GHz**. With the HackRF on 2.4 GHz only the 10–20 ms window has a signal;
the other dwells are **flat**. Under it one line per band: `SIGNAL` + phases, or `FLAT` + `nan`.

**Spectra tab** — spectrum of the LAB TONE band's dwells.

If the plot goes flat for a few seconds while LO LOCK stays full, the HackRF's
own transmit stream stalled and its watchdog is restarting it (see
`/tmp/hackrf_tone.log`, lines `[watchdog] ...`). That is the transmitter, not the
receiver. The tone script no longer retunes onto the frequency it is already on
(retuning is what makes the HackRF stall) and recovers a stall in ~2-3 s.

## 6. Safety rules built in

* A slot that is late, skipped or not locked is **never used** (counted in SCHEDULE).
* Lost samples → `TIMING LOST`, all dwells stop being used; restart.
* No tone on a band → `nan`, never an old or made-up number.

## 7. Optional: real-time priority (fewer "late" slots)

Once (then log out and in):

```bash
echo "shankar - rtprio 95" | sudo tee /etc/security/limits.d/99-sdr-rt.conf
```

Then set **Real-time priority = 90** in the *TwinRX Radio-Clock Hopping Source*
block (GRC → guru_fast.grc) and regenerate (step 8).

## 8. Editing the flowgraph

* Open in GNU Radio Companion 3.8: `~/gnuradio-3.8/run_grc.sh ~/radar2/guru/guru_fast.grc`
* After saving: `cd ~/radar2/guru && source ~/gnuradio-3.8/setup_env.sh && grcc guru_fast.grc -o .`
* Different bands: `python3 make_guru_fast.py --bands 2.4e9:46,5.2e9:60,5.8e9:69` then
  `grcc guru_fast.grc -o .` (1–4 bands; 5.00–5.14 GHz is refused — LO1 cannot lock there).
  `make_guru_fast.py` rebuilds guru_fast.grc from guru.grc, so edits made only in
  guru_fast.grc are lost if you run it.

## 9. Checks you can run (radio free, guru closed)

```bash
python3 dwell_exact_check.py --secs 60      # every dwell/switch/slot = exact sample count
python3 fast_chain_check.py --table phase_table_deg.txt --secs 20   # all bands within 1 deg?
python3 hop_blocks_selftest.py              # block logic, no radio
```

## 10. Back to a known-good state

```bash
~/radar2/BACKUP_FAST_2026-09-28/RESTORE.sh --check
~/radar2/BACKUP_FAST_2026-09-28/RESTORE.sh
```

## 11. Burst mode: 5 ms dwell / 7 ms switching, 2 MS/s, 200 kHz tone (guru_burst)

`guru_burst.grc` / `guru_burst.py`. The X310 sends **only each dwell** (plus 0.25 ms pre-roll inside the
switching time, never used); nothing while the LO relocks. The HackRF is **only a source** (plain
200 kHz tone, no correction from the receiver); everything is measured on the RX.

```bash
cd ~/radar2/guru
./run_hop.sh --burst            # then CALIBRATE
```

At 2 MS/s: dwell = **10,000 samples**, switching 14,000, one band slot 24,000, cycle 36 ms.
Bottom of the screen, 10x/s, from two independent engine counters:
`SAMPLES RECEIVED: n   DWELLS: m` (n / m = samples per dwell) and the tone frequency + cycles
counted on the last dwell (~1,000 for 200 kHz; the HackRF's own clock moves it a little).

* Every burst is checked for its exact start sample and length; a missing/late one is never used.
* The tone is the strongest line of the band; a tone within +/-2 kHz of 0 Hz is "NOT measured".
* Plots: display filter +/-10 kHz around the tone (all channels alike), autoscale; measurements
  use the unfiltered samples.
* Rebuild: `python3 make_guru_fast.py --burst --dwell 0.005 --settle 0.007 --rt-priority 90
  --display-filter 10e3 --samp-rate 2e6 --out guru_burst.grc && grcc guru_burst.grc -o .`
* Late slots come from the PC: enable real-time priority (section 7) and log in again.

Measured 2026-09-29 17:58 (2 MS/s, 200 kHz, no rtprio): CAL OK (worst window 0.05 deg); 2.4 / 5.2 /
5.8 GHz tone +190.8 / +180.2 / +177.9 kHz (HackRF -3.8 ppm), 953.8 / 901.0 / 889.3 cycles counted,
samples / dwells = 10000.000 exactly in every 4 s window and every random reading, phases <= 0.1 deg,
5630/5632 slots (2 late), 0 unlocked, 0 overflow.
