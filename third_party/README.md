# third_party/gr-doa

Source of the `doa` GNU Radio module that guru's original blocks come from
(`_doa_swig.so`, `libgnuradio-doa.so`, the `doa_*` GRC blocks in `installed_snapshot/`).

* Upstream: https://github.com/EttusResearch/gr-doa at `7f982b7` (GR 3.7 / X310 + TwinRX line),
  ported to GNU Radio 3.8 and extended in the lab (`~/REPO/gr-doa`).
* `gr-doa_REPO_README.md` — the notes kept next to that clone.
* `gr-doa_git_log.txt` — the local commits on top of `7f982b7`.
* `gr-doa_changes_vs_upstream_7f982b7.patch` — every change vs upstream (committed + uncommitted).
* `gr-doa_uncommitted_status.txt` — files that were modified but not committed when saved.
* License: GPL-3.0 (`gr-doa/LICENSE.md`).

Build (GR 3.8 env; from `gr-doa_REPO_README.md`):

```bash
source ~/gnuradio-3.8/setup_env.sh
cd third_party/gr-doa && mkdir -p build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=$HOME/gnuradio-3.8 \
         -DCMAKE_PREFIX_PATH="$HOME/gnuradio-3.8;$HOME/uhd-3.15;$HOME/.local" \
         -DARMADILLO_INCLUDE_DIR=$HOME/.local/include \
         -DARMADILLO_LIBRARY=$HOME/.local/lib/libarmadillo.so \
         -DENABLE_TESTING=OFF -DENABLE_DOXYGEN=OFF
```

(then `make` / `make install` as in that file). The guru_fast Python blocks (`oot/`) do not need this build; `install_blocks.sh` installs them.
