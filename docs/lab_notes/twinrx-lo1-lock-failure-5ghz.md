# twinrx-lo1-lock-failure-5ghz

_USRP-2945 cannot RETUNE into ~5.00-5.14 GHz: UHD picks a high-side LO1 the synthesiser never locks to. Low-side fallback recovers it, with one caveat._

Measured 2026-09-23 on the USRP-2945 (X310 `31082D8`, GR 3.8 + UHD 3.15), tone from a
HackRF One.

**The TwinRX first IF is 1.25 GHz**, so LO1 sits one IF either side of the RF:

| RF | LO1 | side | locks |
|---|---|---|---|
| 2.40 GHz | 3.650 GHz | high | yes |
| 5.10 GHz | 6.350 GHz | **high** | **no** |
| 5.15 GHz | 3.900 GHz | low | yes |
| 5.20 GHz | 3.950 GHz | low | yes |

Low-side at 5.1 GHz needs LO1 = 3.85 GHz, just under UHD's ~3.9 GHz band-plan floor, so
it flips to high-side 6.35 GHz — **where the synthesiser never locks**. `lo_locked` reads
False, no channel receives anything, yet the tune reports success and `actual_rf` equals
the request. The dead range is roughly **5.00–5.14 GHz** and only affects *retuning*: a
flowgraph started directly at 5.1 GHz works fine (66 dB), because the LO is set during
init rather than retuned into place.

It is a band-planning choice, not a hardware limit — LO1's range is 2.0–6.8 GHz and
`set_lo_freq(3.85e9, "LO1", ch)` locks instantly.

**Fix, now in `twinrx_usrp_source._relock_lo()`** (installed tree and `~/REPO`): after each
tune, check `lo_locked` on the exporting channel and fall back to `RF - 1.25 GHz` if clear.
Two things that are easy to get wrong:

- The block's tunes are **timed commands 10 ms ahead**, so the fallback must sleep first or
  it is silently overwritten.
- Force LO1 on the **exporting channel only**. Forcing all four lets each board lock
  independently — seen as 90° jumps in the inter-channel offsets.

**Why:** the two LO sides invert the spectrum relative to each other, so a tone sent at
+200 kHz arrives at **−169 kHz**. Any tone search must look both sides of DC.

**How to apply:** 5.1 GHz goes from nothing to 57.6 dB, with ch1−ch0 and ch3−ch0 repeating
to ~0.2°. **But ch2−ch0 still steps 180° on every re-lock** (ch2 is the channel being
forced; re-asserting the LO export does not settle it). So for fully coherent work prefer
**5.15 GHz or above**, which uses low-side naturally and needs no re-lock — all three pairs
then repeat within 0.7°. See [usrp-2945-twinrx-lo-sharing](usrp-2945-twinrx-lo-sharing.md) and
[twinrx-phase-drift-frequency-scaling](twinrx-phase-drift-frequency-scaling.md).

**RX gain:** 60 dB suits all three bands — most SNR on the weak ones, ~4.8 dB headroom at
2.4 GHz. At 70 dB the 2.4 GHz band clips and its SNR *falls* from 81 to 69 dB.
