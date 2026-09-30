# guru_switch — USRP-2945 DF + MON in one program, switched on the radio clock

Work copy made 2026-09-30 from the frozen `~/radar2/guru_DF_v1` (DF) and `~/radar2/guru_MON_v1` (MON).
Those two stay untouched. Nothing here is installed into `~/gnuradio-3.8`: the new engine
(`oot/engine/libtwinrx_switch.so`), the source block (`switch_source.py`) and its GRC definition
(`grc/switch_source.block.yml`) live in this folder; the DF blocks after the source are the installed,
verified ones (same as guru_DF_v1).

```bash
cd ~/radar2/guru_switch && ./run_hop.sh --switch          # GUI; then CALIBRATE (in DF)
python3 switch_validate.py --switches 150                 # validation through the API (GUI running)
```

## Modes
| | DF | MON |
|---|---|---|
| LO | shared: board B exports (ch0/ch1 external, ch2 internal + export, ch3 companion) | every channel its OWN internal LO, export off |
| bands | 2.4 → 5.2 → 5.8 GHz on all 4 channels, 7 ms switching + 5 ms dwell (burst mode) | ch0 900 MHz, ch1 2.4, ch2 5.2, ch3 5.8 GHz, ONE continuous stream (timed start, stop at the switch back); lock read every 20 ms |
| outputs | 0–3 of `switch_source`, tags `hop_off` / `hop_on` / `hop_cycle` exactly as guru_burst | 4–7, tags `mon_on` (verified dwell) / `mon_bad` / `mon_off` |
| on screen | the DF tabs of guru_burst (Hopping, Spectra, Switching, CALIBRATE) | MON tab: per LO spectrum, time graph, status line |

The mode changes **only with the MODE selector** (above the tabs) — nothing switches by itself (user,
2026-09-30). An optional control API (`python3 make_guru_switch.py --api 127.0.0.1:5124`, UDP: `mode df` ·
`mode mon` · `status`) is OFF by default. A request is taken at the next slot boundary.

## How a switch works (engine, `twinrx_engine.cpp`)
1. The request is taken at a slot boundary.
2. The scheduler waits until the old mode's last dwell has **ended**, then sends the LO routing **untimed**
   (nothing timed is waiting then, so it takes ~1–3 ms).
3. The new slot starts `switch_gap` (10 ms) after that dwell: the usual phase-correct **timed** tune
   (gains at S, ch c at S + c·0.4 ms, second pass at S + 3 ms), lock read, burst.
4. MON: after its tune, ONE continuous stream (STREAM_MODE_START_CONTINUOUS, timed at the first MON sample);
   the engine keeps a 20 ms record with a lock read (one channel in turn). Back to DF: the stream is stopped,
   it ends where it ends (end-of-burst gives the exact last sample), routing untimed, DF slot switch_gap later.

Why this way (all measured 2026-09-30, see `docs/WORK_LOG.md`):
* **untimed tunes** leave the TwinRX LO dividers in random 90°-multiple states — only the engine's timed,
  staggered, second-pass tune returns the DF phase (`switch_check.py`);
* **timed routing** does take effect at its time (`route_burst_test.py`), but in the running engine every
  routing call reads the TwinRX back, the read waits behind the timed write, the host blocks until S and the
  tune after it goes out late → routing untimed after the old dwell instead;
* the radio runs commands strictly in order; 200 burst commands at once overflow its queue.

## Measured (cable: HackRF 200 kHz tone → divider → 4 ports)
* `switch_check.py` (pyuhd, DF → MON → DF, 150 trips): DF phase after a MON trip worst 0.33° (plain DF retune
  0.26°); lock 4–8 ms after the timed tune.
* `switch_engine_check.py` (engine + source, no GUI, 10 switches): 1558/1558 slots used, 0 late / unlocked /
  missing bursts; DF phase after each return ≤ 0.26°; every DF dwell 10,000 samples, every MON dwell 40,000;
  MON: only the tone band's channel sees the tone (ch1 84.8 dB; ch0 34 dB = board-mate leak).
* GUI + API (20 switches): 20/20 locked and used, 0 missing bursts; request → first dwell DF→MON ~24–33 ms,
  MON→DF ~38–50 ms (the request waits for the next planned slot: up to two slots, + switch gap + settle).
* `switch_validate.py`: see the WORK_LOG entry of the run.

## Known limits
* **CPU headroom**: the DF chain's Python blocks run close to their limit at 2 MS/s; the MON path is C++ only
  (probes, thinned displays) for that reason. A busy PC (kernel worker at 60 %, `powersave` governor) made DF
  band changes slower (4 ms instead of 1.1) → late slots (marked, never used). Performance governor: user.
* ch0 (A/RX1) RF path 13–16 dB low (a cable/port fault, `mon_port_check.py`).
* The X310 was power-cycled on 2026-09-30 → press CALIBRATE (in DF) before trusting DF phases; the start state
  can come up 180° apart between program starts.
* MON frequencies/gains are fixed at start (`make_guru_switch.py --mon`); changing them live is not built yet.

## Files
`guru_switch.grc/.py` (generated: `python3 make_guru_switch.py && GRC_BLOCKS_PATH=$GRC_BLOCKS_PATH:$PWD/grc grcc guru_switch.grc -o .`) ·
`switch_source.py` · `oot/engine/twinrx_engine.cpp` (+ `build.sh`: `OUT=libtwinrx_switch.so ./build.sh`) ·
`grc/switch_source.block.yml` · `switch_check.py` · `route_burst_test.py` · `switch_engine_check.py` ·
`switch_validate.py` · `run_hop.sh --switch` · everything of guru_DF_v1 and guru_MON_v1.
