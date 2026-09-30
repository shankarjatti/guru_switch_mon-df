#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Guru fast: USRP-2945 4-Channel, 10 ms dwell + 10 ms switching, radio-clock hopping
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
from PyQt5.QtCore import QObject, pyqtSlot
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
import doa

from gnuradio import qtgui

class guru_fast(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "Guru fast: USRP-2945 4-Channel, 10 ms dwell + 10 ms switching, radio-clock hopping")
        Qt.QWidget.__init__(self)
        self.setWindowTitle("Guru fast: USRP-2945 4-Channel, 10 ms dwell + 10 ms switching, radio-clock hopping")
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

        self.settings = Qt.QSettings("GNU Radio", "guru_fast")

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
        self.tone_band = tone_band = 2400000000.0
        self.time_interp = time_interp = 20
        self.samp_rate = samp_rate = 1000000
        self.disp_bw = disp_bw = 300e3
        self.view_decim = view_decim = 2048
        self.tx_disp_gain = tx_disp_gain = 10
        self.tx_control = tx_control = '127.0.0.1:5123'
        self.tone_taps = tone_taps = firdes.low_pass(1.0, samp_rate, tone_bw, tone_bw/2.0, firdes.WIN_HAMMING)
        self.time_srate = time_srate = samp_rate * time_interp
        self.subdev = subdev = "A:0 A:1 B:0 B:1"
        self.stream_state = stream_state = 'receiving'
        self.sched_state = sched_state = 'starting'
        self.ph_skip = ph_skip = 2**13
        self.ph_avg = ph_avg = 16384
        self.lo_sources = lo_sources = ['external', 'external', 'internal', 'companion']
        self.lo_export_chan = lo_export_chan = 2
        self.dsp_manual = dsp_manual = True
        self.disp_taps_bp = disp_taps_bp = firdes.complex_band_pass(1.0, samp_rate, tone_offset - disp_bw/2, tone_offset + disp_bw/2, disp_bw/4, firdes.WIN_HAMMING)
        self.disp_interp_trans = disp_interp_trans = samp_rate - 2 * disp_bw
        self.disp_gain = disp_gain = 25
        self.cmd_lead = cmd_lead = 0.1
        self.center_freq = center_freq = tone_band
        self.avg_len = avg_len = 65536

        ##################################################
        # Blocks
        ##################################################
        self.tabs = Qt.QTabWidget()
        self.tabs_widget_0 = Qt.QWidget()
        self.tabs_layout_0 = Qt.QBoxLayout(Qt.QBoxLayout.TopToBottom, self.tabs_widget_0)
        self.tabs_grid_layout_0 = Qt.QGridLayout()
        self.tabs_layout_0.addLayout(self.tabs_grid_layout_0)
        self.tabs.addTab(self.tabs_widget_0, 'Hopping')
        self.tabs_widget_1 = Qt.QWidget()
        self.tabs_layout_1 = Qt.QBoxLayout(Qt.QBoxLayout.TopToBottom, self.tabs_widget_1)
        self.tabs_grid_layout_1 = Qt.QGridLayout()
        self.tabs_layout_1.addLayout(self.tabs_grid_layout_1)
        self.tabs.addTab(self.tabs_widget_1, 'Spectra')
        self.tabs_widget_2 = Qt.QWidget()
        self.tabs_layout_2 = Qt.QBoxLayout(Qt.QBoxLayout.TopToBottom, self.tabs_widget_2)
        self.tabs_grid_layout_2 = Qt.QGridLayout()
        self.tabs_layout_2.addLayout(self.tabs_grid_layout_2)
        self.tabs.addTab(self.tabs_widget_2, 'Switching')
        self.top_layout.addWidget(self.tabs)
        # Create the options list
        self._tone_band_options = [2400000000.0, 5200000000.0, 5800000000.0]
        # Create the labels list
        self._tone_band_labels = ['2.4 GHz', '5.2 GHz', '5.8 GHz']
        # Create the combo box
        self._tone_band_tool_bar = Qt.QToolBar(self)
        self._tone_band_tool_bar.addWidget(Qt.QLabel('LAB TONE (HackRF) BAND' + ": "))
        self._tone_band_combo_box = Qt.QComboBox()
        self._tone_band_tool_bar.addWidget(self._tone_band_combo_box)
        for _label in self._tone_band_labels: self._tone_band_combo_box.addItem(_label)
        self._tone_band_callback = lambda i: Qt.QMetaObject.invokeMethod(self._tone_band_combo_box, "setCurrentIndex", Qt.Q_ARG("int", self._tone_band_options.index(i)))
        self._tone_band_callback(self.tone_band)
        self._tone_band_combo_box.currentIndexChanged.connect(
            lambda i: self.set_tone_band(self._tone_band_options[i]))
        # Create the radio buttons
        self.tabs_grid_layout_0.addWidget(self._tone_band_tool_bar, 1, 0, 1, 3)
        for r in range(1, 2):
            self.tabs_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 3):
            self.tabs_grid_layout_0.setColumnStretch(c, 1)
        self.wave_sink = qtgui.time_sink_f(
            1000, #size
            time_srate, #samp_rate
            "RF waveforms of the LAB TONE band (its 10 ms dwells only), all 4 channels", #name
            4 #number of inputs
        )
        self.wave_sink.set_update_time(0.10)
        self.wave_sink.set_y_axis(-0.6, 0.6)

        self.wave_sink.set_y_label('Amplitude', "")

        self.wave_sink.enable_tags(False)
        self.wave_sink.set_trigger_mode(qtgui.TRIG_MODE_TAG, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, 'hop_frame')
        self.wave_sink.enable_autoscale(True)
        self.wave_sink.enable_grid(True)
        self.wave_sink.enable_axis_labels(True)
        self.wave_sink.enable_control_panel(True)
        self.wave_sink.enable_stem_plot(False)


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
                self.wave_sink.set_line_label(i, "Data {0}".format(i))
            else:
                self.wave_sink.set_line_label(i, labels[i])
            self.wave_sink.set_line_width(i, widths[i])
            self.wave_sink.set_line_color(i, colors[i])
            self.wave_sink.set_line_style(i, styles[i])
            self.wave_sink.set_line_marker(i, markers[i])
            self.wave_sink.set_line_alpha(i, alphas[i])

        self._wave_sink_win = sip.wrapinstance(self.wave_sink.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_0.addWidget(self._wave_sink_win, 7, 0, 1, 3)
        for r in range(7, 8):
            self.tabs_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 3):
            self.tabs_grid_layout_0.setColumnStretch(c, 1)
        self.wave_sel = doa.hop_band_select(4, tone_band, 'hop_frame', 100, False, 0.0, samp_rate)
        self.wave_rs_3 = filter.rational_resampler_ccc(
                interpolation=time_interp,
                decimation=1,
                taps=firdes.low_pass(time_interp * disp_gain, time_srate, disp_bw, disp_interp_trans, firdes.WIN_HAMMING),
                fractional_bw=0)
        self.wave_rs_2 = filter.rational_resampler_ccc(
                interpolation=time_interp,
                decimation=1,
                taps=firdes.low_pass(time_interp * disp_gain, time_srate, disp_bw, disp_interp_trans, firdes.WIN_HAMMING),
                fractional_bw=0)
        self.wave_rs_1 = filter.rational_resampler_ccc(
                interpolation=time_interp,
                decimation=1,
                taps=firdes.low_pass(time_interp * disp_gain, time_srate, disp_bw, disp_interp_trans, firdes.WIN_HAMMING),
                fractional_bw=0)
        self.wave_rs_0 = filter.rational_resampler_ccc(
                interpolation=time_interp,
                decimation=1,
                taps=firdes.low_pass(time_interp * disp_gain, time_srate, disp_bw, disp_interp_trans, firdes.WIN_HAMMING),
                fractional_bw=0)
        self.wave_c2r_3 = blocks.complex_to_real(1)
        self.wave_c2r_2 = blocks.complex_to_real(1)
        self.wave_c2r_1 = blocks.complex_to_real(1)
        self.wave_c2r_0 = blocks.complex_to_real(1)
        self.twinrx_radio_source_0 = doa.twinrx_radio_source(
            samp_rate=samp_rate,
            addresses='addr=192.168.10.2',
            bands=[
                (2400000000.0, 46.0, 0.01),
                (5200000000.0, 60.0, 0.01),
                (5800000000.0, 69.0, 0.01),
            ],
            settle=0.01,
            guard_pre=0.00025,
            gain_trim=(0.0, -13.3, 1.5, -1.7),
            hop_enable=True,
            start_delay=0.5,
            tx_control="127.0.0.1:5123",
            park_freq=tone_band,
            lock_check=0.007,
            min_slack=0.008,
            recv_buff_size=33554432,
            rt_priority=0,
            burst=False,
            preroll=0.00025,
        )
        self.sw_sink = qtgui.time_sink_f(
            3000, #size
            50000.0, #samp_rate
            "One cycle:  0-10 ms switch | 10-20 ms 2.4 GHz  |  20-30 ms switch | 30-40 ms 5.2 GHz  |  40-50 ms switch | 50-60 ms 5.8 GHz", #name
            4 #number of inputs
        )
        self.sw_sink.set_update_time(0.20)
        self.sw_sink.set_y_axis(-0.05, 0.5)

        self.sw_sink.set_y_label('|amplitude|', "")

        self.sw_sink.enable_tags(False)
        self.sw_sink.set_trigger_mode(qtgui.TRIG_MODE_TAG, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, 'hop_cycle')
        self.sw_sink.enable_autoscale(False)
        self.sw_sink.enable_grid(True)
        self.sw_sink.enable_axis_labels(True)
        self.sw_sink.enable_control_panel(True)
        self.sw_sink.enable_stem_plot(False)


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
                self.sw_sink.set_line_label(i, "Data {0}".format(i))
            else:
                self.sw_sink.set_line_label(i, labels[i])
            self.sw_sink.set_line_width(i, widths[i])
            self.sw_sink.set_line_color(i, colors[i])
            self.sw_sink.set_line_style(i, styles[i])
            self.sw_sink.set_line_marker(i, markers[i])
            self.sw_sink.set_line_alpha(i, alphas[i])

        self._sw_sink_win = sip.wrapinstance(self.sw_sink.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_2.addWidget(self._sw_sink_win, 0, 0, 1, 3)
        for r in range(0, 1):
            self.tabs_grid_layout_2.setRowStretch(r, 1)
        for c in range(0, 3):
            self.tabs_grid_layout_2.setColumnStretch(c, 1)
        self.sw_mag_3 = blocks.complex_to_mag(1)
        self.sw_mag_2 = blocks.complex_to_mag(1)
        self.sw_mag_1 = blocks.complex_to_mag(1)
        self.sw_mag_0 = blocks.complex_to_mag(1)
        self.sw_dec_3 = blocks.keep_one_in_n(gr.sizeof_float*1, 20)
        self.sw_dec_2 = blocks.keep_one_in_n(gr.sizeof_float*1, 20)
        self.sw_dec_1 = blocks.keep_one_in_n(gr.sizeof_float*1, 20)
        self.sw_dec_0 = blocks.keep_one_in_n(gr.sizeof_float*1, 20)
        self.sw_avg_3 = blocks.moving_average_ff(20, disp_gain * 1.0/20, 4000, 1)
        self.sw_avg_2 = blocks.moving_average_ff(20, disp_gain * 1.0/20, 4000, 1)
        self.sw_avg_1 = blocks.moving_average_ff(20, disp_gain * 1.0/20, 4000, 1)
        self.sw_avg_0 = blocks.moving_average_ff(20, disp_gain * 1.0/20, 4000, 1)
        self._stream_state_tool_bar = Qt.QToolBar(self)

        if None:
            self._stream_state_formatter = None
        else:
            self._stream_state_formatter = lambda x: str(x)

        self._stream_state_tool_bar.addWidget(Qt.QLabel('STREAM' + ": "))
        self._stream_state_label = Qt.QLabel(str(self._stream_state_formatter(self.stream_state)))
        self._stream_state_tool_bar.addWidget(self._stream_state_label)
        self.tabs_grid_layout_0.addWidget(self._stream_state_tool_bar, 3, 0, 1, 3)
        for r in range(3, 4):
            self.tabs_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 3):
            self.tabs_grid_layout_0.setColumnStretch(c, 1)
        self.spec_sel = doa.hop_band_select(4, tone_band, '', 100, False, 0, samp_rate)
        self._sched_state_tool_bar = Qt.QToolBar(self)

        if None:
            self._sched_state_formatter = None
        else:
            self._sched_state_formatter = lambda x: str(x)

        self._sched_state_tool_bar.addWidget(Qt.QLabel('SCHEDULE' + ": "))
        self._sched_state_label = Qt.QLabel(str(self._sched_state_formatter(self.sched_state)))
        self._sched_state_tool_bar.addWidget(self._sched_state_label)
        self.tabs_grid_layout_0.addWidget(self._sched_state_tool_bar, 2, 0, 1, 3)
        for r in range(2, 3):
            self.tabs_grid_layout_0.setRowStretch(r, 1)
        for c in range(0, 3):
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
        self.phase_correct_hopping_0 = doa.phase_correct_hopping(
            num_channels=4,
            bands=[
                (2400000000.0, (175.90, -86.62, -168.03), 10),
                (5200000000.0, (111.43, 71.93, 35.91), 10),
                (5800000000.0, (82.66, 155.54, 173.74), 10),
            ],
            cal_file="",
            follow_source=True,
            settle=1.0,
            start_delay=2.0,
            freq_tol=1000000,
            follow_tags=True,
        )
        self.ph_meter_null3 = blocks.null_sink(gr.sizeof_float*1)
        self.ph_meter_null2 = blocks.null_sink(gr.sizeof_float*1)
        self.ph_meter_null1 = blocks.null_sink(gr.sizeof_float*1)
        self.ph_meter_null0 = blocks.null_sink(gr.sizeof_float*1)
        self.ph_meter = doa.hop_phase_meter(4, tone_band, samp_rate, tone_offset - disp_bw/2 + 10e3, tone_offset + disp_bw/2 - 10e3, 20, 10, 1e9, False, 0)
        self.met_2_null3 = blocks.null_sink(gr.sizeof_float*1)
        self.met_2_null2 = blocks.null_sink(gr.sizeof_float*1)
        self.met_2_null1 = blocks.null_sink(gr.sizeof_float*1)
        self.met_2_null0 = blocks.null_sink(gr.sizeof_float*1)
        self.met_2 = doa.hop_phase_meter(4, 5800000000.0, samp_rate, tone_offset - disp_bw/2 + 10e3, tone_offset + disp_bw/2 - 10e3, 20, 10, 5, False, 0)
        self.met_1_null3 = blocks.null_sink(gr.sizeof_float*1)
        self.met_1_null2 = blocks.null_sink(gr.sizeof_float*1)
        self.met_1_null1 = blocks.null_sink(gr.sizeof_float*1)
        self.met_1_null0 = blocks.null_sink(gr.sizeof_float*1)
        self.met_1 = doa.hop_phase_meter(4, 5200000000.0, samp_rate, tone_offset - disp_bw/2 + 10e3, tone_offset + disp_bw/2 - 10e3, 20, 10, 5, False, 0)
        self.met_0_null3 = blocks.null_sink(gr.sizeof_float*1)
        self.met_0_null2 = blocks.null_sink(gr.sizeof_float*1)
        self.met_0_null1 = blocks.null_sink(gr.sizeof_float*1)
        self.met_0_null0 = blocks.null_sink(gr.sizeof_float*1)
        self.met_0 = doa.hop_phase_meter(4, 2400000000.0, samp_rate, tone_offset - disp_bw/2 + 10e3, tone_offset + disp_bw/2 - 10e3, 20, 10, 5, False, 0)
        self.bp_3 = filter.fir_filter_ccc(1, disp_taps_bp)
        self.bp_3.declare_sample_delay(0)
        self.bp_2 = filter.fir_filter_ccc(1, disp_taps_bp)
        self.bp_2.declare_sample_delay(0)
        self.bp_1 = filter.fir_filter_ccc(1, disp_taps_bp)
        self.bp_1.declare_sample_delay(0)
        self.bp_0 = filter.fir_filter_ccc(1, disp_taps_bp)
        self.bp_0.declare_sample_delay(0)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.bp_0, 0), (self.phase_correct_hopping_0, 0))
        self.connect((self.bp_1, 0), (self.phase_correct_hopping_0, 3))
        self.connect((self.bp_2, 0), (self.phase_correct_hopping_0, 1))
        self.connect((self.bp_3, 0), (self.phase_correct_hopping_0, 2))
        self.connect((self.met_0, 0), (self.met_0_null0, 0))
        self.connect((self.met_0, 1), (self.met_0_null1, 0))
        self.connect((self.met_0, 2), (self.met_0_null2, 0))
        self.connect((self.met_0, 3), (self.met_0_null3, 0))
        self.connect((self.met_1, 0), (self.met_1_null0, 0))
        self.connect((self.met_1, 1), (self.met_1_null1, 0))
        self.connect((self.met_1, 2), (self.met_1_null2, 0))
        self.connect((self.met_1, 3), (self.met_1_null3, 0))
        self.connect((self.met_2, 0), (self.met_2_null0, 0))
        self.connect((self.met_2, 1), (self.met_2_null1, 0))
        self.connect((self.met_2, 2), (self.met_2_null2, 0))
        self.connect((self.met_2, 3), (self.met_2_null3, 0))
        self.connect((self.ph_meter, 0), (self.ph_meter_null0, 0))
        self.connect((self.ph_meter, 1), (self.ph_meter_null1, 0))
        self.connect((self.ph_meter, 2), (self.ph_meter_null2, 0))
        self.connect((self.ph_meter, 3), (self.ph_meter_null3, 0))
        self.connect((self.phase_correct_hopping_0, 2), (self.met_0, 2))
        self.connect((self.phase_correct_hopping_0, 0), (self.met_0, 0))
        self.connect((self.phase_correct_hopping_0, 1), (self.met_0, 1))
        self.connect((self.phase_correct_hopping_0, 3), (self.met_0, 3))
        self.connect((self.phase_correct_hopping_0, 0), (self.met_1, 0))
        self.connect((self.phase_correct_hopping_0, 3), (self.met_1, 3))
        self.connect((self.phase_correct_hopping_0, 1), (self.met_1, 1))
        self.connect((self.phase_correct_hopping_0, 2), (self.met_1, 2))
        self.connect((self.phase_correct_hopping_0, 1), (self.met_2, 1))
        self.connect((self.phase_correct_hopping_0, 2), (self.met_2, 2))
        self.connect((self.phase_correct_hopping_0, 3), (self.met_2, 3))
        self.connect((self.phase_correct_hopping_0, 0), (self.met_2, 0))
        self.connect((self.phase_correct_hopping_0, 2), (self.ph_meter, 2))
        self.connect((self.phase_correct_hopping_0, 0), (self.ph_meter, 0))
        self.connect((self.phase_correct_hopping_0, 1), (self.ph_meter, 1))
        self.connect((self.phase_correct_hopping_0, 3), (self.ph_meter, 3))
        self.connect((self.phase_correct_hopping_0, 0), (self.sw_mag_0, 0))
        self.connect((self.phase_correct_hopping_0, 1), (self.sw_mag_1, 0))
        self.connect((self.phase_correct_hopping_0, 2), (self.sw_mag_2, 0))
        self.connect((self.phase_correct_hopping_0, 3), (self.sw_mag_3, 0))
        self.connect((self.phase_correct_hopping_0, 2), (self.wave_sel, 2))
        self.connect((self.phase_correct_hopping_0, 0), (self.wave_sel, 0))
        self.connect((self.phase_correct_hopping_0, 1), (self.wave_sel, 1))
        self.connect((self.phase_correct_hopping_0, 3), (self.wave_sel, 3))
        self.connect((self.spec_sel, 1), (self.qtgui_freq_sink_x_0, 1))
        self.connect((self.spec_sel, 3), (self.qtgui_freq_sink_x_0, 3))
        self.connect((self.spec_sel, 0), (self.qtgui_freq_sink_x_0, 0))
        self.connect((self.spec_sel, 2), (self.qtgui_freq_sink_x_0, 2))
        self.connect((self.sw_avg_0, 0), (self.sw_dec_0, 0))
        self.connect((self.sw_avg_1, 0), (self.sw_dec_1, 0))
        self.connect((self.sw_avg_2, 0), (self.sw_dec_2, 0))
        self.connect((self.sw_avg_3, 0), (self.sw_dec_3, 0))
        self.connect((self.sw_dec_0, 0), (self.sw_sink, 0))
        self.connect((self.sw_dec_1, 0), (self.sw_sink, 1))
        self.connect((self.sw_dec_2, 0), (self.sw_sink, 2))
        self.connect((self.sw_dec_3, 0), (self.sw_sink, 3))
        self.connect((self.sw_mag_0, 0), (self.sw_avg_0, 0))
        self.connect((self.sw_mag_1, 0), (self.sw_avg_1, 0))
        self.connect((self.sw_mag_2, 0), (self.sw_avg_2, 0))
        self.connect((self.sw_mag_3, 0), (self.sw_avg_3, 0))
        self.connect((self.twinrx_radio_source_0, 0), (self.bp_0, 0))
        self.connect((self.twinrx_radio_source_0, 3), (self.bp_1, 0))
        self.connect((self.twinrx_radio_source_0, 1), (self.bp_2, 0))
        self.connect((self.twinrx_radio_source_0, 2), (self.bp_3, 0))
        self.connect((self.twinrx_radio_source_0, 2), (self.spec_sel, 2))
        self.connect((self.twinrx_radio_source_0, 3), (self.spec_sel, 3))
        self.connect((self.twinrx_radio_source_0, 0), (self.spec_sel, 0))
        self.connect((self.twinrx_radio_source_0, 1), (self.spec_sel, 1))
        self.connect((self.wave_c2r_0, 0), (self.wave_sink, 0))
        self.connect((self.wave_c2r_1, 0), (self.wave_sink, 1))
        self.connect((self.wave_c2r_2, 0), (self.wave_sink, 2))
        self.connect((self.wave_c2r_3, 0), (self.wave_sink, 3))
        self.connect((self.wave_rs_0, 0), (self.wave_c2r_0, 0))
        self.connect((self.wave_rs_1, 0), (self.wave_c2r_1, 0))
        self.connect((self.wave_rs_2, 0), (self.wave_c2r_2, 0))
        self.connect((self.wave_rs_3, 0), (self.wave_c2r_3, 0))
        self.connect((self.wave_sel, 0), (self.wave_rs_0, 0))
        self.connect((self.wave_sel, 1), (self.wave_rs_1, 0))
        self.connect((self.wave_sel, 2), (self.wave_rs_2, 0))
        self.connect((self.wave_sel, 3), (self.wave_rs_3, 0))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("GNU Radio", "guru_fast")
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

    def get_tone_band(self):
        return self.tone_band

    def set_tone_band(self, tone_band):
        self.tone_band = tone_band
        self.set_center_freq(self.tone_band)
        self.twinrx_radio_source_0.set_park_freq(self.tone_band)
        self._tone_band_callback(self.tone_band)
        self.spec_sel.set_band_freq(self.tone_band)
        self.wave_sel.set_band_freq(self.tone_band)
        self.ph_meter.set_band_freq(self.tone_band)

    def get_time_interp(self):
        return self.time_interp

    def set_time_interp(self, time_interp):
        self.time_interp = time_interp
        self.set_time_srate(self.samp_rate * self.time_interp)
        self.wave_rs_0.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_1.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_2.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_3.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_disp_interp_trans(self.samp_rate - 2 * self.disp_bw)
        self.set_disp_taps_bp(firdes.complex_band_pass(1.0, self.samp_rate, self.tone_offset - self.disp_bw/2, self.tone_offset + self.disp_bw/2, self.disp_bw/4, firdes.WIN_HAMMING))
        self.set_time_srate(self.samp_rate * self.time_interp)
        self.set_tone_taps(firdes.low_pass(1.0, self.samp_rate, self.tone_bw, self.tone_bw/2.0, firdes.WIN_HAMMING))
        self.qtgui_freq_sink_x_0.set_frequency_range(self.center_freq, self.samp_rate)

    def get_disp_bw(self):
        return self.disp_bw

    def set_disp_bw(self, disp_bw):
        self.disp_bw = disp_bw
        self.set_disp_interp_trans(self.samp_rate - 2 * self.disp_bw)
        self.set_disp_taps_bp(firdes.complex_band_pass(1.0, self.samp_rate, self.tone_offset - self.disp_bw/2, self.tone_offset + self.disp_bw/2, self.disp_bw/4, firdes.WIN_HAMMING))
        self.wave_rs_0.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_1.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_2.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_3.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))

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
        self.wave_sink.set_samp_rate(self.time_srate)
        self.wave_rs_0.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_1.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_2.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_3.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))

    def get_subdev(self):
        return self.subdev

    def set_subdev(self, subdev):
        self.subdev = subdev

    def get_stream_state(self):
        return self.stream_state

    def set_stream_state(self, stream_state):
        self.stream_state = stream_state
        Qt.QMetaObject.invokeMethod(self._stream_state_label, "setText", Qt.Q_ARG("QString", self.stream_state))

    def get_sched_state(self):
        return self.sched_state

    def set_sched_state(self, sched_state):
        self.sched_state = sched_state
        Qt.QMetaObject.invokeMethod(self._sched_state_label, "setText", Qt.Q_ARG("QString", self.sched_state))

    def get_ph_skip(self):
        return self.ph_skip

    def set_ph_skip(self, ph_skip):
        self.ph_skip = ph_skip

    def get_ph_avg(self):
        return self.ph_avg

    def set_ph_avg(self, ph_avg):
        self.ph_avg = ph_avg

    def get_lo_sources(self):
        return self.lo_sources

    def set_lo_sources(self, lo_sources):
        self.lo_sources = lo_sources

    def get_lo_export_chan(self):
        return self.lo_export_chan

    def set_lo_export_chan(self, lo_export_chan):
        self.lo_export_chan = lo_export_chan

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

    def get_disp_interp_trans(self):
        return self.disp_interp_trans

    def set_disp_interp_trans(self, disp_interp_trans):
        self.disp_interp_trans = disp_interp_trans
        self.wave_rs_0.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_1.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_2.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_3.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))

    def get_disp_gain(self):
        return self.disp_gain

    def set_disp_gain(self, disp_gain):
        self.disp_gain = disp_gain
        self.wave_rs_0.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_1.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_2.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.wave_rs_3.set_taps(firdes.low_pass(self.time_interp * self.disp_gain, self.time_srate, self.disp_bw, self.disp_interp_trans, firdes.WIN_HAMMING))
        self.sw_avg_0.set_length_and_scale(20, self.disp_gain * 1.0/20)
        self.sw_avg_1.set_length_and_scale(20, self.disp_gain * 1.0/20)
        self.sw_avg_2.set_length_and_scale(20, self.disp_gain * 1.0/20)
        self.sw_avg_3.set_length_and_scale(20, self.disp_gain * 1.0/20)

    def get_cmd_lead(self):
        return self.cmd_lead

    def set_cmd_lead(self, cmd_lead):
        self.cmd_lead = cmd_lead

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.qtgui_freq_sink_x_0.set_frequency_range(self.center_freq, self.samp_rate)

    def get_avg_len(self):
        return self.avg_len

    def set_avg_len(self, avg_len):
        self.avg_len = avg_len

def snipfcn_snippet_hop(self):
    # Radio-clock hopping: the band changes every slot on the radio's own clock,
    # far faster than a GUI can follow, so nothing here touches the band. The
    # correction, the plot and the readouts all switch on the hop marks the
    # source puts on the exact samples. This only reports status, twice a second.
    from PyQt5 import QtCore

    self._hop_run = True
    self._fast_state = {}

    def _poll():
        st = self._fast_state
        src = self.twinrx_radio_source_0
        try:
            s = src.get_schedule_stats()
            alive = src.stream_is_alive()
            stalls = src.get_stream_stalls()
        except Exception as e:
            s, alive, stalls = None, None, 0
            if not st.get('err'):
                st['err'] = True
                print('[follow] cannot read the source: %s: %s' % (type(e).__name__, e))
        if s is not None:
            txt = ('slots %d | used %d | late %d | unlocked %d | skipped %d | too slow %d | '
                   'send: typical %.1f ms, worst %.1f ms (limit 13 ms)'
                   % (s['slots'], s['valid'], s['late'], s['unlocked'], s['skipped'],
                      s['unknown_in_time'], s.get('avg_send_ms', 0.0), s['max_send_ms']))
            if s['timing_lost']:
                txt = 'TIMING LOST - restart. ' + txt
            if txt != st.get('sched'):
                st['sched'] = txt
                self.set_sched_state(txt)
        state = ('receiving' if alive else
                 'UNKNOWN - cannot read the stream state' if alive is None else
                 'STOPPED - the radio is not sending, nothing below is a reading')
        if stalls:
            state += '   (recovered %d time(s) this run)' % stalls
        if state != st.get('stream'):
            st['stream'] = state
            self.set_stream_state(state)

    # CALIBRATE: re-measure the table on the live chain (lab tone), see
    # doa/hop_calibrator.py. Result is applied only if every band passes.
    import os
    import time
    import doa
    from PyQt5 import Qt as _Qt
    self._cal = doa.hop_calibrator(
        self.twinrx_radio_source_0, self.phase_correct_hopping_0, {2400000000.0: self.met_0, 5200000000.0: self.met_1, 5800000000.0: self.met_2},
        [2400000000.0, 5200000000.0, 5800000000.0], secs=4.0,
        out_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'phase_table_live_deg.txt'))
    self._cal_btn = _Qt.QPushButton('CALIBRATE  (lab tone on each band, ~15 s)')
    self._cal_lbl = _Qt.QLabel('CAL: startup table from the flowgraph (not re-measured this session)')
    def _cal_click():
        if self._cal.start(restore_freq=self.tone_band):
            self._cal_btn.setEnabled(False)
    self._cal_btn.clicked.connect(_cal_click)
    self.tabs_grid_layout_0.addWidget(self._cal_btn, 0, 0, 1, 1)
    self.tabs_grid_layout_0.addWidget(self._cal_lbl, 0, 1, 1, 2)

    # one status line per band: SIGNAL or FLAT, from that band's own dwells
    self._band_lbl = []
    for _i, (_f, _m) in enumerate([(2400000000.0, self.met_0), (5200000000.0, self.met_1), (5800000000.0, self.met_2)]):
        _l = _Qt.QLabel('%g GHz: waiting for dwells' % (_f / 1e9))
        _l.setStyleSheet('font-family: monospace; font-size: 13pt;')
        self.tabs_grid_layout_2.addWidget(_l, 1 + _i, 0, 1, 3)
        self._band_lbl.append((_f, _m, _l, {'w': 0, 't': 0}))

    self._now_lbl = _Qt.QLabel('RECEIVING NOW: starting')
    self._now_lbl.setStyleSheet('font-size: 15pt; font-weight: bold;')
    self.tabs_grid_layout_0.addWidget(self._now_lbl, 4, 0, 1, 3)
    self._lock_lbl = _Qt.QLabel('LO LOCK: starting')
    self._lock_lbl.setStyleSheet('font-size: 12pt;')
    self.tabs_grid_layout_0.addWidget(self._lock_lbl, 5, 0, 1, 3)
    self._show_lbl = _Qt.QLabel('SHOWING: starting')
    self._show_lbl.setStyleSheet('font-size: 13pt; font-weight: bold; color: #1a4d8f;')
    self.tabs_grid_layout_0.addWidget(self._show_lbl, 6, 0, 1, 3)

    def _lock_poll():
        bs = self.twinrx_radio_source_0.get_band_lock_stats()
        parts = []
        for _f in [2400000000.0, 5200000000.0, 5800000000.0]:
            b = [v for k, v in bs.items() if abs(k - _f) <= 1e6]
            if not b:
                parts.append('%g GHz: waiting' % (_f / 1e9))
                continue
            b = b[0]
            why = [('%d not locked' % b['unlocked']) if b['unlocked'] else '',
                   ('%d late' % b['late']) if b['late'] else '',
                   ('%d skipped' % b['skipped']) if b['skipped'] else '',
                   ('%d no burst' % b.get('no burst', 0)) if b.get('no burst', 0) else '']
            why = ', '.join(w for w in why if w)
            parts.append('%g GHz: used %d/%d%s' % (_f / 1e9, b['locked'], b['slots'],
                         '' if not why else '  (not used: %s)' % why))
        self._lock_lbl.setText('DWELLS (LO lock confirmed before every one):   ' + '   |   '.join(parts))
        tb = float(self.tone_band)
        b = [v for k, v in bs.items() if abs(k - tb) <= 1e6]
        # say exactly why a dwell was not used: the LO itself, or the PC's timing
        if not b or b[0]['slots'] == 0:
            lock_txt = 'waiting for dwells'
        elif b[0]['unlocked']:
            lock_txt = 'LO NOT LOCKED on %d dwells (those are not drawn)' % b[0]['unlocked']
        elif b[0]['locked'] == b[0]['slots']:
            lock_txt = 'LO LOCKED on every dwell'
        else:
            lock_txt = ('LO locked on every dwell it checked; %d dwells not used because the PC sent the '
                        'band change late (not drawn)' % (b[0]['slots'] - b[0]['locked']))
        # is the lab tone actually there? (the receiver can be perfect while the
        # transmitter is silent -- say which one it is)
        ms = self.ph_meter.get_stats()
        row = [v for k, v in ms.items() if abs(k - tb) <= 1e6]
        w, t = (row[0]['windows'], row[0]['tone']) if row else (0, 0)
        last = self._fast_state.setdefault('tone_seen', {'w': 0, 't': 0, 'band': tb})
        if last['band'] != tb:
            last.update(w=w, t=t, band=tb)
        dw, dt = w - last['w'], t - last['t']
        last['w'], last['t'] = w, t
        if dw > 0 and dt == 0:
            self._show_lbl.setStyleSheet('font-size: 13pt; font-weight: bold; color: #c00000;')
            self._show_lbl.setText('SHOWING:  %g GHz  --  NO TONE right now (0/%d dwells): the lab '
                                   'transmitter is not sending on this band. Receiver OK: %s'
                                   % (tb / 1e9, dw, lock_txt))
        else:
            self._show_lbl.setStyleSheet('font-size: 13pt; font-weight: bold; color: #1a4d8f;')
            self._show_lbl.setText('SHOWING:  %g GHz  (LAB TONE band) -- its 10 ms dwells only, %s%s'
                                   % (tb / 1e9, lock_txt,
                                      '' if dw <= 0 or dt == dw else
                                      '  -- tone in only %d/%d dwells' % (dt, dw)))

    self._ph_val = []
    for _c in range(4):
        _t = _Qt.QLabel('ch%d - ch0 phase offset (deg)' % _c)
        _t.setStyleSheet('font-size: 13pt; font-weight: bold;')
        _v = _Qt.QLabel('waiting')
        _v.setStyleSheet('font-family: monospace; font-size: 15pt;')
        self.tabs_grid_layout_0.addWidget(_t, 8 + _c, 0, 1, 1)
        self.tabs_grid_layout_0.addWidget(_v, 8 + _c, 1, 1, 2)
        self._ph_val.append(_v)

    def _ph_poll():
        row = self.ph_meter.last_row
        for _c, _v in enumerate(self._ph_val):
            if row is None:
                _v.setText('waiting for the first dwell')
                _v.setStyleSheet('font-family: monospace; font-size: 15pt; color: gray;')
            elif _c == 0:
                _v.setText('   0.000 deg  (reference)')
                _v.setStyleSheet('font-family: monospace; font-size: 15pt;')
            elif row[_c] != row[_c]:
                _v.setText('NO TONE - nothing measured')
                _v.setStyleSheet('font-family: monospace; font-size: 15pt; color: #c00000; font-weight: bold;')
            else:
                _v.setText('%+8.3f deg   (average of the last 10 dwells)' % row[_c])
                _v.setStyleSheet('font-family: monospace; font-size: 15pt;')

    self._dwell_lbl = _Qt.QLabel('SAMPLES RECEIVED: 0        DWELLS: 0')
    self._dwell_lbl.setStyleSheet('font-family: monospace; font-size: 16pt; font-weight: bold;')
    self.tabs_grid_layout_0.addWidget(self._dwell_lbl, 12, 0, 1, 3)

    # the HackRF's clock correction measured at start (run_hop.sh --burst): the
    # tone's distance from where it should be then shows how far the two clocks
    # have drifted apart since
    try:
        self._ppm_start = float(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   'hackrf_ppm.txt')).read())
    except Exception:
        self._ppm_start = None

    def _dwell_poll():
        # line 1: two independent counters kept by the engine as the X310 delivers
        #   SAMPLES = every dwell sample received, added packet by packet
        #   DWELLS  = +1 for every complete dwell burst
        # line 2: the last dwell of the lab tone's band, measured on its samples
        bi = self.twinrx_radio_source_0.get_burst_info()
        if bi:
            l1 = 'SAMPLES RECEIVED: %s        DWELLS: %s' % (format(bi['dwell_samples_total'], ','),
                                                           format(bi['dwells_total'], ','))
        else:
            l1 = 'SAMPLES RECEIVED: -        DWELLS: -   (burst mode only)'
        tb = float(self.tone_band)
        w = [v for k, v in self.ph_meter.last_windows.items() if abs(k - tb) <= 1e6]
        if w and w[0]['tone']:
            l2 = 'TONE (%g GHz): %+.1f Hz        CYCLES in the last dwell (counted): %.2f' % (
                tb / 1e9, w[0]['tone_hz'], abs(w[0]['cycles_counted']))
        elif w and w[0].get('near_dc'):
            l2 = ('TONE (%g GHz): %+.0f Hz -- inside +/-2 kHz of 0 Hz (receiver leakage): NOT measured'
                  % (tb / 1e9, w[0]['tone_hz']))
        else:
            l2 = 'TONE (%g GHz): no tone in the last dwell' % (tb / 1e9)
        self._dwell_lbl.setText(l1 + '\n' + l2)

    self._dwell_timer = QtCore.QTimer(self)
    self._dwell_timer.timeout.connect(_dwell_poll)
    self._dwell_timer.start(100)

    def _now_poll():
        st, f = self.twinrx_radio_source_0.get_current()
        if f:
            self._now_lbl.setText('RECEIVING NOW:  %g GHz  (%s)' % (f / 1e9, st))
    self._now_timer = QtCore.QTimer(self)
    self._now_timer.timeout.connect(_now_poll)
    self._now_timer.start(40)

    def _band_poll():
        for _f, _m, _l, _last in self._band_lbl:
            _s = _m.get_stats()
            _row = [v for k, v in _s.items() if abs(k - _f) <= 1e6]
            _w = _row[0]['windows'] if _row else 0
            _t = _row[0]['tone'] if _row else 0
            dw, dt = _w - _last['w'], _t - _last['t']
            _last['w'], _last['t'] = _w, _t
            _ph = _m.recent(10)
            _num = ('  '.join('ch%d-ch0 %+7.2f deg' % (c + 1, v) for c, v in enumerate(_ph))
                    if _ph is not None and dt > 0 else '  '.join('ch%d-ch0     nan    ' % (c + 1) for c in range(3)))
            if dw <= 0:
                _state = 'NO DWELLS ARRIVING   '
            elif dt == dw:
                _state = 'SIGNAL (%2d/%2d dwells)' % (dt, dw)
            elif dt == 0:
                _state = 'FLAT   ( 0/%2d dwells)' % dw
            else:
                _state = 'PARTLY (%2d/%2d dwells)' % (dt, dw)
            _l.setText('%-8s  %s   %s' % ('%g GHz' % (_f / 1e9), _state, _num))

    def _cal_poll():
        if self._cal.status != self._fast_state.get('cal'):
            self._fast_state['cal'] = self._cal.status
            if self._cal.status != 'not run':
                self._cal_lbl.setText('CAL: ' + self._cal.status)
        self._cal_btn.setEnabled(not self._cal.busy)

    self._follow_timer = QtCore.QTimer(self)
    self._follow_timer.timeout.connect(_poll)
    self._follow_timer.timeout.connect(_cal_poll)
    self._follow_timer.timeout.connect(_band_poll)
    self._follow_timer.timeout.connect(_lock_poll)
    self._now_timer_ph = QtCore.QTimer(self)
    self._now_timer_ph.timeout.connect(_ph_poll)
    self._now_timer_ph.start(200)
    self._follow_timer.start(500)

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
    # twinrx_radio_source stops its scheduler and the stream inside the
    # flowgraph's own stop, before the device goes away. Only the GUI poll is
    # left to stop here.
    self._hop_run = False
    for _t in ("_follow_timer", "_now_timer", "_now_timer_ph", "_dwell_timer"):
        try:
            getattr(self, _t).stop()
        except Exception:
            pass
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




def main(top_block_cls=guru_fast, options=None):

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
