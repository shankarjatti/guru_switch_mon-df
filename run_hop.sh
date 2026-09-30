#!/usr/bin/env bash
# Start the calibration transmitter and the hopping receiver together, in the
# order they have to go in: the transmitter first, because the receiver
# commands it on every hop and refuses to start without it.
#
# The two halves need different GNU Radio installs -- the B210 and the HackRF
# need the system 3.10, the TwinRX needs ~/gnuradio-3.8 -- so they cannot share
# a process and talk over UDP instead.
#
#   ./run_hop.sh              start both; Ctrl-C or closing the window stops both
#   ./run_hop.sh --restart    stop whatever is running first, then start both
#   ./run_hop.sh --vga 60     louder transmitter
#   ./run_hop.sh --fast       guru_fast.py: 10 ms radio-clock hopping instead of guru.py
#   ./run_hop.sh --burst      guru_burst.py: 5 ms dwell / 7 ms switching, burst mode
#   ./run_hop.sh --mon        guru_mon.py: MON mode, every channel its own LO and band
#
# Bands, gains, dwell and LO settings all live in guru.grc, not here.
set -u

RESTART=0
RX=guru.py
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --restart) RESTART=1 ;;
        --fast) RX=guru_fast.py ;;
        --burst) RX=guru_burst.py ;;
        --mon) RX=guru_mon.py ;;
        *) ARGS+=("$arg") ;;
    esac
done
set -- ${ARGS+"${ARGS[@]}"}

CTRL_HOST=127.0.0.1
CTRL_PORT=5123
# the folder this script is in: guru_fast.py and the tone script are run from
# here, so a copy of the project (e.g. guru10ms) runs its own files
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TXLOG=/tmp/hackrf_tone.log


# The HackRF needs the system GNU Radio 3.10 (gr-soapy), while this shell
# defaults to 3.8 for the TwinRX. The interactive gr310 helper is a shell
# function, so a script never inherits it -- and the GRSYS_* variables it
# relies on only exist once ~/.bashrc has run interactively. Rebuild the
# system environment here instead, either from those variables when they were
# inherited, or by filtering the 3.8 tree out of the paths.
strip38() {
    local out="" part
    local IFS=:
    for part in $1; do
        case "$part" in
            *gnuradio-3.8*) ;;
            "") ;;
            *) out="${out:+$out:}$part" ;;
        esac
    done
    printf '%s' "$out"
}

run_under_system_gnuradio() {
    env -u GR38_DIR -u UHD315_DIR \
        PATH="${GRSYS_PATH:-$(strip38 "$PATH")}" \
        LD_LIBRARY_PATH="${GRSYS_LD_LIBRARY_PATH:-$(strip38 "${LD_LIBRARY_PATH:-}")}" \
        PYTHONPATH="${GRSYS_PYTHONPATH:-$(strip38 "${PYTHONPATH:-}")}" \
        GRC_BLOCKS_PATH="${GRSYS_GRC_BLOCKS_PATH:-$(strip38 "${GRC_BLOCKS_PATH:-}")}" \
        PKG_CONFIG_PATH="${GRSYS_PKG_CONFIG_PATH:-$(strip38 "${PKG_CONFIG_PATH:-}")}" \
        CMAKE_PREFIX_PATH="${GRSYS_CMAKE_PREFIX_PATH:-$(strip38 "${CMAKE_PREFIX_PATH:-}")}" \
        "$@"
}

cleanup() {
    if [ -n "${TXPID:-}" ] && kill -0 "$TXPID" 2>/dev/null; then
        echo "[run] stopping the transmitter (pid $TXPID)"
        kill "$TXPID" 2>/dev/null
        wait "$TXPID" 2>/dev/null
    fi
}
trap cleanup EXIT INT TERM

# ---- 0. optional restart ---------------------------------------------------
# A plain TERM, never KILL. The receiver has to run its own shutdown: the hop
# thread must stop before the flowgraph tears down, or the X310's control plane
# is left wedged and only a power cycle clears it.
if [ "$RESTART" = "1" ]; then
    echo "[run] --restart: stopping anything already running"
    stopped=0
    for pat in "python3 -u guru\.py" "guru/guru\.py" "python3 -u guru_(fast|burst|mon)\.py" "hackrf_tone_source\.py"; do
        if pgrep -f "$pat" >/dev/null 2>&1; then
            pkill -f "$pat" 2>/dev/null
            stopped=1
        fi
    done
    if [ "$stopped" = "1" ]; then
        # Wait for them to actually go, and for the radio to be released.
        # Starting while the old process still holds the X310 fails with a
        # confusing "No devices found".
        for _ in $(seq 1 40); do
            pgrep -f "python3 -u guru\.py|guru/guru\.py|python3 -u guru_(fast|burst|mon)\.py|hackrf_tone_source\.py" \
                >/dev/null 2>&1 || break
            sleep 0.25
        done
        if pgrep -f "python3 -u guru\.py|guru/guru\.py|python3 -u guru_(fast|burst|mon)\.py|hackrf_tone_source\.py" \
            >/dev/null 2>&1; then
            echo "[run] something did not stop within 10 s:"
            pgrep -af "python3 -u guru\.py|guru/guru\.py|python3 -u guru_(fast|burst|mon)\.py|hackrf_tone_source\.py"
            echo "      Not forcing it -- a killed receiver can leave the X310"
            echo "      needing a power cycle. Close it yourself and try again."
            exit 1
        fi
        echo "[run] stopped."
        sleep 1
    else
        echo "[run] nothing was running."
    fi
fi

# ---- 1. the X310 has to be answering before anything else is worth doing ----
echo "[run] checking the X310 ..."
if ! ping -c3 -W1 192.168.10.2 >/dev/null 2>&1; then
    echo "[run] X310 does not answer on 192.168.10.2."
    echo "      Check the cable, and that enp3s0 still has its address:"
    echo "        sudo ip addr add 192.168.10.1/24 dev enp3s0 && sudo ip link set enp3s0 up"
    exit 1
fi

# ---- 1b. one receiver at a time ----
if pgrep -f "python3 .*guru/guru\.py|python3 -u guru\.py" >/dev/null 2>&1; then
    echo "[run] a receiver is already running -- close that window first."
    echo "      Two of them cannot share the X310, and the second just fails"
    echo "      with a confusing 'No devices found'."
    exit 1
fi

# ---- 2. transmitter, under the SYSTEM GNU Radio ----
# guru_burst listens for a 10 kHz tone, guru/guru_fast for 200 kHz: the tone
# source has to be started for the one being run. It remembers what it was
# started with in $TXMODE, and is restarted if that is not what is needed.
TXMODE=/tmp/hackrf_tone.mode
TX_OFFSET=200e3
TX_EXTRA=""
if [ "$RX" = "guru_burst.py" ] || [ "$RX" = "guru_mon.py" ]; then
    # the transmitter is only a source: plain 10 kHz from its own clock, no
    # correction fed back from the receiver. Everything is measured on the RX.
    # 200 kHz: far from 0 Hz on every band even with the HackRF's own clock
    # error (-3.8 ppm = -22 kHz at 5.8 GHz); 10 kHz landed at +835 Hz on 2.4 GHz
    TX_OFFSET=200e3
fi
# the clock correction is applied live at every start (below), so it is not
# part of what the transmitter has to be restarted for
# v2: the transmitter answers 'get' (its real clock correction) -- an older one is restarted
WANT="offset $TX_OFFSET v3-source-only"
if pgrep -f hackrf_tone_source.py >/dev/null && [ "$(cat "$TXMODE" 2>/dev/null)" != "$WANT" ]; then
    echo "[run] transmitter running with '$(cat "$TXMODE" 2>/dev/null || echo unknown settings)',"
    echo "      this receiver needs '$WANT' -- restarting it"
    python3 - "$CTRL_HOST" "$CTRL_PORT" <<'PY2' 2>/dev/null
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(1.0)
s.sendto(b"quit", (sys.argv[1], int(sys.argv[2])))
s.recv(16)
PY2
    for _ in $(seq 1 20); do pgrep -f hackrf_tone_source.py >/dev/null || break; sleep 0.25; done
fi
if pgrep -f hackrf_tone_source.py >/dev/null; then
    echo "[run] transmitter already running ($WANT) -- leaving it alone"
    TXPID=""
else
    # No per-band tone offsets on either radio: every band is centre plus
    # 200 kHz. Where the LO fallback mirrors the spectrum the receiver
    # mirrors it back.
    if lsusb | grep -qi "1d50:6089"; then
        # The HackRF needs 2 Msps. At 1 Msps its SoapySDR stream produces
        # continuous timeouts. Per-band drive because its output falls off
        # badly at 5 GHz and up: one gain either clips 2.4 or buries the
        # others.
        RADIO_ARGS="--radio hackrf --vga 14 --rate 2e6 \
                    --vga-map 900e6:14,2.4e9:14,5.2e9:47,5.8e9:47"
        echo "[run] HackRF One found -- using it as the calibration source"
        echo "[run] note: this radio's stream has been seen to stall under"
        echo "      repeated retuning and not recover, which reads as a band"
        echo "      with no tone. The tone source restarts a stalled stream;"
        echo "      watch $TXLOG if a band goes quiet."
    elif lsusb | grep -qi "2500:"; then
        RADIO_ARGS="--radio b210 --vga 55 --rate 1e6"
        echo "[run] B210 found -- using it as the calibration source"
    else
        echo "[run] no transmitter on USB -- plug in the HackRF One (or a B210)."
        exit 1
    fi
    echo "[run] starting the tone source (log: $TXLOG)"
    # shellcheck disable=SC2086
    run_under_system_gnuradio python3 "$HERE/hackrf_tone_source.py" \
        $RADIO_ARGS --offset $TX_OFFSET $TX_EXTRA --control "$CTRL_HOST:$CTRL_PORT" "$@" > "$TXLOG" 2>&1 &
    TXPID=$!
    echo "$WANT" > "$TXMODE"
fi

# ---- 3. wait until it actually answers, rather than guessing at a sleep ----
echo -n "[run] waiting for the transmitter (a cold B210 loads FPGA first) "
for _ in $(seq 1 120); do
    if python3 - "$CTRL_HOST" "$CTRL_PORT" <<'PY' 2>/dev/null
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(0.5)
s.sendto(b"ping", (sys.argv[1], int(sys.argv[2])))
sys.exit(0 if s.recv(16) else 1)
PY
    then
        echo " ok"
        break
    fi
    echo -n "."
    sleep 0.5
done

if ! python3 - "$CTRL_HOST" "$CTRL_PORT" <<'PY' 2>/dev/null
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(0.5)
s.sendto(b"ping", (sys.argv[1], int(sys.argv[2])))
sys.exit(0 if s.recv(16) else 1)
PY
then
    echo
    echo "[run] the transmitter never answered. Last lines of $TXLOG:"
    tail -15 "$TXLOG"
    exit 1
fi

# ---- 4. receiver, under GNU Radio 3.8 ----
# Keep the run's own record. The block's stream watchdog reports what it did,
# but not why the radio stopped -- UHD's own overflow, time-align and late
# command messages are what say that, and they are only useful if they were
# written down when it happened.
RXLOG=/tmp/guru_rx.log
export UHD_LOG_FILE=/tmp/guru_uhd.log
export UHD_LOG_FILE_LEVEL=info

echo "[run] starting $RX"
echo "[run] receiver log: $RXLOG    UHD log: $UHD_LOG_FILE"
echo "[run] close the window (or Ctrl-C) to stop both."
# shellcheck disable=SC1090
# setup_env.sh appends to LD_LIBRARY_PATH/PYTHONPATH etc., which may be unset:
# under set -u that stopped the script here, before the receiver started
set +u
source "$HOME/gnuradio-3.8/setup_env.sh" >/dev/null 2>&1
set -u
cd "$HERE" || exit 1
python3 -u "$RX" 2>&1 | tee "$RXLOG"
