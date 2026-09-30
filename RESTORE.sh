#!/usr/bin/env bash
# guru_DF_v1 -- DF (shared LO, coherent hopping) = guru0930 + later 2026-09-30 fixes, frozen 2026-09-30.
#
#   ./RESTORE.sh --verify   check that no file in this copy has changed (SHA256SUMS)
#   ./RESTORE.sh --check    compare the blocks installed in ~/gnuradio-3.8 with this copy
#   ./RESTORE.sh            put this copy's installed blocks back into ~/gnuradio-3.8
#
# The project files (guru_fast.grc/.py, oot/, scripts, tables) run from this
# folder as they are; only the GNU Radio side lives outside it.
# Before a restore, whatever is installed now is saved to ~/radar2/pre_restore_<time>/,
# so a restore can itself be undone.
set -u
B="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
S="$B/installed_snapshot"
DOA="$HOME/gnuradio-3.8/lib/python3/dist-packages/doa"
GRC="$HOME/gnuradio-3.8/share/gnuradio/grc/blocks"
LIB="$HOME/gnuradio-3.8/lib"

pairs() {
    for f in "$S"/doa/*;        do echo "$f $DOA/$(basename "$f")"; done
    for f in "$S"/grc_blocks/*; do echo "$f $GRC/$(basename "$f")"; done
    for f in "$S"/lib/*;        do echo "$f $LIB/$(basename "$f")"; done
}

case "${1:-}" in
--verify)
    cd "$B" && sha256sum --quiet -c SHA256SUMS && echo "all $(wc -l < SHA256SUMS) files intact"
    exit $? ;;
--check)
    n=0
    while read -r src dst; do
        if ! cmp -s "$src" "$dst"; then echo "DIFFERS  $dst"; n=$((n+1)); fi
    done < <(pairs)
    # the block sources in oot/ must be what the snapshot holds
    for f in "$B"/oot/*.py; do
        cmp -s "$f" "$S/doa/$(basename "$f")" || { echo "oot/ DIFFERS from snapshot  $(basename "$f")"; n=$((n+1)); }
    done
    [ $n -eq 0 ] && echo "installed blocks match guru_DF_v1 exactly" || echo "$n file(s) differ"
    exit 0 ;;
"") ;;
*) echo "usage: $0 [--verify|--check]"; exit 2 ;;
esac

if pgrep -f "^python3 .*(guru(_fast)?\.py|gui_band_tour\.py|fast_chain_check\.py|dwell_exact_check\.py)" >/dev/null; then
    echo "guru is running. Close its window first (never kill it -- that wedges the X310)."
    exit 1
fi

K="$HOME/radar2/pre_restore_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$K"
while read -r src dst; do
    if [ -e "$dst" ]; then
        mkdir -p "$K$(dirname "$dst")"
        cp -p "$dst" "$K$dst"
    fi
    mkdir -p "$(dirname "$dst")"
    # atomic for the engine library: a process that still maps the old one keeps it
    cp -p "$src" "$dst.restore_new" && mv -f "$dst.restore_new" "$dst"
done < <(pairs)
rm -rf "$DOA/__pycache__"

echo "restored. previous installed files saved in $K"
"$0" --check
