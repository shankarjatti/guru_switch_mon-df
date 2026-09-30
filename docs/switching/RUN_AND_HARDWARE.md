# Hardware setup and how to run

## Hardware
| item | detail |
|---|---|
| receiver | NI USRP-2945 = Ettus X310 (serial 31082D8) + 2 × TwinRX Rev B (Rx A 3104B3C, Rx B 31050CD) |
| LO cables | Rx B J3 (LO1 OUT) → Rx A J4 (LO1 IN); Rx B J1 (LO2 OUT) → Rx A J2 (LO2 IN). (A→B pair fitted, passes no LO) |
| RF (lab) | HackRF One → power divider (~7 dB split) → Rx A RX1, Rx A RX2, Rx B RX1, Rx B RX2 |
| host link | Ethernet `enp3s0` 192.168.10.1/24 ↔ X310 192.168.10.2, 1 Gb/s link (Realtek RTL8125 2.5 GbE NIC) — enough for 4 × 2 MS/s; ~25–30 MS/s total at most |
| host | Ubuntu 22.04 (kernel 6.8), 12 cores; rtprio limit for the user (real-time priority 90) |
| clock | X310 internal; REF OUT (10 MHz) on — can feed the HackRF CLKIN so the tone lands exactly at 200 kHz |

Damage limits: TwinRX +10 dBm at the port. No attenuator pad is fitted — keep the HackRF VGA as set (14 / 47).

## Software
* GNU Radio **3.8.5** + UHD **3.15** in `~/gnuradio-3.8` and `~/uhd-3.15` (isolated; `source ~/gnuradio-3.8/setup_env.sh`).
  The FPGA image is the UHD 3.15 one. The system GNU Radio 3.10 / UHD 4 is NOT used for the receiver.
* The HackRF runs under the system GNU Radio 3.10 (gr-soapy), in its own process, controlled over UDP 127.0.0.1:5123
  (`freq`, `vga`, `ppm`, `get`, `ping`, `quit`) — `run_hop.sh` starts it.
* DF blocks: the installed `doa` package in `~/gnuradio-3.8` (same as `installed_snapshot/`; `./RESTORE.sh --check`
  compares, `./RESTORE.sh` puts them back). `switch_source` and `libtwinrx_switch.so` are used from this folder.

## Run
```bash
cd ~/radar2/guru_switch && ./run_hop.sh --switch
```
1. It checks the X310 (3 pings), starts the HackRF tone source if needed, then the program — in **DF**.
2. **CALIBRATE** (in DF) at every start; after it passes the phases read ~0° on 2.4 / 5.2 / 5.8 GHz.
3. **MODE** selector above the tabs: DF (shared LO, hopping) ⇄ MON (own LO per channel, continuous). Only this
   selector changes the mode. The line next to it: mode, switches, last switch time (request → first dwell), samples.
4. DF: tabs Hopping / Spectra / Switching (as guru_burst). MON: tab **MON** — per LO spectrum, time graph, status line.
5. LAB TONE: moves the HackRF (2.4 / 5.2 / 5.8 GHz / 900 MHz). In MON only that band's channel shows the tone.
6. Stop: close the window (never kill the process — a killed program can leave the X310 wedged).

Regenerate after a change: `python3 make_guru_switch.py && GRC_BLOCKS_PATH=$GRC_BLOCKS_PATH:$PWD/grc grcc guru_switch.grc -o .`
Options: `--mon 900e6:60,2.4e9:46,5.2e9:60,5.8e9:69` (MON band:gain per channel), `--mon-dwell`, `--switch-gap`,
`--start-mode`, `--api 127.0.0.1:5124` (control API, OFF by default).
Open in GRC: `GRC_BLOCKS_PATH=$GRC_BLOCKS_PATH:$PWD/grc ~/gnuradio-3.8/run_grc.sh guru_switch.grc`.

## Tests (RX only; close the GUI first)
```bash
source ~/gnuradio-3.8/setup_env.sh
python3 switch_check.py --rounds 50          # DF phase after trips through MON (pyuhd)
python3 route_burst_test.py                  # timed routing, command order, chained bursts
python3 switch_engine_check.py --cycles 10   # engine + source, no GUI (switches by itself: a TEST)
python3 mon_port_check.py                    # MON: same freq + gain on all channels -> port levels
python3 tone_freq_check.py --rate 2e6 --offset 200e3 --dc-guard 20e3   # where the tone lands per channel
```
`switch_validate.py` needs the GUI built with `--api`.

## Troubleshooting
| symptom | cause / fix |
|---|---|
| `X310 does not answer` / `No UHD Devices Found` | X310 off or cable; `ip -br addr show enp3s0`; if no address: `sudo ip addr add 192.168.10.1/24 dev enp3s0 && sudo ip link set enp3s0 up` |
| "no tone" on every band | the HackRF stopped: `/tmp/hackrf_tone.log` (TIMEOUT, watchdog). It restarts itself as a fresh process; if it keeps dropping off USB, another port / cable / powered hub |
| one channel weak | cable / divider output (`mon_port_check.py`; ch0 is 13–16 dB low on this setup) |
| TIMING LOST | the PC fell behind (ring full): close heavy programs, restart; performance CPU governor helps |
| late slots in the mode line | PC latency; late slots are never used |
| phases not ~0 in DF | press CALIBRATE (needed after every start / power cycle / cable change) |
| logs | receiver `/tmp/guru_rx.log`, UHD `/tmp/guru_uhd.log`, transmitter `/tmp/hackrf_tone.log` |
