# GNU Radio 3.8 + UHD 3.15 isolated environment
export GR38_DIR="/home/shankar/gnuradio-3.8"
export UHD315_DIR="/home/shankar/uhd-3.15"

export PATH="$GR38_DIR/bin:$UHD315_DIR/bin:$PATH"
export LD_LIBRARY_PATH="$GR38_DIR/lib:$UHD315_DIR/lib:$HOME/.local/lib:$LD_LIBRARY_PATH"  # ~/.local/lib holds libarmadillo, which gr-doa links against
export PYTHONPATH="$GR38_DIR/lib/python3/dist-packages:$UHD315_DIR/lib/python3.10/site-packages:$PYTHONPATH"
export GRC_BLOCKS_PATH="$GR38_DIR/share/gnuradio/grc/blocks"
# 3.8-only GRC prefs: no local_blocks_path, so the GR 3.10 OOT modules
# do not appear in the 3.8 palette.
export GR_PREFS_PATH="$GR38_DIR/prefs"
# GRC always scans its hier-block dir; the shared ~/.grc_gnuradio holds 23
# GR 3.10 OOT definitions, so give 3.8 an empty one of its own.
export GRC_HIER_PATH="$GR38_DIR/grc_hier"
export PKG_CONFIG_PATH="$GR38_DIR/lib/pkgconfig:$UHD315_DIR/lib/pkgconfig:$PKG_CONFIG_PATH"
export CMAKE_PREFIX_PATH="$GR38_DIR:$UHD315_DIR:$CMAKE_PREFIX_PATH"

echo "=========================================================="
echo " GNU Radio 3.8 + UHD 3.15 Environment Loaded Successfully!"
echo "   GNU Radio version : $(gnuradio-config-info --version)"
echo "   UHD version       : $(uhd_config_info --version | grep -o 'UHD [0-9.]*')"
echo "=========================================================="
