# sdr-toolchain-isolated-env

_radar2 work uses an isolated GNU Radio 3.8 + UHD 3.15 env, not the system GR 3.10 / UHD 4.10 on PATH_

The default shell PATH on this machine has **GNU Radio 3.10.1.1 and UHD 4.10.0.0**,
but all radar2 / USRP-2945 work targets **GNU Radio 3.8.5.0 + UHD 3.15.0**, installed
side by side at `~/gnuradio-3.8` and `~/uhd-3.15`.

Always run `source ~/gnuradio-3.8/setup_env.sh` before any `python3`, `grcc`,
`gnuradio-companion`, `uhd_*` or flowgraph command. `~/gnuradio-3.8/run_grc.sh`
sources it and launches GRC in one step.

**Why:** version checks (`gnuradio-config-info -v`, `uhd_config_info --version`)
report the system toolchain and look like the user is mistaken about their versions.
They are not — they have both, and the 3.8/3.15 pair is the real target.

**How to apply:** prefix toolchain commands with the source line; do not "correct"
the user's stated versions based on what bare `PATH` reports. `gr-aoa` (the DF /
angle-of-arrival OOT from the Ettus TwinRX direction-finding app note) is installed
into the 3.8 tree only. See [usrp-2945-twinrx-lo-sharing](usrp-2945-twinrx-lo-sharing.md).
