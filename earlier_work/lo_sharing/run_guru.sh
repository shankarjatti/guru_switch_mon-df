#!/usr/bin/env bash
# ==============================================================================
# run_guru.sh — Launch the complete Guru 4-Channel Coherent Receiver
# ==============================================================================
# Features:
#   - Automated B210 Calibration Tone Source in background
#   - USRP-2945 (X310 + 2x TwinRX) 4-channel coherent LO receiver
#   - Phase-aligned & amplitude-normalized RF waveforms scope
#   - Live controls for Center Frequency (Hz) and RX Gain (dB)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GR38_ENV="${HOME}/gnuradio-3.8/setup_env.sh"

if [ ! -f "${GR38_ENV}" ]; then
    echo "ERROR: GNU Radio 3.8 environment script not found at ${GR38_ENV}"
    exit 1
fi

source "${GR38_ENV}"
exec python3 "${SCRIPT_DIR}/guru.py" "$@"
