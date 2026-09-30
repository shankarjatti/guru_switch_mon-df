# x310-rx-timestamp-2x-and-hop-timing

_USRP-2945 radio-clock hopping — what works (C++ engine, staggered+2nd-pass timed tune, whole-sample slots), what breaks (gr-uhd 180° ch0 flips, Python GIL stalls, reads behind timed cmds), RX timestamps 2x._

Measured 2026-09-28 on the USRP-2945 (raw data in guru/results/, design in guru/README.md "guru_fast").

- **Phase-correct timed tune:** gains at T, channel c's RF tune (rf manual, dsp POLICY_NONE) at T + c*0.4 ms, the same 4 RF tunes again at T+3 ms. Matches guru's untimed+timed tune within 0.1° (30/30). One timed pass: right frequency, wrong and *repeatable* LO phase state (11°–180°, depends on previous band) — it looks steady, so only a comparison against a reference catches it.
- **gr-uhd is unusable for this:** the same schedule through gr-uhd (guru's block or a bare usrp_source) left ch0 exactly 180° off on 6–12 % of 5.8 GHz dwells; through UHD's own API (pyuhd or C++) 0 flips. Not caused by concurrent get_rx_freq reads (tested). Hence `twinrx_radio_source` + C++ `libtwinrx_engine.so`.
- **Python scheduler is not enough with the GUI:** GIL/OS stalls 16–34 ms → ~0.5 % skipped/late slots. C++ engine: 4720/4720 and 3219/3219 slots, 0 skipped/late. Setting sys.setswitchinterval(0.2 ms) and gc tuning both made it WORSE (measured).
- **Any radio read (get_time_now, get_sensor) issued while a timed command is pending is queued behind it.** Per slot: read lock at S+7 ms, then send the next batch. Never read the radio from the flowgraph thread.
- **DDC is 0 Hz on all channels for 2.4/5.2/5.8 GHz** → pin once, never command it while hopping ([twinrx-ddc-timed-command-fifo](twinrx-ddc-timed-command-fifo.md)).
- **RX packet time_spec steps at 2x** (first packet = commanded start). Time samples as start + n/fs; the step is only a gap detector. gr-uhd retune rx_time tags follow the same 2x rule, except an occasional mid-packet tag off by 50–150 samples (quirk, not loss).
- **Slots must be scheduled in whole samples** (n_S integer, S = start + n_S/fs) or float rounding makes dwell boundaries jitter by a sample.
- **Drift:** ch2/ch3 (cross the board A↔B LO cable) moved +2.6/+3.2° at 5.2/5.8 GHz within 1.5 h in the morning; in the afternoon (after hours of running) CALIBRATE found 4.5° then 7.8° changes within 16–18 min. Program restarts are NOT the cause (two starts 40 s apart both ≤0.55° with one table). guru_fast CALIBRATE (hop_calibrator.py) measures all bands with strict accept rules; advise calibrating at start and every 5–10 min.
- **User's display spec (2026-09-28, final):** HackRF transmits only on the LAB TONE band (2.4 GHz), moved only by that chooser or CALIBRATE. Main tab like the original guru: ONE sine plot of the tone band's dwells + "chN − ch0 phase offset" readouts ("NO TONE – nothing measured", never 0.000), with RECEIVING NOW / LO LOCK / SHOWING lines above. The whole 60 ms cycle plot (tone dwell vs flat dwells) is on the Switching tab with one line per band. Not three plots.

- **Burst mode works (2026-09-29, `guru_burst`, lab commit 03f222b):** timed NUM_SAMPS_AND_DONE per dwell; the first packet of every burst is stamped exactly at its commanded sample (6,472/6,472 bursts, exact length), phase = continuous mode. Limit at 5 ms/7 ms is the PC: the lock read is at 6.5 ms, leaving ~5.5 ms to send the next batch; UHD tune calls (typ 2.3 ms) stall to ~6 ms without rtprio → 1.7–14.5 % late. rtprio is required there.
- **HackRF vs X310: −4.5 ppm** (2026-09-29), drifting several kHz during warm-up → a 10 kHz tone lands near/over 0 Hz; stay at 200 kHz unless the HackRF is locked to X310 REF OUT.

**How to apply:** build on the engine; never reintroduce gr-uhd or a Python scheduler for fast hopping ([feedback-permanent-real-solutions](feedback-permanent-real-solutions.md), [final-project-real-antennas](final-project-real-antennas.md)).
