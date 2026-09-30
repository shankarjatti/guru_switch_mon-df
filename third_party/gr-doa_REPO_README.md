# REPO — EttusResearch/gr-doa @ 7f982b7

    https://github.com/EttusResearch/gr-doa/tree/7f982b7e2447a7c08112db42e231a94791e88003

One folder, one repo, one commit. `gr-doa/` is checked out at **`7f982b7`** —
the GR 3.7 / X310+TwinRX line — with a port to GNU Radio 3.8 applied on top.

Nothing else lives here. The earlier `main`-branch clone and the loose copy of
`apps/` were removed; `main` is a different line (GR 3.10 / X440) and is
reachable from this clone's history if it is ever needed.

## State

    HEAD          7f982b7  (detached)
    working tree  22 files modified, 9 deleted  = the 3.8 port
    remote        https://github.com/EttusResearch/gr-doa

See every change with:

    git -C ~/REPO/gr-doa diff

## The port, in short

Built and installed into `~/gnuradio-3.8`. All **13 blocks** and all **14
flowgraphs** in `apps/` work there.

Build fixes:

1. CMake: require GR 3.8; `cmake_minimum_required` 3.8
2. deleted the bundled 3.7 CMake modules so GR 3.8's own are used
3. GR 3.8 module path added early — `include(GrPlatform)` runs before
   `find_package(Gnuradio)`
4. `include_directories(BEFORE ...)` — otherwise the compiler picked up the
   **system 3.10** headers and every block failed on `boost::shared_ptr`
   vs `std::shared_ptr`
5. SWIG include dirs pointed at the 3.8 tree so it can find `gnuradio.i`
6. linked `gnuradio-runtime` and `gnuradio-pmt` explicitly —
   `GNURADIO_ALL_LIBRARIES` came back empty, giving
   `undefined symbol: _ZTIN2gr5blockE`

Python 2 → 3:

7. print statements, mixed tabs, implicit relative imports
8. removed `import parser` (gone in 3.10, and unused)
9. deleted `build_utils*.py` (3.7 build-time helpers, py2-only, unreferenced)

Qt4 → Qt5 / Qwt5 → Qwt6, all in `python/compass.py`:

10. `PyQt4` → `PyQt5`; widgets moved `QtGui` → `QtWidgets`
11. old-style `SIGNAL()`/`connect()` → a real `pyqtSignal`
12. `QwtDial.setRange(min,max,step)` → `setScale()` + `setScaleStepSize()`
13. `QColor.light()` → `lighter()`
14. `int()` around Py3 true division feeding Qt size setters
15. added a `this_widget` wrapper — GRC's `gui_hint` emits `addWidget()`,
    but `this_layout` is a layout
16. `float()` around `lcd.display()` — PyQt5 rejects `numpy.float32`

Outside this folder:

* `~/gnuradio-3.8/share/gnuradio/grc/blocks/doa_qt_compass.block.yml` —
  rewritten for 3.8; the original used the Cheetah `#set` idiom that Mako
  rejects. The stale `.xml` and the auto-converted `.block.yml` in
  `~/.local/share` were renamed `.disabled` so they cannot shadow it.
* `~/gnuradio-3.8/setup_env.sh` — `~/.local/lib` added to `LD_LIBRARY_PATH`
  for Armadillo 12. Backup at `setup_env.sh.bak`.

## Rebuilding

There is no `build/` directory; the installed blocks in `~/gnuradio-3.8` are
unaffected by that. To rebuild:

    source ~/gnuradio-3.8/setup_env.sh
    cd ~/REPO/gr-doa && mkdir -p build && cd build
    cmake .. -DCMAKE_INSTALL_PREFIX=$HOME/gnuradio-3.8 \
             -DCMAKE_PREFIX_PATH="$HOME/gnuradio-3.8;$HOME/uhd-3.15;$HOME/.local" \
             -DARMADILLO_INCLUDE_DIR=$HOME/.local/include \
             -DARMADILLO_LIBRARY=$HOME/.local/lib/libarmadillo.so \
             -DENABLE_TESTING=OFF -DENABLE_DOXYGEN=OFF
    make -j$(nproc) && make install

## Check it still works

    source ~/gnuradio-3.8/setup_env.sh
    python3 -c "import doa; print(doa.MUSIC_lin_array, doa.twinrx_usrp_source)"
