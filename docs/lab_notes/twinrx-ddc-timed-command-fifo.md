# twinrx-ddc-timed-command-fifo

_Never give a DDC a command time on the X310 - its timed writes never execute, fill the FPGA command FIFO after ~72 hops and wedge the radio until a power cycle._

Diagnosed 2026-09-24 on the USRP-2945 (X310 `31082D8`, GR 3.8 + UHD 3.15). This was
the cause of the repeated power cycles, not a separate shutdown bug.

`set_command_time()` applies to **DDC blocks as well as radios** — a DDC subscribes to
`time/cmd` (`ddc_block_ctrl_impl.cpp:93`). A radio has a timekeeper, so its timed
commands execute and retire. **A DDC's time never advances**, so every timed write to
it is queued in the FPGA command FIFO and never retires.

The FIFO holds `CMD_FIFO_SIZE / MAX_CMD_PKT_SIZE` = 256/3 = **85 commands**.
Initialisation uses ~13, each hop strands one more, and at 85 the block stops
answering:

```
[0/DDC_0] sr_write() failed: Block ctrl (CE_03_Port_60) no response packet
```

After that every tune fails for the rest of the run, and **a fresh process inherits the
fault** — the full FIFO is in the FPGA, so only a power cycle clears it.

**Fix** (in `twinrx_usrp_source.set_center_freq`): stamp only the RF frontend.

```python
timed_req = uhd.tune_request(
    rf_freq=center_freq,
    rf_freq_policy=uhd.tune_request.POLICY_MANUAL,
    dsp_freq_policy=uhd.tune_request.POLICY_NONE)
```

The DSP frequency is still set, identically on all four channels, by the untimed pass
before it. Coherence is unaffected: the channels share one LO
([usrp-2945-twinrx-lo-sharing](usrp-2945-twinrx-lo-sharing.md)) and the timed pass exists to make the frontends take
effect on the same tick.

**Why:** the giveaway is that the failure point is a *count*, not a time — 70, 72 and 74
hops across three runs, unmoved by halving host CPU load, by fixing a Qt threading bug,
or by widening the command-time margin from 10 ms to 100 ms. Only `DDC_0` ever failed,
never a radio.

**How to apply:** test it in seconds, not the ~13 minutes a dwelling flowgraph needs —
the fault needs neither dwell, transmitter nor running stream, so
`guru/ddc_fifo_test.py` just tunes back to back. Result after the fix: 400 tunes clean
in 40 s (4.7x the old budget), then 866 hops in a live run with zero failures and the
device still healthy afterwards.
