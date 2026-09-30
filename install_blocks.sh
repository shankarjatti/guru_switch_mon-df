#!/usr/bin/env bash
# Build the C++ engine and install every guru block into the GR 3.8 tree.
#   ./install_blocks.sh
# Close guru / guru_fast first: replacing a loaded library can crash them.
set -e
cd "$(dirname "$0")"
D=$HOME/gnuradio-3.8/lib/python3/dist-packages/doa
B=$HOME/gnuradio-3.8/share/gnuradio/grc/blocks
# only real running Python programs count (a shell whose command line merely
# mentions these names must not)
if pgrep -f "^python3 .*(guru(_fast|_burst)?\.py|gui_band_tour\.py|fast_chain_check\.py|dwell_exact_check\.py)" >/dev/null; then
    echo "guru is running -- close it first:"
    pgrep -af "^python3 .*(guru(_fast|_burst)?\.py|gui_band_tour\.py|fast_chain_check\.py|dwell_exact_check\.py)"
    exit 1
fi
oot/engine/build.sh
cp oot/twinrx_usrp_source.py oot/twinrx_hopping_source.py oot/phase_correct_hopping.py \
   oot/hop_blocks.py oot/hop_calibrator.py oot/twinrx_radio_source.py "$D/"
# atomic replace: a process that still has the old library mapped keeps it
cp oot/engine/libtwinrx_engine.so "$D/.libtwinrx_engine.so.new" && mv -f "$D/.libtwinrx_engine.so.new" "$D/libtwinrx_engine.so"
cp oot/twinrx_hopping_source.block.yml oot/phase_correct_hopping.block.yml \
   oot/twinrx_radio_source.block.yml oot/hop_band_select.block.yml \
   oot/hop_phase_meter.block.yml oot/hop_dc_remove.block.yml "$B/"
for line in "from .twinrx_hopping_source import twinrx_hopping_source" \
            "from .phase_correct_hopping import phase_correct_hopping" \
            "from .hop_blocks import hop_band_select, hop_phase_meter" \
            "from .hop_blocks import hop_dc_remove" \
            "from .twinrx_radio_source import twinrx_radio_source" \
            "from .hop_calibrator import hop_calibrator"; do
    grep -qxF "$line" "$D/__init__.py" || echo "$line" >> "$D/__init__.py"
done
rm -rf "$D/__pycache__"
source "$HOME/gnuradio-3.8/setup_env.sh" >/dev/null 2>&1
python3 -c "import doa; print('installed:', doa.twinrx_radio_source.__name__, doa.hop_band_select.__name__, doa.hop_phase_meter.__name__, doa.hop_calibrator.__name__)"
