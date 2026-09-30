#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Ch2/Ch3 Clean Signal - DC corrected + amplitude normalised (gr-doa reference)
# Author: shankar
# Description: TwinRX LO sharing / phase coherence test bench
# GNU Radio version: v3.8.5.0-6-g57bd109d

from distutils.version import StrictVersion

if __name__ == '__main__':
    import ctypes
    import sys
    if sys.platform.startswith('linux'):
        try:
            x11 = ctypes.cdll.LoadLibrary('libX11.so')
            x11.XInitThreads()
        except:
            print("Warning: failed to XInitThreads()")

from PyQt5 import Qt
from gnuradio import qtgui
from gnuradio.filter import firdes
import sip
from gnuradio import analog
from gnuradio import blocks
from gnuradio import filter
from gnuradio import gr
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
from gnuradio import uhd
import time
from gnuradio.qtgui import Range, RangeWidget

from gnuradio import qtgui

class chan23_clean(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "Ch2/Ch3 Clean Signal - DC corrected + amplitude normalised (gr-doa reference)")
        Qt.QWidget.__init__(self)
        self.setWindowTitle("Ch2/Ch3 Clean Signal - DC corrected + amplitude normalised (gr-doa reference)")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme('gnuradio-grc'))
        except:
            pass
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_layout.addLayout(self.top_grid_layout)

        self.settings = Qt.QSettings("GNU Radio", "chan23_clean")

        try:
            if StrictVersion(Qt.qVersion()) < StrictVersion("5.0.0"):
                self.restoreGeometry(self.settings.value("geometry").toByteArray())
            else:
                self.restoreGeometry(self.settings.value("geometry"))
        except:
            pass

        ##################################################
        # Variables
        ##################################################
        self.tone_offset = tone_offset = 200e3
        self.tone_bw = tone_bw = 10e3
        self.time_interp = time_interp = 20
        self.samp_rate = samp_rate = 1000000
        self.disp_bw = disp_bw = 20e3
        self.view_decim = view_decim = 2048
        self.tone_taps = tone_taps = firdes.low_pass(1.0, samp_rate, tone_bw, tone_bw/2.0, firdes.WIN_HAMMING)
        self.time_srate = time_srate = samp_rate * time_interp
        self.subdev = subdev = "A:0 A:1 B:0 B:1"
        self.lo_sources = lo_sources = ['external', 'external', 'internal', 'companion']
        self.lo_export_chan = lo_export_chan = 2
        self.gain = gain = 60
        self.dsp_manual = dsp_manual = True
        self.disp_taps_bp = disp_taps_bp = firdes.complex_band_pass(1.0, samp_rate, tone_offset - disp_bw/2, tone_offset + disp_bw/2, disp_bw/2, firdes.WIN_HAMMING)
        self.disp_taps = disp_taps = firdes.low_pass(1.0, samp_rate, disp_bw, disp_bw/2.0, firdes.WIN_HAMMING)
        self.cmd_lead = cmd_lead = 0.1
        self.center_freq = center_freq = 2.4e9
        self.avg_len = avg_len = 65536

        ##################################################
        # Blocks
        ##################################################
        self.tabs = Qt.QTabWidget()
        self.tabs_widget_0 = Qt.QWidget()
        self.tabs_layout_0 = Qt.QBoxLayout(Qt.QBoxLayout.TopToBottom, self.tabs_widget_0)
        self.tabs_grid_layout_0 = Qt.QGridLayout()
        self.tabs_layout_0.addLayout(self.tabs_grid_layout_0)
        self.tabs.addTab(self.tabs_widget_0, 'Control & Phase')
        self.tabs_widget_1 = Qt.QWidget()
        self.tabs_layout_1 = Qt.QBoxLayout(Qt.QBoxLayout.TopToBottom, self.tabs_widget_1)
        self.tabs_grid_layout_1 = Qt.QGridLayout()
        self.tabs_layout_1.addLayout(self.tabs_grid_layout_1)
        self.tabs.addTab(self.tabs_widget_1, 'Spectra')
        self.top_layout.addWidget(self.tabs)
        self._gain_range = Range(0, 93, 1, 60, 100)
        self._gain_win = RangeWidget(self._gain_range, self.set_gain, 'RX Gain (dB)', "counter_slider", float)
        self.tabs_grid_layout_0.addWidget(self._gain_win, 1, 0, 1, 1)
        for r in range(1, 2):
            self.tabs_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 1):
            self.tabs_grid_layout_0.setColumnStretch(c, 1)
        self._center_freq_range = Range(10e6, 6e9, 1e6, 2.4e9, 200)
        self._center_freq_win = RangeWidget(self._center_freq_range, self.set_center_freq, 'Center Freq (Hz)', "counter_slider", float)
        self.tabs_grid_layout_0.addWidget(self._center_freq_win, 0, 0, 1, 1)
        for r in range(0, 1):
            self.tabs_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 1):
            self.tabs_grid_layout_0.setColumnStretch(c, 1)
        self.uhd_usrp_source_0 = uhd.usrp_source(
            ",".join(("type=x300", "", "master_clock_rate=200e6")),
            uhd.stream_args(
                cpu_format="fc32",
                args='',
                channels=list(range(0,4)),
            ),
        )
        self.uhd_usrp_source_0.set_subdev_spec(subdev, 0)
        self.uhd_usrp_source_0.set_time_source('internal', 0)
        self.uhd_usrp_source_0.set_clock_source('internal', 0)
        self.uhd_usrp_source_0.set_center_freq(center_freq, 0)
        self.uhd_usrp_source_0.set_gain(gain, 0)
        self.uhd_usrp_source_0.set_antenna('RX1', 0)
        self.uhd_usrp_source_0.set_center_freq(center_freq, 1)
        self.uhd_usrp_source_0.set_gain(gain, 1)
        self.uhd_usrp_source_0.set_antenna('RX2', 1)
        self.uhd_usrp_source_0.set_center_freq(center_freq, 2)
        self.uhd_usrp_source_0.set_gain(gain, 2)
        self.uhd_usrp_source_0.set_antenna('RX1', 2)
        self.uhd_usrp_source_0.set_center_freq(center_freq, 3)
        self.uhd_usrp_source_0.set_gain(gain, 3)
        self.uhd_usrp_source_0.set_antenna('RX2', 3)
        self.uhd_usrp_source_0.set_clock_rate(200e6, uhd.ALL_MBOARDS)
        self.uhd_usrp_source_0.set_samp_rate(samp_rate)
        # No synchronization enforced.
        self.time_resamp_tx = filter.rational_resampler_ccc(
                interpolation=time_interp,
                decimation=1,
                taps=firdes.low_pass(time_interp * 10, time_srate, 300e3, 50e3, firdes.WIN_HAMMING),
                fractional_bw=0)
        self.time_resamp_3 = filter.rational_resampler_ccc(
                interpolation=time_interp,
                decimation=1,
                taps=[t * (0.691236+0.722629j) for t in firdes.low_pass(time_interp, time_srate, 300e3, 50e3, firdes.WIN_HAMMING)],
                fractional_bw=0)
        self.time_resamp_2 = filter.rational_resampler_ccc(
                interpolation=time_interp,
                decimation=1,
                taps=[t * (-0.470642-0.882324j) for t in firdes.low_pass(time_interp, time_srate, 300e3, 50e3, firdes.WIN_HAMMING)],
                fractional_bw=0)
        self.qtgui_time_sink_x_1 = qtgui.time_sink_f(
            1000, #size
            time_srate, #samp_rate
            "ch2 / ch3 — DC removed, amplitude locked to 0.1 (phase free to drift)", #name
            3 #number of inputs
        )
        self.qtgui_time_sink_x_1.set_update_time(0.10)
        self.qtgui_time_sink_x_1.set_y_axis(-0.05, 0.05)

        self.qtgui_time_sink_x_1.set_y_label('Amplitude', "")

        self.qtgui_time_sink_x_1.enable_tags(True)
        self.qtgui_time_sink_x_1.set_trigger_mode(qtgui.TRIG_MODE_AUTO, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.qtgui_time_sink_x_1.enable_autoscale(True)
        self.qtgui_time_sink_x_1.enable_grid(True)
        self.qtgui_time_sink_x_1.enable_axis_labels(True)
        self.qtgui_time_sink_x_1.enable_control_panel(True)
        self.qtgui_time_sink_x_1.enable_stem_plot(False)


        labels = ['Ch2 RF B/RX1', 'Ch3 RF B/RX2', 'TX Signal (B210)', 'Signal4', 'Signal5',
            'Signal6', 'Signal7', 'Signal8', 'Signal9', 'Signal10']
        widths = [2, 2, 2, 1, 1,
            1, 1, 1, 1, 1]
        colors = ['green', 'magenta', 'black', 'magenta', 'black',
            'cyan', 'dark red', 'dark green', 'dark blue', 'dark blue']
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(3):
            if len(labels[i]) == 0:
                self.qtgui_time_sink_x_1.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_time_sink_x_1.set_line_label(i, labels[i])
            self.qtgui_time_sink_x_1.set_line_width(i, widths[i])
            self.qtgui_time_sink_x_1.set_line_color(i, colors[i])
            self.qtgui_time_sink_x_1.set_line_style(i, styles[i])
            self.qtgui_time_sink_x_1.set_line_marker(i, markers[i])
            self.qtgui_time_sink_x_1.set_line_alpha(i, alphas[i])

        self._qtgui_time_sink_x_1_win = sip.wrapinstance(self.qtgui_time_sink_x_1.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_0.addWidget(self._qtgui_time_sink_x_1_win, 6, 0, 1, 2)
        for r in range(6, 7):
            self.tabs_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 2):
            self.tabs_grid_layout_0.setColumnStretch(c, 1)
        self.null_1 = blocks.null_sink(gr.sizeof_gr_complex*1)
        self.null_0 = blocks.null_sink(gr.sizeof_gr_complex*1)
        self.dcblock_3 = filter.dc_blocker_cc(1024, True)
        self.dcblock_2 = filter.dc_blocker_cc(1024, True)
        self.c2r_tx = blocks.complex_to_real(1)
        self.c2r_3 = blocks.complex_to_real(1)
        self.c2r_2 = blocks.complex_to_real(1)
        self.bp_3 = filter.fir_filter_ccc(1, disp_taps_bp)
        self.bp_3.declare_sample_delay(0)
        self.bp_2 = filter.fir_filter_ccc(1, disp_taps_bp)
        self.bp_2.declare_sample_delay(0)
        self.analog_sig_source_x_0 = analog.sig_source_c(samp_rate, analog.GR_COS_WAVE, tone_offset, 0.02, 0, 0)
        self.agc_3 = analog.agc2_cc(0.5, 0.5, 0.1, 100.0)
        self.agc_3.set_max_gain(1e6)
        self.agc_2 = analog.agc2_cc(0.5, 0.5, 0.1, 100.0)
        self.agc_2.set_max_gain(1e6)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.agc_2, 0), (self.time_resamp_2, 0))
        self.connect((self.agc_3, 0), (self.time_resamp_3, 0))
        self.connect((self.analog_sig_source_x_0, 0), (self.time_resamp_tx, 0))
        self.connect((self.bp_2, 0), (self.agc_2, 0))
        self.connect((self.bp_3, 0), (self.agc_3, 0))
        self.connect((self.c2r_2, 0), (self.qtgui_time_sink_x_1, 0))
        self.connect((self.c2r_3, 0), (self.qtgui_time_sink_x_1, 1))
        self.connect((self.c2r_tx, 0), (self.qtgui_time_sink_x_1, 2))
        self.connect((self.dcblock_2, 0), (self.bp_2, 0))
        self.connect((self.dcblock_3, 0), (self.bp_3, 0))
        self.connect((self.time_resamp_2, 0), (self.c2r_2, 0))
        self.connect((self.time_resamp_3, 0), (self.c2r_3, 0))
        self.connect((self.time_resamp_tx, 0), (self.c2r_tx, 0))
        self.connect((self.uhd_usrp_source_0, 2), (self.dcblock_2, 0))
        self.connect((self.uhd_usrp_source_0, 3), (self.dcblock_3, 0))
        self.connect((self.uhd_usrp_source_0, 0), (self.null_0, 0))
        self.connect((self.uhd_usrp_source_0, 1), (self.null_1, 0))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("GNU Radio", "chan23_clean")
        self.settings.setValue("geometry", self.saveGeometry())
        event.accept()

    def get_tone_offset(self):
        return self.tone_offset

    def set_tone_offset(self, tone_offset):
        self.tone_offset = tone_offset
        self.analog_sig_source_x_0.set_frequency(self.tone_offset)
        self.set_disp_taps_bp(firdes.complex_band_pass(1.0, self.samp_rate, self.tone_offset - self.disp_bw/2, self.tone_offset + self.disp_bw/2, self.disp_bw/2, firdes.WIN_HAMMING))

    def get_tone_bw(self):
        return self.tone_bw

    def set_tone_bw(self, tone_bw):
        self.tone_bw = tone_bw
        self.set_tone_taps(firdes.low_pass(1.0, self.samp_rate, self.tone_bw, self.tone_bw/2.0, firdes.WIN_HAMMING))

    def get_time_interp(self):
        return self.time_interp

    def set_time_interp(self, time_interp):
        self.time_interp = time_interp
        self.set_time_srate(self.samp_rate * self.time_interp)
        self.time_resamp_2.set_taps([t * (-0.470642-0.882324j) for t in firdes.low_pass(self.time_interp, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING)])
        self.time_resamp_3.set_taps([t * (0.691236+0.722629j) for t in firdes.low_pass(self.time_interp, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING)])
        self.time_resamp_tx.set_taps(firdes.low_pass(self.time_interp * 10, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING))

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_time_srate(self.samp_rate * self.time_interp)
        self.set_tone_taps(firdes.low_pass(1.0, self.samp_rate, self.tone_bw, self.tone_bw/2.0, firdes.WIN_HAMMING))
        self.analog_sig_source_x_0.set_sampling_freq(self.samp_rate)
        self.uhd_usrp_source_0.set_samp_rate(self.samp_rate)
        self.set_disp_taps(firdes.low_pass(1.0, self.samp_rate, self.disp_bw, self.disp_bw/2.0, firdes.WIN_HAMMING))
        self.set_disp_taps_bp(firdes.complex_band_pass(1.0, self.samp_rate, self.tone_offset - self.disp_bw/2, self.tone_offset + self.disp_bw/2, self.disp_bw/2, firdes.WIN_HAMMING))

    def get_disp_bw(self):
        return self.disp_bw

    def set_disp_bw(self, disp_bw):
        self.disp_bw = disp_bw
        self.set_disp_taps(firdes.low_pass(1.0, self.samp_rate, self.disp_bw, self.disp_bw/2.0, firdes.WIN_HAMMING))
        self.set_disp_taps_bp(firdes.complex_band_pass(1.0, self.samp_rate, self.tone_offset - self.disp_bw/2, self.tone_offset + self.disp_bw/2, self.disp_bw/2, firdes.WIN_HAMMING))

    def get_view_decim(self):
        return self.view_decim

    def set_view_decim(self, view_decim):
        self.view_decim = view_decim

    def get_tone_taps(self):
        return self.tone_taps

    def set_tone_taps(self, tone_taps):
        self.tone_taps = tone_taps

    def get_time_srate(self):
        return self.time_srate

    def set_time_srate(self, time_srate):
        self.time_srate = time_srate
        self.qtgui_time_sink_x_1.set_samp_rate(self.time_srate)
        self.time_resamp_2.set_taps([t * (-0.470642-0.882324j) for t in firdes.low_pass(self.time_interp, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING)])
        self.time_resamp_3.set_taps([t * (0.691236+0.722629j) for t in firdes.low_pass(self.time_interp, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING)])
        self.time_resamp_tx.set_taps(firdes.low_pass(self.time_interp * 10, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING))

    def get_subdev(self):
        return self.subdev

    def set_subdev(self, subdev):
        self.subdev = subdev

    def get_lo_sources(self):
        return self.lo_sources

    def set_lo_sources(self, lo_sources):
        self.lo_sources = lo_sources

    def get_lo_export_chan(self):
        return self.lo_export_chan

    def set_lo_export_chan(self, lo_export_chan):
        self.lo_export_chan = lo_export_chan

    def get_gain(self):
        return self.gain

    def set_gain(self, gain):
        self.gain = gain
        self.uhd_usrp_source_0.set_gain(self.gain, 0)
        self.uhd_usrp_source_0.set_gain(self.gain, 1)
        self.uhd_usrp_source_0.set_gain(self.gain, 2)
        self.uhd_usrp_source_0.set_gain(self.gain, 3)

    def get_dsp_manual(self):
        return self.dsp_manual

    def set_dsp_manual(self, dsp_manual):
        self.dsp_manual = dsp_manual

    def get_disp_taps_bp(self):
        return self.disp_taps_bp

    def set_disp_taps_bp(self, disp_taps_bp):
        self.disp_taps_bp = disp_taps_bp
        self.bp_2.set_taps(self.disp_taps_bp)
        self.bp_3.set_taps(self.disp_taps_bp)

    def get_disp_taps(self):
        return self.disp_taps

    def set_disp_taps(self, disp_taps):
        self.disp_taps = disp_taps

    def get_cmd_lead(self):
        return self.cmd_lead

    def set_cmd_lead(self, cmd_lead):
        self.cmd_lead = cmd_lead

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.uhd_usrp_source_0.set_center_freq(self.center_freq, 0)
        self.uhd_usrp_source_0.set_center_freq(self.center_freq, 1)
        self.uhd_usrp_source_0.set_center_freq(self.center_freq, 2)
        self.uhd_usrp_source_0.set_center_freq(self.center_freq, 3)

    def get_avg_len(self):
        return self.avg_len

    def set_avg_len(self, avg_len):
        self.avg_len = avg_len

def snipfcn_snippet_lo_config(self):
    # =================================================================
    # TwinRX / USRP-2945  --  LO ROUTING + COHERENT TIMED TUNE
    # Runs AFTER the blocks are built, BEFORE the flowgraph starts.
    # =================================================================
    import time
    from gnuradio import uhd as _uhd

    _u = self.uhd_usrp_source_0
    _nch = 4
    _lo_src = list(self.lo_sources)
    _exp_ch = int(self.lo_export_chan)

    print('')
    print('=== TwinRX LO configuration =====================================')
    print('  subdev spec      : %s' % _u.get_subdev_spec(0))
    print('  LO names         : %s' % list(_u.get_lo_names(0)))
    print('  LO sources avail : %s' % list(_u.get_lo_sources(_uhd.ALL_LOS, 0)))

    # --- Step 1: drop every export first.  UHD refuses a state where two
    #             channels export at once, so clear before we re-assert.
    for _ch in range(_nch):
        _u.set_lo_export_enabled(False, _uhd.ALL_LOS, _ch)

    # --- Step 2: program the source of every channel.
    #     'internal'  : this channel's own synth drives it
    #     'companion' : takes the other channel's synth, same daughterboard
    #     'external'  : takes the LO IN connectors (J4=LO1, J2=LO2)
    #     'reimport'  : own synth, exported AND looped back in through LO IN
    #                   (use when a splitter feeds the master's own LO IN,
    #                    so both boards see identical cable delay)
    for _ch in range(_nch):
        _u.set_lo_source(_lo_src[_ch], _uhd.ALL_LOS, _ch)

    # --- Step 3: exactly one exporter.  Never 'external' + export.
    _u.set_lo_export_enabled(True, _uhd.ALL_LOS, _exp_ch)

    for _ch in range(_nch):
        print('  ch%d  requested=%-10s readback=%-10s export=%s'
              % (_ch, _lo_src[_ch],
                 _u.get_lo_source(_uhd.ALL_LOS, _ch),
                 _u.get_lo_export_enabled(_uhd.ALL_LOS, _ch)))

    # --- Hardware DC-offset correction, as gr-doa's
    #     twinrx_usrp_source.py does on every channel.
    for _ch in range(_nch):
        _u.set_auto_dc_offset(True, _ch)

    # --- Step 4: a known device time so timed commands mean something.
    _u.set_time_now(_uhd.time_spec(0.0), 0)


    def _twinrx_tune(freq):
        """Tune all channels on the SAME clock edge.

        Why twice:  a cold TwinRX tune needs more SPI transactions than
        the X310 command FIFO (16 deep) can hold, so part of the first
        burst executes untimed.  The driver caches band/filter/synth
        state, so the second, identical burst is short enough to fit and
        lands atomically on all four channels.
        """
        _tr = _uhd.tune_request(float(freq))
        if bool(self.dsp_manual):
            # Pin every DDC to 0 Hz -> the digital stage contributes no
            # per-channel phase, only the shared LO does.
            _tr.rf_freq_policy  = _uhd.tune_request.POLICY_AUTO
            _tr.dsp_freq_policy = _uhd.tune_request.POLICY_MANUAL
            _tr.dsp_freq        = 0.0
        _lead = float(self.cmd_lead)
        for _pass in range(2):
            _u.set_command_time(_u.get_time_now(0) + _uhd.time_spec(_lead), 0)
            for _ch in range(_nch):
                _u.set_center_freq(_tr, _ch)
            _u.clear_command_time(0)
            time.sleep(_lead + 0.05)
        print('  tuned -> %.6f MHz   (ch0 actual %.6f MHz)'
              % (float(freq) / 1e6, _u.get_center_freq(0) / 1e6))


    self.twinrx_tune = _twinrx_tune
    self.twinrx_tune(float(self.center_freq))
    import subprocess, os
    if subprocess.run(['pgrep', '-f', 'b210_tone_source.py'], stdout=subprocess.DEVNULL).returncode != 0:
        print('[*] Starting B210 calibration source in background...')
        _b210_env = dict(os.environ)
        _b210_env.pop('UHD315_DIR', None)
        _b210_env.pop('GR38_DIR', None)
        _b210_env['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
        self._b210_proc = subprocess.Popen(['python3', '-u', '/home/shankar/radar2/b210_tone_source.py', '--freq', str(self.center_freq), '--gain', '55', '--pad', '30'], env=_b210_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
    print('=================================================================')
    print('')

def snipfcn_snippet_lo_stop(self):
    self._twinrx_run = False
    if hasattr(self, '_b210_proc') and self._b210_proc:
        try:
            self._b210_proc.terminate()
        except Exception:
            pass
    print('LO watcher stopped.')

def snipfcn_snippet_lo_watch(self):
    # Watch the Center Freq slider and redo the FULL coherent tune
    # sequence whenever it moves.  A plain GRC callback would call
    # set_center_freq() per channel, untimed, and break coherence.
    import time
    import threading

    self._twinrx_run = True


    def _twinrx_watch():
        _last = float(self.center_freq)
        while self._twinrx_run:
            _f = float(self.center_freq)
            if _f != _last:
                _last = _f
                try:
                    self.twinrx_tune(_f)
                except Exception as _e:
                    print('coherent retune failed: %s' % _e)
            time.sleep(0.2)


    self._twinrx_thread = threading.Thread(target=_twinrx_watch)
    self._twinrx_thread.daemon = True
    self._twinrx_thread.start()
    print('LO watcher running - move the Center Freq slider to retune coherently.')


def snippets_main_after_init(tb):
    snipfcn_snippet_lo_config(tb)

def snippets_main_after_start(tb):
    snipfcn_snippet_lo_watch(tb)

def snippets_main_after_stop(tb):
    snipfcn_snippet_lo_stop(tb)




def main(top_block_cls=chan23_clean, options=None):

    if StrictVersion("4.5.0") <= StrictVersion(Qt.qVersion()) < StrictVersion("5.0.0"):
        style = gr.prefs().get_string('qtgui', 'style', 'raster')
        Qt.QApplication.setGraphicsSystem(style)
    qapp = Qt.QApplication(sys.argv)

    tb = top_block_cls()
    snippets_main_after_init(tb)
    tb.start()
    snippets_main_after_start(tb)
    tb.show()

    def sig_handler(sig=None, frame=None):
        Qt.QApplication.quit()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    timer = Qt.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    def quitting():
        tb.stop()
        tb.wait()
        snippets_main_after_stop(tb)
    qapp.aboutToQuit.connect(quitting)
    qapp.exec_()

if __name__ == '__main__':
    main()
