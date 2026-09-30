# Theory — why DF and MON work the way they do on the USRP-2945

Everything here is either how the hardware is built, or a fact **measured on this unit**
(X310 serial `31082D8`, TwinRX `3104B3C` = Rx A, `31050CD` = Rx B). Measured facts name the test that
showed them (files in the repo root, raw results in `results/`).

## 1. The receiver
The USRP-2945 is an X310 motherboard with two **TwinRX** daughterboards. Each TwinRX has two receive
channels, so there are 4 channels:

| channel | subdev | port | board |
|---|---|---|---|
| ch0 | A:0 | RX1 | Rx A |
| ch1 | A:1 | RX2 | Rx A |
| ch2 | B:0 | RX1 | Rx B |
| ch3 | B:1 | RX2 | Rx B |

A TwinRX channel is a double-conversion superheterodyne (10 MHz – 6 GHz). The RF is mixed with **LO1**, then
with **LO2**, down to the IF the ADC samples; the X310's DDC then brings it to complex baseband.
Each channel has its own LO1 and LO2 synthesisers, and every LO can take its source from:

* `internal` — the channel's own synthesiser
* `companion` — the synthesiser of the other channel on the same board
* `external` — the LO IN connectors of the board (from another board's LO OUT)

and a channel can **export** its LO on the board's LO OUT connectors. On both boards
J1 = LO2 OUT, J2 = LO2 IN, J3 = LO1 OUT, J4 = LO1 IN. The working cables are **Rx B J3 → Rx A J4**
(LO1) and **Rx B J1 → Rx A J2** (LO2). The two cables in the other direction (A → B) pass no LO.

## 2. Phase coherence needs ONE synthesiser (DF)
A mixer multiplies the RF by the LO. The phase of the LO goes straight into the phase of the output:
two channels mixed with two *different* synthesisers have a phase difference that is random after every tune
and wanders with each synthesiser's own noise. Direction finding needs the phase differences between the
antennas, so all 4 channels must be mixed with the **same** LO:

* ch2: `internal` + **export** — the one master synthesiser (board B)
* ch3: `companion` — the same synthesiser, on board B
* ch0, ch1: `external` — the same synthesiser, over the J3→J4 / J1→J2 cables

The phase differences then depend only on fixed things (cables, board paths, filters), different per band.
They are measured once per session with a common tone (**CALIBRATE**) and removed.
Measured: with one shared LO, the phase repeats to ~0.1° across retunes; with each board on its own LO, 179°.

What still moves the table:
* **temperature** — drift ~0.2° per 20 min at 2.4 GHz, up to ~8° per 16 min at 5–6 GHz on the pairs that cross
  the board A↔B LO cable (the LO cable's electrical length changes with temperature; drift ∝ frequency);
* **a power cycle** of the X310, and even a program start can land in another state (seen: ch2 180° apart
  between two starts) → **calibrate at every start**;
* reseating a cable, changing the RX gain.

## 3. The LO divider state — why the tune must be timed, staggered, and done twice
The TwinRX synthesisers use frequency dividers after the VCO. A divider has several possible output
phases (for ÷2, ÷4: 0/90/180/270°). Which one it starts in after a retune is not defined, so after a
careless retune a channel can come back a multiple of 90° away from its calibrated phase.

Measured (`tune_method_phase_test.py`, `switch_check.py` first trial): **untimed** tunes left the phase an
exact multiple of 90° off after every retune; **one** timed pass came back to a repeatable but wrong state
(11°–180°, depending on the previous band). What returns the calibrated phase every time — 30/30, and 150/150
round trips through MON — is the tune the engine uses:

> gains at radio time **S**; channel c's RF tune at **S + c·0.4 ms**; the same four RF tunes again at **S + 3 ms**;
> the DDC is never commanded (it stays at 0 Hz).

So every band change in DF, and the return from MON, uses exactly this.

## 4. Independent LOs (MON)
Monitoring wants each channel on a different band at the same time, so each channel runs on its own
`internal` synthesiser with export off. The phases between channels are then meaningless — MON never uses
them. Each channel's own `lo_locked` sensor tells whether its synthesiser is locked (in DF the external
channels' sensor reports their own *unused* synthesiser, so there only ch2's is meaningful).

Measured (`guru_mon`, `mon_port_check.py`): with the tone on one band only that band's channel sees it; the other
channel **on the same board** shows it ~54–57 dB weaker at the identical baseband offset (crosstalk after
down-conversion, inside the board); the other board > 65 dB below.

## 5. The radio clock and timed commands
The X310 counts time with its own sample clock. A command can carry a time: the radio holds it until that
radio time, then executes it. Facts that shape the design (all measured):

* The radio's command queue runs **strictly in order**. A command for time T placed behind one for a later
  time waits for that later one (seen: `LATE_COMMAND` when a burst for T−3 ms was queued after commands for
  T and T+50 ms).
* **A read** (sensor, time, or the read-back inside a setter) **waits behind any pending timed command**.
  So the lock is read only after the slot's last timed command has executed, and the next slot's batch is
  sent after that read.
* A **timed LO-routing change** does take effect at its time (ch0's tone vanished 0.12 ms after T, never
  before). BUT every routing call reads the TwinRX back first; in a running schedule that read waited behind
  the timed write, the host was blocked until S, and the tune sent after it arrived **late** (all switch slots
  late, 30–45 ms). → The routing is sent **untimed**, right after the old mode's last dwell has ended, when
  nothing timed is waiting (0.6–4 ms).
* The queue is small: 200 stream commands issued at once — only 32 ran. The engine keeps one slot ahead.
* **Never give a DDC a command time**: its timed writes never retire and fill the FPGA queue at ~72 hops.
* gr-uhd is not used: the same schedule through gr-uhd left ch0 exactly 180° off on 6–12 % of 5.8 GHz dwells;
  through UHD's own API (C++, pyuhd) never.

All slot boundaries are computed in **whole samples** from the stream start (S = start + n/fs), so every dwell
has exactly the same number of samples.

## 6. Two ways to stream
* **Burst** (DF): each dwell is one timed `NUM_SAMPS_AND_DONE` command — the X310 sends pre-roll + dwell samples,
  then stops, so nothing is sent while the LO relocks. Every burst's first packet is stamped with its commanded
  start; the engine checks start sample and length and puts the bursts on one continuous timeline (zeros in the
  gaps). A burst that never came invalidates its slot.
* **Continuous** (MON): one timed `START_CONTINUOUS` at the first MON sample; samples flow until
  `STOP_CONTINUOUS`. The stop is not timed: the stream ends where it ends, and its last packet carries
  end-of-burst, which gives the exact last sample. The user asked for this for MON (2026-09-30): monitoring must
  not have gaps.

## 7. Measuring phase on a tone
The lab source is a HackRF sending a single tone (200 kHz above the band centre, pure source, never corrected)
through a power divider into all 4 ports. The phase of channel c against ch0 is taken at the tone's own FFT bins:

    X_c = FFT(x_c · hann),  k = the tone's bin (strongest line of the band, found on the sum of channels)
    phase_c = angle( Σ_{j=k-2..k+2} X_c[j] · conj(X_0[j]) )

Using only the tone's bins keeps other signals (Wi-Fi bursts over the air, the receiver's own 0 Hz leakage)
out of the estimate; a whole-band correlation was biased up to 175° by Wi-Fi at 5.2 GHz.
A phase is only reported when the tone is really there (`hop_phase_meter`: ≥ 20 dB over the in-band median on
every channel) — a channel receiving nothing still correlates through crosstalk and looks perfectly "steady".

**CALIBRATE** (`hop_calibrator`): per band, park the tone there, collect ≥ 50 dwell windows, take the circular
mean residual; the new table is applied only if every band passes (spread < 0.3°, no window > 1° off).

## 8. Why a C++ engine
The scheduler must send a batch every 12 ms and read the lock at an exact time. Python's interpreter lock and
OS stalls (16–34 ms with the GUI running) made a Python scheduler miss ~0.5 % of slots. The C++ engine runs a
receive thread and a scheduler thread at real-time priority (SCHED_FIFO 90), never touching Python.
Remaining limit: the flowgraph's Python blocks (DF meters) share one interpreter lock; at 2 MS/s they run close
to their limit, so everything new in the MON path is C++ (probes, thinned displays).
