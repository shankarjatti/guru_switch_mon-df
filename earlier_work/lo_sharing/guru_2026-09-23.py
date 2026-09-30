#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Guru: USRP-2945 4-Channel Coherent Receiver & Phase Alignment
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
from gnuradio import eng_notation
from gnuradio import qtgui
from gnuradio.filter import firdes
import sip
from gnuradio import blocks
from gnuradio import filter
from gnuradio import gr
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio.qtgui import Range, RangeWidget
import doa

from gnuradio import qtgui

class guru(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "Guru: USRP-2945 4-Channel Coherent Receiver & Phase Alignment")
        Qt.QWidget.__init__(self)
        self.setWindowTitle("Guru: USRP-2945 4-Channel Coherent Receiver & Phase Alignment")
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

        self.settings = Qt.QSettings("GNU Radio", "guru")

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
        self.disp_bw = disp_bw = 300e3
        self.center_freq = center_freq = 2.4e9
        self.view_decim = view_decim = 2048
        self.tx_disp_gain = tx_disp_gain = 10
        self.tx_control = tx_control = '127.0.0.1:5123'
        self.tone_taps = tone_taps = firdes.low_pass(1.0, samp_rate, tone_bw, tone_bw/2.0, firdes.WIN_HAMMING)
        self.time_srate = time_srate = samp_rate * time_interp
        self.subdev = subdev = "A:0 A:1 B:0 B:1"
        self.ph_skip = ph_skip = 2**13
        self.ph_avg = ph_avg = 16384
        self.lo_sources = lo_sources = ['external', 'external', 'internal', 'companion']
        self.lo_export_chan = lo_export_chan = 2
        self.gain = gain = 60
        self.dsp_manual = dsp_manual = True
        self.disp_taps_bp = disp_taps_bp = firdes.complex_band_pass(1.0, samp_rate, tone_offset - disp_bw/2, tone_offset + disp_bw/2, disp_bw/4, firdes.WIN_HAMMING)
        self.disp_gain = disp_gain = 25
        self.cmd_lead = cmd_lead = 0.1
        self.band = band = '%.4f GHz' % (center_freq/1e9)
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
        self.twinrx_hopping_source_0 = doa.twinrx_hopping_source(
            samp_rate=1000000,
            sources=4,
            addresses="type=x300",
            lo_export_direction="B",
            cpu_format="fc32",
            otw_format="",
            bands=[
                (2400000000, 46, 10.0),
                (5200000000, 60, 10.0),
                (5800000000, 69, 10.0),
            ],
            settle=1.0,
            hop_enable=True,
            tx_control="127.0.0.1:5123",
            blank_during_settle=False,
            lo_lock_fallback=False,
            gain_trim=(0.0, -13.3, 1.5, -1.7),
            start_delay=2.0,
        )
        self.time_resamp_3 = filter.rational_resampler_ccc(
                interpolation=time_interp,
                decimation=1,
                taps=firdes.low_pass(time_interp * disp_gain, time_srate, 300e3, 50e3, firdes.WIN_HAMMING),
                fractional_bw=0)
        self.time_resamp_2 = filter.rational_resampler_ccc(
                interpolation=time_interp,
                decimation=1,
                taps=firdes.low_pass(time_interp * disp_gain, time_srate, 300e3, 50e3, firdes.WIN_HAMMING),
                fractional_bw=0)
        self.time_resamp_1 = filter.rational_resampler_ccc(
                interpolation=time_interp,
                decimation=1,
                taps=firdes.low_pass(time_interp * disp_gain, time_srate, 300e3, 50e3, firdes.WIN_HAMMING),
                fractional_bw=0)
        self.time_resamp_0 = filter.rational_resampler_ccc(
                interpolation=time_interp,
                decimation=1,
                taps=firdes.low_pass(time_interp * disp_gain, time_srate, 300e3, 50e3, firdes.WIN_HAMMING),
                fractional_bw=0)
        self.spec_gate_3 = blocks.multiply_const_cc(0)
        self.spec_gate_2 = blocks.multiply_const_cc(0)
        self.spec_gate_1 = blocks.multiply_const_cc(0)
        self.spec_gate_0 = blocks.multiply_const_cc(0)
        self.qtgui_time_sink_x_1 = qtgui.time_sink_f(
            1000, #size
            time_srate, #samp_rate
            "RF Waveforms - all 4 channels: DC removed, tone filtered, uniform gain", #name
            4 #number of inputs
        )
        self.qtgui_time_sink_x_1.set_update_time(0.10)
        self.qtgui_time_sink_x_1.set_y_axis(-0.6, 0.6)

        self.qtgui_time_sink_x_1.set_y_label('Amplitude', "")

        self.qtgui_time_sink_x_1.enable_tags(True)
        self.qtgui_time_sink_x_1.set_trigger_mode(qtgui.TRIG_MODE_AUTO, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.qtgui_time_sink_x_1.enable_autoscale(False)
        self.qtgui_time_sink_x_1.enable_grid(True)
        self.qtgui_time_sink_x_1.enable_axis_labels(True)
        self.qtgui_time_sink_x_1.enable_control_panel(True)
        self.qtgui_time_sink_x_1.enable_stem_plot(False)


        labels = ['Ch0 RF A/RX2 - LO external', 'Ch1 RF A/RX1 - LO external', 'Ch2 RF B/RX1 - LO internal (MASTER, exports)', 'Ch3 RF B/RX2 - LO companion', 'TX Signal (B210)',
            'Signal6', 'Signal7', 'Signal8', 'Signal9', 'Signal10']
        widths = [2, 2, 2, 2, 2,
            1, 1, 1, 1, 1]
        colors = ['red', 'blue', 'green', 'magenta', 'black',
            'cyan', 'dark red', 'dark green', 'dark blue', 'dark blue']
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(4):
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
        self.qtgui_freq_sink_x_0 = qtgui.freq_sink_c(
            4096, #size
            firdes.WIN_BLACKMAN_hARRIS, #wintype
            center_freq, #fc
            samp_rate, #bw
            "Spectrum - all 4 channels (DC removed)", #name
            4
        )
        self.qtgui_freq_sink_x_0.set_update_time(0.10)
        self.qtgui_freq_sink_x_0.set_y_axis(-140, -20)
        self.qtgui_freq_sink_x_0.set_y_label('Relative Gain', 'dB')
        self.qtgui_freq_sink_x_0.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.qtgui_freq_sink_x_0.enable_autoscale(False)
        self.qtgui_freq_sink_x_0.enable_grid(True)
        self.qtgui_freq_sink_x_0.set_fft_average(0.2)
        self.qtgui_freq_sink_x_0.enable_axis_labels(True)
        self.qtgui_freq_sink_x_0.enable_control_panel(False)



        labels = ['Ch0 RF A/RX1', 'Ch1 RF A/RX2', 'Ch2 RF B/RX1 (LO master)', 'Ch3 RF B/RX2', '',
            '', '', '', '', '']
        widths = [2, 2, 2, 2, 2,
            2, 2, 2, 2, 2]
        colors = ["blue", "red", "green", "black", "blue",
            "blue", "blue", "blue", "blue", "blue"]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(4):
            if len(labels[i]) == 0:
                self.qtgui_freq_sink_x_0.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_freq_sink_x_0.set_line_label(i, labels[i])
            self.qtgui_freq_sink_x_0.set_line_width(i, widths[i])
            self.qtgui_freq_sink_x_0.set_line_color(i, colors[i])
            self.qtgui_freq_sink_x_0.set_line_alpha(i, alphas[i])

        self._qtgui_freq_sink_x_0_win = sip.wrapinstance(self.qtgui_freq_sink_x_0.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_1.addWidget(self._qtgui_freq_sink_x_0_win, 0, 0, 1, 2)
        for r in range(0, 1):
            self.tabs_grid_layout_1.setRowStretch(r, 1)
        for c in range(0, 2):
            self.tabs_grid_layout_1.setColumnStretch(c, 1)
        self.ph_num_2_0 = qtgui.number_sink(
            gr.sizeof_float,
            0,
            qtgui.NUM_GRAPH_HORIZ,
            1
        )
        self.ph_num_2_0.set_update_time(0.20)
        self.ph_num_2_0.set_title("ch3 - ch0   phase offset (deg)")

        labels = ['ch3 - ch0', '', '', '', '',
            '', '', '', '', '']
        units = ['deg', '', '', '', '',
            '', '', '', '', '']
        colors = [("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"),
            ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black")]
        factor = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]

        for i in range(1):
            self.ph_num_2_0.set_min(i, -180)
            self.ph_num_2_0.set_max(i, 180)
            self.ph_num_2_0.set_color(i, colors[i][0], colors[i][1])
            if len(labels[i]) == 0:
                self.ph_num_2_0.set_label(i, "Data {0}".format(i))
            else:
                self.ph_num_2_0.set_label(i, labels[i])
            self.ph_num_2_0.set_unit(i, units[i])
            self.ph_num_2_0.set_factor(i, factor[i])

        self.ph_num_2_0.enable_autoscale(False)
        self._ph_num_2_0_win = sip.wrapinstance(self.ph_num_2_0.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_0.addWidget(self._ph_num_2_0_win, 10, 1, 1, 1)
        for r in range(10, 11):
            self.tabs_grid_layout_0.setRowStretch(r, 1)
        for c in range(1, 2):
            self.tabs_grid_layout_0.setColumnStretch(c, 1)
        self.ph_num_2 = qtgui.number_sink(
            gr.sizeof_float,
            0,
            qtgui.NUM_GRAPH_HORIZ,
            1
        )
        self.ph_num_2.set_update_time(0.20)
        self.ph_num_2.set_title("ch2- ch0   phase offset (deg)")

        labels = ['ch2 - ch0', '', '', '', '',
            '', '', '', '', '']
        units = ['deg', '', '', '', '',
            '', '', '', '', '']
        colors = [("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"),
            ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black")]
        factor = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]

        for i in range(1):
            self.ph_num_2.set_min(i, -180)
            self.ph_num_2.set_max(i, 180)
            self.ph_num_2.set_color(i, colors[i][0], colors[i][1])
            if len(labels[i]) == 0:
                self.ph_num_2.set_label(i, "Data {0}".format(i))
            else:
                self.ph_num_2.set_label(i, labels[i])
            self.ph_num_2.set_unit(i, units[i])
            self.ph_num_2.set_factor(i, factor[i])

        self.ph_num_2.enable_autoscale(False)
        self._ph_num_2_win = sip.wrapinstance(self.ph_num_2.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_0.addWidget(self._ph_num_2_win, 9, 1, 1, 1)
        for r in range(9, 10):
            self.tabs_grid_layout_0.setRowStretch(r, 1)
        for c in range(1, 2):
            self.tabs_grid_layout_0.setColumnStretch(c, 1)
        self.ph_num_1 = qtgui.number_sink(
            gr.sizeof_float,
            0,
            qtgui.NUM_GRAPH_HORIZ,
            1
        )
        self.ph_num_1.set_update_time(0.20)
        self.ph_num_1.set_title("ch1 - ch0   phase offset (deg)")

        labels = ['ch1 - ch0', '', '', '', '',
            '', '', '', '', '']
        units = ['deg', '', '', '', '',
            '', '', '', '', '']
        colors = [("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"),
            ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black")]
        factor = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]

        for i in range(1):
            self.ph_num_1.set_min(i, -180)
            self.ph_num_1.set_max(i, 180)
            self.ph_num_1.set_color(i, colors[i][0], colors[i][1])
            if len(labels[i]) == 0:
                self.ph_num_1.set_label(i, "Data {0}".format(i))
            else:
                self.ph_num_1.set_label(i, labels[i])
            self.ph_num_1.set_unit(i, units[i])
            self.ph_num_1.set_factor(i, factor[i])

        self.ph_num_1.enable_autoscale(False)
        self._ph_num_1_win = sip.wrapinstance(self.ph_num_1.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_0.addWidget(self._ph_num_1_win, 8, 1, 1, 1)
        for r in range(8, 9):
            self.tabs_grid_layout_0.setRowStretch(r, 1)
        for c in range(1, 2):
            self.tabs_grid_layout_0.setColumnStretch(c, 1)
        self.ph_num_0 = qtgui.number_sink(
            gr.sizeof_float,
            0,
            qtgui.NUM_GRAPH_HORIZ,
            1
        )
        self.ph_num_0.set_update_time(0.20)
        self.ph_num_0.set_title("ch0 - ch0   phase offset (deg)")

        labels = ['ch0 - ch0', '', '', '', '',
            '', '', '', '', '']
        units = ['deg', '', '', '', '',
            '', '', '', '', '']
        colors = [("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"),
            ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black"), ("black", "black")]
        factor = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]

        for i in range(1):
            self.ph_num_0.set_min(i, -180)
            self.ph_num_0.set_max(i, 180)
            self.ph_num_0.set_color(i, colors[i][0], colors[i][1])
            if len(labels[i]) == 0:
                self.ph_num_0.set_label(i, "Data {0}".format(i))
            else:
                self.ph_num_0.set_label(i, labels[i])
            self.ph_num_0.set_unit(i, units[i])
            self.ph_num_0.set_factor(i, factor[i])

        self.ph_num_0.enable_autoscale(False)
        self._ph_num_0_win = sip.wrapinstance(self.ph_num_0.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_0.addWidget(self._ph_num_0_win, 7, 1, 1, 1)
        for r in range(7, 8):
            self.tabs_grid_layout_0.setRowStretch(r, 1)
        for c in range(1, 2):
            self.tabs_grid_layout_0.setColumnStretch(c, 1)
        self.ph_est = doa.twinrx_phase_offset_est(5, ph_skip)
        self.ph_deg_2_0 = blocks.multiply_const_ff(57.29577951308232)
        self.ph_deg_2 = blocks.multiply_const_ff(57.29577951308232)
        self.ph_deg_1 = blocks.multiply_const_ff(57.29577951308232)
        self.ph_deg_0 = blocks.multiply_const_ff(57.29577951308232)
        self.ph_dec_2_0 = blocks.keep_one_in_n(gr.sizeof_float*1, 50000)
        self.ph_dec_2 = blocks.keep_one_in_n(gr.sizeof_float*1, 50000)
        self.ph_dec_1 = blocks.keep_one_in_n(gr.sizeof_float*1, 50000)
        self.ph_dec_0 = blocks.keep_one_in_n(gr.sizeof_float*1, 50000)
        self.ph_avg_2_0 = blocks.moving_average_ff(ph_avg, 1.0/ph_avg, 65536, 1)
        self.ph_avg_2 = blocks.moving_average_ff(ph_avg, 1.0/ph_avg, 65536, 1)
        self.ph_avg_1 = blocks.moving_average_ff(ph_avg, 1.0/ph_avg, 65536, 1)
        self.ph_avg_0 = blocks.moving_average_ff(ph_avg, 1.0/ph_avg, 65536, 1)
        self._gain_range = Range(0, 93, 1, 60, 100)
        self._gain_win = RangeWidget(self._gain_range, self.set_gain, 'RX Gain (dB)', "counter_slider", float)
        self.tabs_grid_layout_0.addWidget(self._gain_win, 1, 0, 1, 2)
        for r in range(1, 2):
            self.tabs_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 2):
            self.tabs_grid_layout_0.setColumnStretch(c, 1)
        self.disp_gate_3 = blocks.multiply_const_cc(0)
        self.disp_gate_2 = blocks.multiply_const_cc(0)
        self.disp_gate_1 = blocks.multiply_const_cc(0)
        self.disp_gate_0 = blocks.multiply_const_cc(0)
        self.dcblock_3 = filter.dc_blocker_cc(1024, True)
        self.dcblock_2 = filter.dc_blocker_cc(1024, True)
        self.dcblock_1 = filter.dc_blocker_cc(1024, True)
        self.dcblock_0 = filter.dc_blocker_cc(1024, True)
        self.c2r_3 = blocks.complex_to_real(1)
        self.c2r_2 = blocks.complex_to_real(1)
        self.c2r_1 = blocks.complex_to_real(1)
        self.c2r_0 = blocks.complex_to_real(1)
        self.bp_3 = filter.fir_filter_ccc(1, disp_taps_bp)
        self.bp_3.declare_sample_delay(0)
        self.bp_2 = filter.fir_filter_ccc(1, disp_taps_bp)
        self.bp_2.declare_sample_delay(0)
        self.bp_1 = filter.fir_filter_ccc(1, disp_taps_bp)
        self.bp_1.declare_sample_delay(0)
        self.bp_0 = filter.fir_filter_ccc(1, disp_taps_bp)
        self.bp_0.declare_sample_delay(0)
        self._band_tool_bar = Qt.QToolBar(self)

        if None:
            self._band_formatter = None
        else:
            self._band_formatter = lambda x: str(x)

        self._band_tool_bar.addWidget(Qt.QLabel('CURRENT BAND' + ": "))
        self._band_label = Qt.QLabel(str(self._band_formatter(self.band)))
        self._band_tool_bar.addWidget(self._band_label)
        self.tabs_grid_layout_0.addWidget(self._band_tool_bar, 5, 0, 1, 2)
        for r in range(5, 6):
            self.tabs_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 2):
            self.tabs_grid_layout_0.setColumnStretch(c, 1)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.bp_0, 0), (self.disp_gate_0, 0))
        self.connect((self.bp_0, 0), (self.ph_est, 1))
        self.connect((self.bp_0, 0), (self.ph_est, 0))
        self.connect((self.bp_1, 0), (self.disp_gate_1, 0))
        self.connect((self.bp_1, 0), (self.ph_est, 4))
        self.connect((self.bp_2, 0), (self.disp_gate_2, 0))
        self.connect((self.bp_2, 0), (self.ph_est, 2))
        self.connect((self.bp_3, 0), (self.disp_gate_3, 0))
        self.connect((self.bp_3, 0), (self.ph_est, 3))
        self.connect((self.c2r_0, 0), (self.qtgui_time_sink_x_1, 0))
        self.connect((self.c2r_1, 0), (self.qtgui_time_sink_x_1, 3))
        self.connect((self.c2r_2, 0), (self.qtgui_time_sink_x_1, 1))
        self.connect((self.c2r_3, 0), (self.qtgui_time_sink_x_1, 2))
        self.connect((self.dcblock_0, 0), (self.bp_0, 0))
        self.connect((self.dcblock_0, 0), (self.spec_gate_0, 0))
        self.connect((self.dcblock_1, 0), (self.bp_1, 0))
        self.connect((self.dcblock_1, 0), (self.spec_gate_1, 0))
        self.connect((self.dcblock_2, 0), (self.bp_2, 0))
        self.connect((self.dcblock_2, 0), (self.spec_gate_2, 0))
        self.connect((self.dcblock_3, 0), (self.bp_3, 0))
        self.connect((self.dcblock_3, 0), (self.spec_gate_3, 0))
        self.connect((self.disp_gate_0, 0), (self.time_resamp_0, 0))
        self.connect((self.disp_gate_1, 0), (self.time_resamp_1, 0))
        self.connect((self.disp_gate_2, 0), (self.time_resamp_2, 0))
        self.connect((self.disp_gate_3, 0), (self.time_resamp_3, 0))
        self.connect((self.ph_avg_0, 0), (self.ph_dec_0, 0))
        self.connect((self.ph_avg_1, 0), (self.ph_dec_1, 0))
        self.connect((self.ph_avg_2, 0), (self.ph_dec_2, 0))
        self.connect((self.ph_avg_2_0, 0), (self.ph_dec_2_0, 0))
        self.connect((self.ph_dec_0, 0), (self.ph_num_0, 0))
        self.connect((self.ph_dec_1, 0), (self.ph_num_1, 0))
        self.connect((self.ph_dec_2, 0), (self.ph_num_2, 0))
        self.connect((self.ph_dec_2_0, 0), (self.ph_num_2_0, 0))
        self.connect((self.ph_deg_0, 0), (self.ph_avg_0, 0))
        self.connect((self.ph_deg_1, 0), (self.ph_avg_1, 0))
        self.connect((self.ph_deg_2, 0), (self.ph_avg_2, 0))
        self.connect((self.ph_deg_2_0, 0), (self.ph_avg_2_0, 0))
        self.connect((self.ph_est, 0), (self.ph_deg_0, 0))
        self.connect((self.ph_est, 1), (self.ph_deg_1, 0))
        self.connect((self.ph_est, 2), (self.ph_deg_2, 0))
        self.connect((self.ph_est, 3), (self.ph_deg_2_0, 0))
        self.connect((self.spec_gate_0, 0), (self.qtgui_freq_sink_x_0, 0))
        self.connect((self.spec_gate_1, 0), (self.qtgui_freq_sink_x_0, 3))
        self.connect((self.spec_gate_2, 0), (self.qtgui_freq_sink_x_0, 1))
        self.connect((self.spec_gate_3, 0), (self.qtgui_freq_sink_x_0, 2))
        self.connect((self.time_resamp_0, 0), (self.c2r_0, 0))
        self.connect((self.time_resamp_1, 0), (self.c2r_1, 0))
        self.connect((self.time_resamp_2, 0), (self.c2r_2, 0))
        self.connect((self.time_resamp_3, 0), (self.c2r_3, 0))
        self.connect((self.twinrx_hopping_source_0, 0), (self.dcblock_0, 0))
        self.connect((self.twinrx_hopping_source_0, 3), (self.dcblock_1, 0))
        self.connect((self.twinrx_hopping_source_0, 1), (self.dcblock_2, 0))
        self.connect((self.twinrx_hopping_source_0, 2), (self.dcblock_3, 0))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("GNU Radio", "guru")
        self.settings.setValue("geometry", self.saveGeometry())
        event.accept()

    def get_tone_offset(self):
        return self.tone_offset

    def set_tone_offset(self, tone_offset):
        self.tone_offset = tone_offset
        self.set_disp_taps_bp(firdes.complex_band_pass(1.0, self.samp_rate, self.tone_offset - self.disp_bw/2, self.tone_offset + self.disp_bw/2, self.disp_bw/4, firdes.WIN_HAMMING))

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
        self.time_resamp_0.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING))
        self.time_resamp_1.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING))
        self.time_resamp_2.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING))
        self.time_resamp_3.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING))

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_disp_taps_bp(firdes.complex_band_pass(1.0, self.samp_rate, self.tone_offset - self.disp_bw/2, self.tone_offset + self.disp_bw/2, self.disp_bw/4, firdes.WIN_HAMMING))
        self.set_time_srate(self.samp_rate * self.time_interp)
        self.set_tone_taps(firdes.low_pass(1.0, self.samp_rate, self.tone_bw, self.tone_bw/2.0, firdes.WIN_HAMMING))
        self.qtgui_freq_sink_x_0.set_frequency_range(self.center_freq, self.samp_rate)

    def get_disp_bw(self):
        return self.disp_bw

    def set_disp_bw(self, disp_bw):
        self.disp_bw = disp_bw
        self.set_disp_taps_bp(firdes.complex_band_pass(1.0, self.samp_rate, self.tone_offset - self.disp_bw/2, self.tone_offset + self.disp_bw/2, self.disp_bw/4, firdes.WIN_HAMMING))

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.set_band(self._band_formatter('%.4f GHz' % (self.center_freq/1e9)))
        self.qtgui_freq_sink_x_0.set_frequency_range(self.center_freq, self.samp_rate)

    def get_view_decim(self):
        return self.view_decim

    def set_view_decim(self, view_decim):
        self.view_decim = view_decim

    def get_tx_disp_gain(self):
        return self.tx_disp_gain

    def set_tx_disp_gain(self, tx_disp_gain):
        self.tx_disp_gain = tx_disp_gain

    def get_tx_control(self):
        return self.tx_control

    def set_tx_control(self, tx_control):
        self.tx_control = tx_control

    def get_tone_taps(self):
        return self.tone_taps

    def set_tone_taps(self, tone_taps):
        self.tone_taps = tone_taps

    def get_time_srate(self):
        return self.time_srate

    def set_time_srate(self, time_srate):
        self.time_srate = time_srate
        self.qtgui_time_sink_x_1.set_samp_rate(self.time_srate)
        self.time_resamp_0.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING))
        self.time_resamp_1.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING))
        self.time_resamp_2.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING))
        self.time_resamp_3.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING))

    def get_subdev(self):
        return self.subdev

    def set_subdev(self, subdev):
        self.subdev = subdev

    def get_ph_skip(self):
        return self.ph_skip

    def set_ph_skip(self, ph_skip):
        self.ph_skip = ph_skip

    def get_ph_avg(self):
        return self.ph_avg

    def set_ph_avg(self, ph_avg):
        self.ph_avg = ph_avg
        self.ph_avg_0.set_length_and_scale(self.ph_avg, 1.0/self.ph_avg)
        self.ph_avg_1.set_length_and_scale(self.ph_avg, 1.0/self.ph_avg)
        self.ph_avg_2.set_length_and_scale(self.ph_avg, 1.0/self.ph_avg)
        self.ph_avg_2_0.set_length_and_scale(self.ph_avg, 1.0/self.ph_avg)

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

    def get_dsp_manual(self):
        return self.dsp_manual

    def set_dsp_manual(self, dsp_manual):
        self.dsp_manual = dsp_manual

    def get_disp_taps_bp(self):
        return self.disp_taps_bp

    def set_disp_taps_bp(self, disp_taps_bp):
        self.disp_taps_bp = disp_taps_bp
        self.bp_0.set_taps(self.disp_taps_bp)
        self.bp_1.set_taps(self.disp_taps_bp)
        self.bp_2.set_taps(self.disp_taps_bp)
        self.bp_3.set_taps(self.disp_taps_bp)

    def get_disp_gain(self):
        return self.disp_gain

    def set_disp_gain(self, disp_gain):
        self.disp_gain = disp_gain
        self.time_resamp_0.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING))
        self.time_resamp_1.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING))
        self.time_resamp_2.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING))
        self.time_resamp_3.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, 300e3, 50e3, firdes.WIN_HAMMING))

    def get_cmd_lead(self):
        return self.cmd_lead

    def set_cmd_lead(self, cmd_lead):
        self.cmd_lead = cmd_lead

    def get_band(self):
        return self.band

    def set_band(self, band):
        self.band = band
        Qt.QMetaObject.invokeMethod(self._band_label, "setText", Qt.Q_ARG("QString", self.band))

    def get_avg_len(self):
        return self.avg_len

    def set_avg_len(self, avg_len):
        self.avg_len = avg_len

def snipfcn_snippet_hop(self):
    # Follows the hopping block: keeps the CURRENT BAND label in step, and
    # blanks the time plot while the radio settles after a hop.
    #
    # Only the display path is gated. Muting the samples themselves also fed
    # zeros to the phase estimator, which then read a clean +0.00 deg -- a
    # perfectly steady number from no signal at all, which is the one reading
    # this bench must never produce.
    import threading, time

    self._hop_run = True
    _gates = [self.disp_gate_0, self.disp_gate_1,
              self.disp_gate_2, self.disp_gate_3,
              self.spec_gate_0, self.spec_gate_1,
              self.spec_gate_2, self.spec_gate_3]

    def _follow():
        last_band, last_open = None, None
        while self._hop_run:
            try:
                b = self.twinrx_hopping_source_0.get_current_band()
                settled = self.twinrx_hopping_source_0.is_settled()
            except Exception:
                b, settled = None, True
            if b is not None and b != last_band:
                last_band = b
                self.set_center_freq(b[0])
            if settled != last_open:
                last_open = settled
                for g in _gates:
                    g.set_k(1.0 if settled else 0.0)
            time.sleep(0.05)

    threading.Thread(target=_follow, daemon=True).start()

def snipfcn_snippet_lo_config(self):
    # LO routing and the timed tune happen INSIDE the TwinRX USRP Source
    # block, so nothing LO-related belongs here.
    #
    # The calibration source is a HackRF One, started outside this flowgraph
    # (run_hop.sh, or: hackrf --freq 2.4e9 --vga 16). It cannot be launched
    # from here: the HackRF needs the system GNU Radio 3.10 while this runs
    # under 3.8, and keeping libuhd 4.1 out of the transmitter's process
    # matters because the X310's FPGA image is built for UHD 3.15.
    print('[*] Calibration source: HackRF One (started separately).')

def snipfcn_snippet_lo_stop(self):
    # Stop the block's hop thread BEFORE the flowgraph tears down.
    #
    # It lives inside the source block and checks that block's own flag, so
    # setting a flag on the top block here did nothing. The thread kept
    # issuing timed tune commands while the USRP object was being destroyed,
    # which left the X310's RFNoC control plane wedged -- recoverable only by
    # power cycling the radio.
    try:
        self.twinrx_hopping_source_0.stop_hopping()
        print('Hop thread stopped.')
    except Exception as e:
        print('Could not stop the hop thread: %s' % e)
    self._twinrx_run = False

def snipfcn_snippet_lo_watch(self):
    print('TwinRX USRP Source block owns LO routing and tuning.')


def snippets_main_after_init(tb):
    snipfcn_snippet_lo_config(tb)

def snippets_main_after_start(tb):
    snipfcn_snippet_hop(tb)
    snipfcn_snippet_lo_watch(tb)

def snippets_main_after_stop(tb):
    snipfcn_snippet_lo_stop(tb)




def main(top_block_cls=guru, options=None):

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
