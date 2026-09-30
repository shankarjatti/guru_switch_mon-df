# -*- coding: utf-8 -*-
#
# Copyright 2016
# Travis F. Collins <travisfcollins@gmail.com>
# Srikanth Pagadarai <srikanth.pagadarai@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from gnuradio import gr
from gnuradio import uhd
import time
from gnuradio.filter import firdes

def gen_sig_io(num_elements):
    # Dynamically create types for signature
    io = []
    for i in range(num_elements):
        io.append(gr.sizeof_gr_complex*1)
    io.append(gr.sizeof_float*num_elements)
    return io

class twinrx_usrp_source(gr.hier_block2):

    def __init__(self, samp_rate=1000000, center_freq=2400000000, gain=40, sources=4, addresses="addr=192.168.10.2", lo_export_direction="B", lo_lock_fallback=False,
                 cmd_time_margin=0.1):
        gr.hier_block2.__init__(
            self, "TwinRX USRP",
            gr.io_signature(0, 0, 0),
            gr.io_signaturev(sources, sources, gen_sig_io(sources)),
        )

        ##################################################
        # Parameters
        ##################################################
        self.samp_rate = samp_rate
        self.center_freq = center_freq
        self.gain = gain
        self.sources = sources
        self.addresses = addresses
        self.lo_export_direction = lo_export_direction
        # Off by default: the radio is never reconfigured behind the
        # caller's back. When the LO will not lock, say so and stop.
        self.lo_lock_fallback = bool(lo_lock_fallback)
        # How far ahead the timed tune is stamped. See set_center_freq for
        # why this is a deadline and what happens when a write misses it.
        self.cmd_time_margin = float(cmd_time_margin)
        # True while the LO is running on the side UHD did not plan for,
        # which mirrors the received spectrum.
        self.lo_fallback_active = False

        ##################################################
        # Blocks
        ##################################################
        self.uhd_usrp_source_0 = uhd.usrp_source(
                ",".join((self.addresses, "")),
                uhd.stream_args(
                        cpu_format="fc32",
                        channels=list(range(sources)),
                ),
        )

        self.uhd_usrp_source_0.set_clock_source('internal', 0)
        subdevs = 'A:0 A:1 B:0 B:1'.split(' ')
        self.uhd_usrp_source_0.set_subdev_spec(' '.join(subdevs[:sources]), 0)
        self.uhd_usrp_source_0.set_samp_rate(samp_rate)
        self.uhd_usrp_source_0.set_time_unknown_pps(uhd.time_spec())

        # The upstream block never selects an antenna, so every channel stays
        # on whatever UHD defaults to.  On a TwinRX the two ports of a board
        # are RX1 and RX2, and a channel left on the wrong one reads ~70x down
        # -- it looks like a dead channel.  Same mapping twinrx_lo_check.py uses:
        #   A:0 -> RX1, A:1 -> RX2, B:0 -> RX1, B:1 -> RX2
        for _ch in range(self.sources):
            self.uhd_usrp_source_0.set_antenna('RX1' if _ch % 2 == 0 else 'RX2', _ch)
        # Set channel specific settings
        for _ch in range(sources):
            self.uhd_usrp_source_0.set_gain(gain, _ch)
            self.uhd_usrp_source_0.set_auto_dc_offset(True, _ch)

        # --- LO routing -------------------------------------------------
        # Upstream hard-codes Rx A as the exporter (ch0 internal + export,
        # ch1 companion, ch2/ch3 external).  On THIS USRP-2945 the A->B MMCX
        # jumpers pass no LO, so that leaves ch2/ch3 without an oscillator and
        # they read ~70x down -- indistinguishable from dead channels.
        # Measured on hardware, twice: B->A works, A->B does not.
        #
        # lo_export_direction picks which board exports:
        #   'B' (default here) : ch2 internal + export, ch3 companion,
        #                        ch0/ch1 external   <- correct for this unit
        #   'A'                : the upstream arrangement
        #
        # Exports are cleared first because UHD refuses a state where two
        # channels export at once.
        if sources == 4:
            for _ch in range(sources):
                try:
                    self.uhd_usrp_source_0.set_lo_export_enabled(False, uhd.ALL_LOS, _ch)
                except Exception as e:
                    # Not fatal: a channel that never exported will refuse.
                    # Still said out loud, because LO routing is what decides
                    # whether channels 2 and 3 receive anything at all, and a
                    # silent failure here reads as two dead channels later.
                    print("[twinrx] clearing LO export on ch%d: %s" % (_ch, e))
            if self.lo_export_direction.upper() == 'A':
                _src = ['internal', 'companion', 'external', 'external']
                _exp = 0
            else:
                _src = ['external', 'external', 'internal', 'companion']
                _exp = 2
            for _ch in range(sources):
                self.uhd_usrp_source_0.set_lo_source(_src[_ch], uhd.ALL_LOS, _ch)
            self.uhd_usrp_source_0.set_lo_export_enabled(True, uhd.ALL_LOS, _exp)
        else:
            self.uhd_usrp_source_0.set_lo_export_enabled(True, uhd.ALL_LOS, 0)
            self.uhd_usrp_source_0.set_lo_source('internal', uhd.ALL_LOS, 0)
            self.uhd_usrp_source_0.set_lo_source('companion', uhd.ALL_LOS, 1)

        # Use timed commands to set frequencies
        self.set_center_freq(center_freq,sources)
  
        ##################################################
        # Connections
        ##################################################
        for source in range(sources):
            self.connect((self.uhd_usrp_source_0, source), (self, source))

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.uhd_usrp_source_0.set_samp_rate(self.samp_rate)

    def set_center_freq(self, center_freq, sources):
        # Tune all channels to the desired frequency
        tune_resp = self.uhd_usrp_source_0.set_center_freq(center_freq, 0)
        tune_req = uhd.tune_request(rf_freq=center_freq, rf_freq_policy=uhd.tune_request.POLICY_MANUAL, 
               dsp_freq=tune_resp.actual_dsp_freq, dsp_freq_policy=uhd.tune_request.POLICY_MANUAL)

        self.uhd_usrp_source_0.set_center_freq(tune_req, 1)
        if sources==4:
            self.uhd_usrp_source_0.set_center_freq(tune_req, 2)
            self.uhd_usrp_source_0.set_center_freq(tune_req, 3)

        # Synchronize the tuned channels.
        #
        # The margin below is a deadline, not a delay. Every one of the writes
        # that follows is stamped with this time, and the FPGA holds it in its
        # command FIFO until then. A write that arrives after its own timestamp
        # is late, and a late command is never acknowledged.
        #
        # That matters more than it looks, because of how UHD accounts for
        # acknowledgements. ctrl_iface lets CMD_FIFO_SIZE / MAX_CMD_PKT_SIZE =
        # 256/3 = 85 commands stay in flight unacknowledged, and only then
        # starts draining one acknowledgement per new command. From that point
        # a SINGLE missing acknowledgement starves the drain: the next write
        # waits the full 10 s timeout for a packet that will never arrive and
        # throws
        #
        #   Block ctrl (CE_03_Port_60) no response packet
        #
        # after which every tune on that block fails for the rest of the run.
        # There is no way to resynchronise it from the API; the process has to
        # be restarted.
        #
        # Measured here: with a 10 ms margin the failure arrived after 72 hops
        # in one run and about 70 in another -- a count, not a time, which is
        # what a per-command accumulation looks like rather than a leak or
        # overheating. 10 ms has to cover a device time round trip plus eight
        # register writes on a host that can be descheduled at any point in
        # between, and one overrun in a few hundred is enough.
        #
        # 100 ms costs nothing: it only postpones the retune, which already
        # sits inside a settle window, and it is one tenth of the settle.
        now = self.uhd_usrp_source_0.get_time_now()
        self.uhd_usrp_source_0.set_command_time(
            now + uhd.time_spec(self.cmd_time_margin))

        # The timed pass sets the RF frontend only -- POLICY_NONE keeps the
        # DDC out of it. This is not a refinement, it is what stops the radio
        # dying after about seventy hops.
        #
        # A DDC block subscribes to time/cmd like a radio does
        # (ddc_block_ctrl_impl.cpp:93), so a command time applies to it and
        # its writes are queued in the FPGA's command FIFO to execute when the
        # block's time reaches the stamp. A radio has a timekeeper, so its
        # timed commands execute and retire. The DDC's time never advances, so
        # its timed writes are queued and never execute, and never retire.
        #
        # The FIFO holds CMD_FIFO_SIZE / MAX_CMD_PKT_SIZE = 256/3 = 85
        # commands. Initialisation uses about thirteen, each hop strands one
        # more, and at eighty-five the block stops answering entirely:
        #
        #   [0/DDC_0] sr_write() failed: Block ctrl (CE_03_Port_60)
        #   no response packet
        #
        # Measured failure points: 70, 72 and 74 hops across three runs. A
        # count, not a time -- and unchanged by fixing host CPU load, a Qt
        # threading bug, or widening the command-time margin, none of which
        # touch the number of commands stranded per hop. It is also why only
        # DDC_0 ever fails and never a radio, why a fresh process inherits the
        # fault, and why only a power cycle clears it: the full FIFO is in the
        # FPGA, not the driver.
        #
        # Channel coherence does not need the DDC in the timed window. The
        # four channels share one LO, and the DSP frequency is already set
        # identically on all of them by the untimed pass above; what the timed
        # pass is for is making the frontends take effect on the same tick.
        timed_req = uhd.tune_request(
            rf_freq=center_freq,
            rf_freq_policy=uhd.tune_request.POLICY_MANUAL,
            dsp_freq_policy=uhd.tune_request.POLICY_NONE)

        self.uhd_usrp_source_0.set_center_freq(timed_req, 0)
        self.uhd_usrp_source_0.set_center_freq(timed_req, 1)
        if sources==4:
            self.uhd_usrp_source_0.set_center_freq(timed_req, 2)
            self.uhd_usrp_source_0.set_center_freq(timed_req, 3)

        self.uhd_usrp_source_0.clear_command_time()

        self._relock_lo(center_freq, sources)

    # TwinRX first IF; LO1 sits one IF away from the RF on either side.
    TWINRX_IF1 = 1.25e9

    def _relock_lo(self, center_freq, sources):
        self.lo_fallback_active = False
        """Fall back to low-side LO1 when UHD picks a high-side one that will
        not lock.

        Measured on this unit: retuning into roughly 5.00-5.14 GHz makes UHD
        ask for LO1 = RF + 1.25 GHz (6.35 GHz at 5.1 GHz), and the synthesiser
        never locks -- lo_locked stays False and no channel sees anything, even
        though the tune reports success and actual_rf equals the request.
        Low-side (RF - 1.25 GHz) locks immediately and gives full signal. The
        synthesiser covers 2.0-6.8 GHz, so the low-side frequency is well
        inside its range; this is a band-planning choice, not a hardware limit.

        Note the two sides invert the spectrum relative to each other, so a
        tone at +f appears at -f. That is common to all four channels, so
        inter-channel phase offsets are unaffected.
        """
        # The tunes above are issued as timed commands 10 ms ahead. Give them
        # time to execute first, or anything set here is simply overwritten.
        time.sleep(0.08)

        master = 0 if self.lo_export_direction.upper() == 'A' else 2
        try:
            if self.uhd_usrp_source_0.get_sensor('lo_locked', master).to_bool():
                return
        except Exception as e:
            print("[twinrx] cannot read lo_locked on ch%d: %s -- lock state "
                  "unknown" % (master, e))
            return

        if not self.lo_lock_fallback:
            print("[twinrx] LO1 DID NOT LOCK at %.4f GHz -- this band is not\n"
                  "         receiving. UHD asks for a high-side LO here that\n"
                  "         this synthesiser will not lock to. Low-side would\n"
                  "         work but inverts the spectrum and re-locks the LO,\n"
                  "         which puts a 180 degree step on the exporting\n"
                  "         channel -- so it is not done unless you ask for it\n"
                  "         with lo_lock_fallback=True."
                  % (center_freq / 1e9))
            return

        low_side = center_freq - self.TWINRX_IF1
        try:
            rng = self.uhd_usrp_source_0.get_lo_freq_range("LO1", master)
            if not (rng.start() <= low_side <= rng.stop()):
                print("[twinrx] LO1 unlocked at %.3f GHz and low-side %.3f GHz "
                      "is out of range -- cannot recover"
                      % (center_freq / 1e9, low_side / 1e9))
                return
        except Exception as e:
            print("[twinrx] cannot read the LO1 range (%s) -- trying the "
                  "low-side frequency anyway" % e)

        # Only the exporting channel. Its LO1 is what every other channel
        # actually runs on, so re-locking it moves them all together and any
        # phase step the synthesiser takes is common mode -- it cancels in the
        # inter-channel differences. Forcing LO1 on all four instead lets each
        # board lock independently, which showed up as 90 degree jumps in the
        # measured offsets.
        ok = None
        for _attempt in range(3):
            try:
                self.uhd_usrp_source_0.set_lo_freq(low_side, "LO1", master)
            except Exception as e:
                print("[twinrx] forcing LO1 low-side failed on attempt %d: %s"
                      % (_attempt + 1, e))
            time.sleep(0.15)
            # Re-assert the export: the master's own mixer path picked up a
            # 180 degree step on each re-lock while the exported copy did not.
            try:
                self.uhd_usrp_source_0.set_lo_export_enabled(True, uhd.ALL_LOS, master)
            except Exception as e:
                print("[twinrx] re-asserting LO export failed on attempt %d: %s"
                      % (_attempt + 1, e))
            time.sleep(0.05)
            try:
                ok = self.uhd_usrp_source_0.get_sensor('lo_locked', master).to_bool()
            except Exception:
                ok = None
            if ok:
                break
        self.lo_fallback_active = bool(ok)
        print("[twinrx] LO1 would not lock at %.3f GHz; FALLBACK forced "
              "low-side "
              "%.3f GHz (locked=%s)" % (center_freq / 1e9, low_side / 1e9, ok))

    def get_center_freq(self):
        return self.center_freq


    def get_gain(self):
        return self.gain

    def set_gain(self, gain):
        # Upstream refused to do anything here.  Applying gain live is fine on
        # a TwinRX and is wanted for a GUI slider, so push it to every channel.
        #
        # One caveat worth knowing: changing RX gain can shift the per-channel
        # phase by a small amount, so a calibration taken at one gain is not
        # strictly valid at another.  Re-measure the offsets after moving it.
        self.gain = gain
        for _ch in range(self.sources):
            self.uhd_usrp_source_0.set_gain(gain, _ch)
    def get_sources(self):
        return self.sources

    def set_sources(self, sources):
        self.sources = sources
