# environment

* `versions.txt` — OS, kernel, CPU, GNU Radio / UHD / compiler / numpy / PyQt versions, network
  link, kernel buffer sizes, real-time limit, CPU governor, USB devices — recorded when saved.
* `x310_uhd_usrp_probe.txt` — `uhd_usrp_probe` of the X310 (serial, FPGA, both TwinRX boards).
* `setup_env.sh` — `~/gnuradio-3.8/setup_env.sh`: puts GR 3.8 + UHD 3.15 first on every path.
  Source it before anything on the X310.
* `uhd-3.15_setup_env.sh` — `~/uhd-3.15/setup_env.sh`.
* `run_grc.sh` — opens GNU Radio Companion 3.8.

Not in versions.txt: the host needs `enp3s0` = 192.168.10.1/24 for the X310 at 192.168.10.2,
and `net.core.rmem_max` ≥ 33554432 for UHD's receive buffer.
