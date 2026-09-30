#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Guru SWITCH: USRP-2945 DF (shared LO, 5 ms / 7 ms hopping) + MON (own LO per channel), switched on the radio clock
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
import switch_source

from gnuradio import qtgui

class guru_switch(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "Guru SWITCH: USRP-2945 DF (shared LO, 5 ms / 7 ms hopping) + MON (own LO per channel), switched on the radio clock")
        Qt.QWidget.__init__(self)
        self.setWindowTitle("Guru SWITCH: USRP-2945 DF (shared LO, 5 ms / 7 ms hopping) + MON (own LO per channel), switched on the radio clock")
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

        self.settings = Qt.QSettings("GNU Radio", "guru_switch")

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
        self.samp_rate = samp_rate = 2000000
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
        self.mon_lbl3 = mon_lbl3 = 'MON not running'
        self.mon_lbl2 = mon_lbl2 = 'MON not running'
        self.mon_lbl1 = mon_lbl1 = 'MON not running'
        self.mon_lbl0 = mon_lbl0 = 'MON not running'
        self.mode_state = mode_state = 'starting'
        self.mode = mode = 'df'
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
        self.tabs_widget_3 = Qt.QWidget()
        self.tabs_layout_3 = Qt.QBoxLayout(Qt.QBoxLayout.TopToBottom, self.tabs_widget_3)
        self.tabs_grid_layout_3 = Qt.QGridLayout()
        self.tabs_layout_3.addLayout(self.tabs_grid_layout_3)
        self.tabs.addTab(self.tabs_widget_3, 'MON')
        self.top_layout.addWidget(self.tabs)
        # Create the options list
        self._tone_band_options = [2400000000.0, 5200000000.0, 5800000000.0, 900000000.0]
        # Create the labels list
        self._tone_band_labels = ['2.4 GHz', '5.2 GHz', '5.8 GHz', '900 MHz (MON ch0 only)']
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
        # Create the options list
        self._mode_options = ['df', 'mon']
        # Create the labels list
        self._mode_labels = ['DF - shared LO, coherent hopping', 'MON - own LO per channel']
        # Create the combo box
        self._mode_tool_bar = Qt.QToolBar(self)
        self._mode_tool_bar.addWidget(Qt.QLabel('MODE' + ": "))
        self._mode_combo_box = Qt.QComboBox()
        self._mode_tool_bar.addWidget(self._mode_combo_box)
        for _label in self._mode_labels: self._mode_combo_box.addItem(_label)
        self._mode_callback = lambda i: Qt.QMetaObject.invokeMethod(self._mode_combo_box, "setCurrentIndex", Qt.Q_ARG("int", self._mode_options.index(i)))
        self._mode_callback(self.mode)
        self._mode_combo_box.currentIndexChanged.connect(
            lambda i: self.set_mode(self._mode_options[i]))
        # Create the radio buttons
        self.top_grid_layout.addWidget(self._mode_tool_bar, 0, 0, 1, 1)
        for r in range(0, 1):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(0, 1):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.wave_sink = qtgui.time_sink_f(
            1000, #size
            time_srate, #samp_rate
            "RF waveforms of the LAB TONE band (its 5 ms dwells only), all 4 channels", #name
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
        self.wave_sel = doa.hop_band_select(4, tone_band, 'hop_frame', 100, False, 10000.0, samp_rate)
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
        self.twinrx_radio_source_0 = switch_source.switch_source(
            samp_rate=samp_rate,
            addresses='addr=192.168.10.2',
            bands=[
                (2400000000.0, 46.0, 0.005),
                (5200000000.0, 60.0, 0.005),
                (5800000000.0, 69.0, 0.005),
            ],
            settle=0.007,
            guard_pre=0.00025,
            gain_trim=(0.0, -13.3, 1.5, -1.7),
            start_delay=0.5,
            tx_control="127.0.0.1:5123",
            park_freq=tone_band,
            lock_check=0.0065,
            min_slack=0.003,
            recv_buff_size=33554432,
            rt_priority=90,
            preroll=0.00025,
            mon_freqs=(900000000.0, 2400000000.0, 5200000000.0, 5800000000.0),
            mon_gains=(60.0, 46.0, 60.0, 69.0),
            mon_dwell=0.02,
            start_mode=mode,
            switch_gap=0.01,
        )
        self.sw_sink = qtgui.time_sink_f(
            3600, #size
            100000.0, #samp_rate
            "One cycle:  0-7 ms switch | 7-12 ms 2.4 GHz  |  12-19 ms switch | 19-24 ms 5.2 GHz  |  24-31 ms switch | 31-36 ms 5.8 GHz", #name
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
        self.ph_meter = doa.hop_phase_meter(4, tone_band, samp_rate, tone_offset - disp_bw/2 + 10e3, tone_offset + disp_bw/2 - 10e3, 20, 20, 1e9, False, 0)
        self.mon_v2s3 = blocks.vector_to_stream(gr.sizeof_gr_complex*1, 4096)
        self.mon_v2s2 = blocks.vector_to_stream(gr.sizeof_gr_complex*1, 4096)
        self.mon_v2s1 = blocks.vector_to_stream(gr.sizeof_gr_complex*1, 4096)
        self.mon_v2s0 = blocks.vector_to_stream(gr.sizeof_gr_complex*1, 4096)
        self.mon_time3 = qtgui.time_sink_c(
            400, #size
            samp_rate, #samp_rate
            "MON LO3 ch3 - time (real samples, I and Q)", #name
            1 #number of inputs
        )
        self.mon_time3.set_update_time(0.10)
        self.mon_time3.set_y_axis(-0.1, 0.1)

        self.mon_time3.set_y_label('Amplitude', "")

        self.mon_time3.enable_tags(False)
        self.mon_time3.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.mon_time3.enable_autoscale(True)
        self.mon_time3.enable_grid(True)
        self.mon_time3.enable_axis_labels(True)
        self.mon_time3.enable_control_panel(False)
        self.mon_time3.enable_stem_plot(False)


        labels = ['I', 'Q', 'Ch2 RF B/RX1 - LO internal (MASTER, exports)', 'Ch3 RF B/RX2 - LO companion', 'TX Signal (B210)',
            'Signal6', 'Signal7', 'Signal8', 'Signal9', 'Signal10']
        widths = [2, 2, 2, 2, 2,
            1, 1, 1, 1, 1]
        colors = ['blue', 'red', 'green', 'magenta', 'black',
            'cyan', 'dark red', 'dark green', 'dark blue', 'dark blue']
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(2):
            if len(labels[i]) == 0:
                if (i % 2 == 0):
                    self.mon_time3.set_line_label(i, "Re{{Data {0}}}".format(i/2))
                else:
                    self.mon_time3.set_line_label(i, "Im{{Data {0}}}".format(i/2))
            else:
                self.mon_time3.set_line_label(i, labels[i])
            self.mon_time3.set_line_width(i, widths[i])
            self.mon_time3.set_line_color(i, colors[i])
            self.mon_time3.set_line_style(i, styles[i])
            self.mon_time3.set_line_marker(i, markers[i])
            self.mon_time3.set_line_alpha(i, alphas[i])

        self._mon_time3_win = sip.wrapinstance(self.mon_time3.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_3.addWidget(self._mon_time3_win, 4, 3, 2, 1)
        for r in range(4, 6):
            self.tabs_grid_layout_3.setRowStretch(r, 1)
        for c in range(3, 4):
            self.tabs_grid_layout_3.setColumnStretch(c, 1)
        self.mon_time2 = qtgui.time_sink_c(
            400, #size
            samp_rate, #samp_rate
            "MON LO2 ch2 - time (real samples, I and Q)", #name
            1 #number of inputs
        )
        self.mon_time2.set_update_time(0.10)
        self.mon_time2.set_y_axis(-0.1, 0.1)

        self.mon_time2.set_y_label('Amplitude', "")

        self.mon_time2.enable_tags(False)
        self.mon_time2.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.mon_time2.enable_autoscale(True)
        self.mon_time2.enable_grid(True)
        self.mon_time2.enable_axis_labels(True)
        self.mon_time2.enable_control_panel(False)
        self.mon_time2.enable_stem_plot(False)


        labels = ['I', 'Q', 'Ch2 RF B/RX1 - LO internal (MASTER, exports)', 'Ch3 RF B/RX2 - LO companion', 'TX Signal (B210)',
            'Signal6', 'Signal7', 'Signal8', 'Signal9', 'Signal10']
        widths = [2, 2, 2, 2, 2,
            1, 1, 1, 1, 1]
        colors = ['blue', 'red', 'green', 'magenta', 'black',
            'cyan', 'dark red', 'dark green', 'dark blue', 'dark blue']
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(2):
            if len(labels[i]) == 0:
                if (i % 2 == 0):
                    self.mon_time2.set_line_label(i, "Re{{Data {0}}}".format(i/2))
                else:
                    self.mon_time2.set_line_label(i, "Im{{Data {0}}}".format(i/2))
            else:
                self.mon_time2.set_line_label(i, labels[i])
            self.mon_time2.set_line_width(i, widths[i])
            self.mon_time2.set_line_color(i, colors[i])
            self.mon_time2.set_line_style(i, styles[i])
            self.mon_time2.set_line_marker(i, markers[i])
            self.mon_time2.set_line_alpha(i, alphas[i])

        self._mon_time2_win = sip.wrapinstance(self.mon_time2.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_3.addWidget(self._mon_time2_win, 4, 1, 2, 1)
        for r in range(4, 6):
            self.tabs_grid_layout_3.setRowStretch(r, 1)
        for c in range(1, 2):
            self.tabs_grid_layout_3.setColumnStretch(c, 1)
        self.mon_time1 = qtgui.time_sink_c(
            400, #size
            samp_rate, #samp_rate
            "MON LO1 ch1 - time (real samples, I and Q)", #name
            1 #number of inputs
        )
        self.mon_time1.set_update_time(0.10)
        self.mon_time1.set_y_axis(-0.1, 0.1)

        self.mon_time1.set_y_label('Amplitude', "")

        self.mon_time1.enable_tags(False)
        self.mon_time1.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.mon_time1.enable_autoscale(True)
        self.mon_time1.enable_grid(True)
        self.mon_time1.enable_axis_labels(True)
        self.mon_time1.enable_control_panel(False)
        self.mon_time1.enable_stem_plot(False)


        labels = ['I', 'Q', 'Ch2 RF B/RX1 - LO internal (MASTER, exports)', 'Ch3 RF B/RX2 - LO companion', 'TX Signal (B210)',
            'Signal6', 'Signal7', 'Signal8', 'Signal9', 'Signal10']
        widths = [2, 2, 2, 2, 2,
            1, 1, 1, 1, 1]
        colors = ['blue', 'red', 'green', 'magenta', 'black',
            'cyan', 'dark red', 'dark green', 'dark blue', 'dark blue']
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(2):
            if len(labels[i]) == 0:
                if (i % 2 == 0):
                    self.mon_time1.set_line_label(i, "Re{{Data {0}}}".format(i/2))
                else:
                    self.mon_time1.set_line_label(i, "Im{{Data {0}}}".format(i/2))
            else:
                self.mon_time1.set_line_label(i, labels[i])
            self.mon_time1.set_line_width(i, widths[i])
            self.mon_time1.set_line_color(i, colors[i])
            self.mon_time1.set_line_style(i, styles[i])
            self.mon_time1.set_line_marker(i, markers[i])
            self.mon_time1.set_line_alpha(i, alphas[i])

        self._mon_time1_win = sip.wrapinstance(self.mon_time1.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_3.addWidget(self._mon_time1_win, 1, 3, 2, 1)
        for r in range(1, 3):
            self.tabs_grid_layout_3.setRowStretch(r, 1)
        for c in range(3, 4):
            self.tabs_grid_layout_3.setColumnStretch(c, 1)
        self.mon_time0 = qtgui.time_sink_c(
            400, #size
            samp_rate, #samp_rate
            "MON LO0 ch0 - time (real samples, I and Q)", #name
            1 #number of inputs
        )
        self.mon_time0.set_update_time(0.10)
        self.mon_time0.set_y_axis(-0.1, 0.1)

        self.mon_time0.set_y_label('Amplitude', "")

        self.mon_time0.enable_tags(False)
        self.mon_time0.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.mon_time0.enable_autoscale(True)
        self.mon_time0.enable_grid(True)
        self.mon_time0.enable_axis_labels(True)
        self.mon_time0.enable_control_panel(False)
        self.mon_time0.enable_stem_plot(False)


        labels = ['I', 'Q', 'Ch2 RF B/RX1 - LO internal (MASTER, exports)', 'Ch3 RF B/RX2 - LO companion', 'TX Signal (B210)',
            'Signal6', 'Signal7', 'Signal8', 'Signal9', 'Signal10']
        widths = [2, 2, 2, 2, 2,
            1, 1, 1, 1, 1]
        colors = ['blue', 'red', 'green', 'magenta', 'black',
            'cyan', 'dark red', 'dark green', 'dark blue', 'dark blue']
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]
        styles = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        markers = [-1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1]


        for i in range(2):
            if len(labels[i]) == 0:
                if (i % 2 == 0):
                    self.mon_time0.set_line_label(i, "Re{{Data {0}}}".format(i/2))
                else:
                    self.mon_time0.set_line_label(i, "Im{{Data {0}}}".format(i/2))
            else:
                self.mon_time0.set_line_label(i, labels[i])
            self.mon_time0.set_line_width(i, widths[i])
            self.mon_time0.set_line_color(i, colors[i])
            self.mon_time0.set_line_style(i, styles[i])
            self.mon_time0.set_line_marker(i, markers[i])
            self.mon_time0.set_line_alpha(i, alphas[i])

        self._mon_time0_win = sip.wrapinstance(self.mon_time0.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_3.addWidget(self._mon_time0_win, 1, 1, 2, 1)
        for r in range(1, 3):
            self.tabs_grid_layout_3.setRowStretch(r, 1)
        for c in range(1, 2):
            self.tabs_grid_layout_3.setColumnStretch(c, 1)
        self.mon_spec3 = qtgui.freq_sink_c(
            4096, #size
            firdes.WIN_BLACKMAN_hARRIS, #wintype
            5800000000.0, #fc
            samp_rate, #bw
            "MON LO3 ch3 - spectrum", #name
            1
        )
        self.mon_spec3.set_update_time(0.10)
        self.mon_spec3.set_y_axis(-140, 0)
        self.mon_spec3.set_y_label('Relative Gain', 'dB')
        self.mon_spec3.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.mon_spec3.enable_autoscale(False)
        self.mon_spec3.enable_grid(True)
        self.mon_spec3.set_fft_average(0.2)
        self.mon_spec3.enable_axis_labels(True)
        self.mon_spec3.enable_control_panel(False)



        labels = ['ch3 B/RX2', 'Ch1 RF A/RX2', 'Ch2 RF B/RX1 (LO master)', 'Ch3 RF B/RX2', '',
            '', '', '', '', '']
        widths = [2, 2, 2, 2, 2,
            2, 2, 2, 2, 2]
        colors = ["blue", "red", "green", "black", "blue",
            "blue", "blue", "blue", "blue", "blue"]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.mon_spec3.set_line_label(i, "Data {0}".format(i))
            else:
                self.mon_spec3.set_line_label(i, labels[i])
            self.mon_spec3.set_line_width(i, widths[i])
            self.mon_spec3.set_line_color(i, colors[i])
            self.mon_spec3.set_line_alpha(i, alphas[i])

        self._mon_spec3_win = sip.wrapinstance(self.mon_spec3.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_3.addWidget(self._mon_spec3_win, 4, 2, 2, 1)
        for r in range(4, 6):
            self.tabs_grid_layout_3.setRowStretch(r, 1)
        for c in range(2, 3):
            self.tabs_grid_layout_3.setColumnStretch(c, 1)
        self.mon_spec2 = qtgui.freq_sink_c(
            4096, #size
            firdes.WIN_BLACKMAN_hARRIS, #wintype
            5200000000.0, #fc
            samp_rate, #bw
            "MON LO2 ch2 - spectrum", #name
            1
        )
        self.mon_spec2.set_update_time(0.10)
        self.mon_spec2.set_y_axis(-140, 0)
        self.mon_spec2.set_y_label('Relative Gain', 'dB')
        self.mon_spec2.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.mon_spec2.enable_autoscale(False)
        self.mon_spec2.enable_grid(True)
        self.mon_spec2.set_fft_average(0.2)
        self.mon_spec2.enable_axis_labels(True)
        self.mon_spec2.enable_control_panel(False)



        labels = ['ch2 B/RX1', 'Ch1 RF A/RX2', 'Ch2 RF B/RX1 (LO master)', 'Ch3 RF B/RX2', '',
            '', '', '', '', '']
        widths = [2, 2, 2, 2, 2,
            2, 2, 2, 2, 2]
        colors = ["blue", "red", "green", "black", "blue",
            "blue", "blue", "blue", "blue", "blue"]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.mon_spec2.set_line_label(i, "Data {0}".format(i))
            else:
                self.mon_spec2.set_line_label(i, labels[i])
            self.mon_spec2.set_line_width(i, widths[i])
            self.mon_spec2.set_line_color(i, colors[i])
            self.mon_spec2.set_line_alpha(i, alphas[i])

        self._mon_spec2_win = sip.wrapinstance(self.mon_spec2.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_3.addWidget(self._mon_spec2_win, 4, 0, 2, 1)
        for r in range(4, 6):
            self.tabs_grid_layout_3.setRowStretch(r, 1)
        for c in range(0, 1):
            self.tabs_grid_layout_3.setColumnStretch(c, 1)
        self.mon_spec1 = qtgui.freq_sink_c(
            4096, #size
            firdes.WIN_BLACKMAN_hARRIS, #wintype
            2400000000.0, #fc
            samp_rate, #bw
            "MON LO1 ch1 - spectrum", #name
            1
        )
        self.mon_spec1.set_update_time(0.10)
        self.mon_spec1.set_y_axis(-140, 0)
        self.mon_spec1.set_y_label('Relative Gain', 'dB')
        self.mon_spec1.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.mon_spec1.enable_autoscale(False)
        self.mon_spec1.enable_grid(True)
        self.mon_spec1.set_fft_average(0.2)
        self.mon_spec1.enable_axis_labels(True)
        self.mon_spec1.enable_control_panel(False)



        labels = ['ch1 A/RX2', 'Ch1 RF A/RX2', 'Ch2 RF B/RX1 (LO master)', 'Ch3 RF B/RX2', '',
            '', '', '', '', '']
        widths = [2, 2, 2, 2, 2,
            2, 2, 2, 2, 2]
        colors = ["blue", "red", "green", "black", "blue",
            "blue", "blue", "blue", "blue", "blue"]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.mon_spec1.set_line_label(i, "Data {0}".format(i))
            else:
                self.mon_spec1.set_line_label(i, labels[i])
            self.mon_spec1.set_line_width(i, widths[i])
            self.mon_spec1.set_line_color(i, colors[i])
            self.mon_spec1.set_line_alpha(i, alphas[i])

        self._mon_spec1_win = sip.wrapinstance(self.mon_spec1.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_3.addWidget(self._mon_spec1_win, 1, 2, 2, 1)
        for r in range(1, 3):
            self.tabs_grid_layout_3.setRowStretch(r, 1)
        for c in range(2, 3):
            self.tabs_grid_layout_3.setColumnStretch(c, 1)
        self.mon_spec0 = qtgui.freq_sink_c(
            4096, #size
            firdes.WIN_BLACKMAN_hARRIS, #wintype
            900000000.0, #fc
            samp_rate, #bw
            "MON LO0 ch0 - spectrum", #name
            1
        )
        self.mon_spec0.set_update_time(0.10)
        self.mon_spec0.set_y_axis(-140, 0)
        self.mon_spec0.set_y_label('Relative Gain', 'dB')
        self.mon_spec0.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.mon_spec0.enable_autoscale(False)
        self.mon_spec0.enable_grid(True)
        self.mon_spec0.set_fft_average(0.2)
        self.mon_spec0.enable_axis_labels(True)
        self.mon_spec0.enable_control_panel(False)



        labels = ['ch0 A/RX1', 'Ch1 RF A/RX2', 'Ch2 RF B/RX1 (LO master)', 'Ch3 RF B/RX2', '',
            '', '', '', '', '']
        widths = [2, 2, 2, 2, 2,
            2, 2, 2, 2, 2]
        colors = ["blue", "red", "green", "black", "blue",
            "blue", "blue", "blue", "blue", "blue"]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.mon_spec0.set_line_label(i, "Data {0}".format(i))
            else:
                self.mon_spec0.set_line_label(i, labels[i])
            self.mon_spec0.set_line_width(i, widths[i])
            self.mon_spec0.set_line_color(i, colors[i])
            self.mon_spec0.set_line_alpha(i, alphas[i])

        self._mon_spec0_win = sip.wrapinstance(self.mon_spec0.pyqwidget(), Qt.QWidget)
        self.tabs_grid_layout_3.addWidget(self._mon_spec0_win, 1, 0, 2, 1)
        for r in range(1, 3):
            self.tabs_grid_layout_3.setRowStretch(r, 1)
        for c in range(0, 1):
            self.tabs_grid_layout_3.setColumnStretch(c, 1)
        self.mon_snap_s2v3 = blocks.stream_to_vector(gr.sizeof_gr_complex*1, 8192)
        self.mon_snap_s2v2 = blocks.stream_to_vector(gr.sizeof_gr_complex*1, 8192)
        self.mon_snap_s2v1 = blocks.stream_to_vector(gr.sizeof_gr_complex*1, 8192)
        self.mon_snap_s2v0 = blocks.stream_to_vector(gr.sizeof_gr_complex*1, 8192)
        self.mon_snap_k1n3 = blocks.keep_one_in_n(gr.sizeof_gr_complex*8192, 25)
        self.mon_snap_k1n2 = blocks.keep_one_in_n(gr.sizeof_gr_complex*8192, 25)
        self.mon_snap_k1n1 = blocks.keep_one_in_n(gr.sizeof_gr_complex*8192, 25)
        self.mon_snap_k1n0 = blocks.keep_one_in_n(gr.sizeof_gr_complex*8192, 25)
        self.mon_s2v3 = blocks.stream_to_vector(gr.sizeof_gr_complex*1, 4096)
        self.mon_s2v2 = blocks.stream_to_vector(gr.sizeof_gr_complex*1, 4096)
        self.mon_s2v1 = blocks.stream_to_vector(gr.sizeof_gr_complex*1, 4096)
        self.mon_s2v0 = blocks.stream_to_vector(gr.sizeof_gr_complex*1, 4096)
        self.mon_probe3 = blocks.probe_signal_vc(8192)
        self.mon_probe2 = blocks.probe_signal_vc(8192)
        self.mon_probe1 = blocks.probe_signal_vc(8192)
        self.mon_probe0 = blocks.probe_signal_vc(8192)
        self._mon_lbl3_tool_bar = Qt.QToolBar(self)

        if None:
            self._mon_lbl3_formatter = None
        else:
            self._mon_lbl3_formatter = lambda x: str(x)

        self._mon_lbl3_tool_bar.addWidget(Qt.QLabel('LO3 ch3 B/RX2  5.8 GHz' + ": "))
        self._mon_lbl3_label = Qt.QLabel(str(self._mon_lbl3_formatter(self.mon_lbl3)))
        self._mon_lbl3_tool_bar.addWidget(self._mon_lbl3_label)
        self.tabs_grid_layout_3.addWidget(self._mon_lbl3_tool_bar, 3, 2, 1, 2)
        for r in range(3, 4):
            self.tabs_grid_layout_3.setRowStretch(r, 1)
        for c in range(2, 4):
            self.tabs_grid_layout_3.setColumnStretch(c, 1)
        self._mon_lbl2_tool_bar = Qt.QToolBar(self)

        if None:
            self._mon_lbl2_formatter = None
        else:
            self._mon_lbl2_formatter = lambda x: str(x)

        self._mon_lbl2_tool_bar.addWidget(Qt.QLabel('LO2 ch2 B/RX1  5.2 GHz' + ": "))
        self._mon_lbl2_label = Qt.QLabel(str(self._mon_lbl2_formatter(self.mon_lbl2)))
        self._mon_lbl2_tool_bar.addWidget(self._mon_lbl2_label)
        self.tabs_grid_layout_3.addWidget(self._mon_lbl2_tool_bar, 3, 0, 1, 2)
        for r in range(3, 4):
            self.tabs_grid_layout_3.setRowStretch(r, 1)
        for c in range(0, 2):
            self.tabs_grid_layout_3.setColumnStretch(c, 1)
        self._mon_lbl1_tool_bar = Qt.QToolBar(self)

        if None:
            self._mon_lbl1_formatter = None
        else:
            self._mon_lbl1_formatter = lambda x: str(x)

        self._mon_lbl1_tool_bar.addWidget(Qt.QLabel('LO1 ch1 A/RX2  2.4 GHz' + ": "))
        self._mon_lbl1_label = Qt.QLabel(str(self._mon_lbl1_formatter(self.mon_lbl1)))
        self._mon_lbl1_tool_bar.addWidget(self._mon_lbl1_label)
        self.tabs_grid_layout_3.addWidget(self._mon_lbl1_tool_bar, 0, 2, 1, 2)
        for r in range(0, 1):
            self.tabs_grid_layout_3.setRowStretch(r, 1)
        for c in range(2, 4):
            self.tabs_grid_layout_3.setColumnStretch(c, 1)
        self._mon_lbl0_tool_bar = Qt.QToolBar(self)

        if None:
            self._mon_lbl0_formatter = None
        else:
            self._mon_lbl0_formatter = lambda x: str(x)

        self._mon_lbl0_tool_bar.addWidget(Qt.QLabel('LO0 ch0 A/RX1  0.9 GHz' + ": "))
        self._mon_lbl0_label = Qt.QLabel(str(self._mon_lbl0_formatter(self.mon_lbl0)))
        self._mon_lbl0_tool_bar.addWidget(self._mon_lbl0_label)
        self.tabs_grid_layout_3.addWidget(self._mon_lbl0_tool_bar, 0, 0, 1, 2)
        for r in range(0, 1):
            self.tabs_grid_layout_3.setRowStretch(r, 1)
        for c in range(0, 2):
            self.tabs_grid_layout_3.setColumnStretch(c, 1)
        self.mon_k1n3 = blocks.keep_one_in_n(gr.sizeof_gr_complex*4096, 10)
        self.mon_k1n2 = blocks.keep_one_in_n(gr.sizeof_gr_complex*4096, 10)
        self.mon_k1n1 = blocks.keep_one_in_n(gr.sizeof_gr_complex*4096, 10)
        self.mon_k1n0 = blocks.keep_one_in_n(gr.sizeof_gr_complex*4096, 10)
        self._mode_state_tool_bar = Qt.QToolBar(self)

        if None:
            self._mode_state_formatter = None
        else:
            self._mode_state_formatter = lambda x: str(x)

        self._mode_state_tool_bar.addWidget(Qt.QLabel('mode_state' + ": "))
        self._mode_state_label = Qt.QLabel(str(self._mode_state_formatter(self.mode_state)))
        self._mode_state_tool_bar.addWidget(self._mode_state_label)
        self.top_grid_layout.addWidget(self._mode_state_tool_bar, 0, 1, 1, 3)
        for r in range(0, 1):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(1, 4):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.met_2_null3 = blocks.null_sink(gr.sizeof_float*1)
        self.met_2_null2 = blocks.null_sink(gr.sizeof_float*1)
        self.met_2_null1 = blocks.null_sink(gr.sizeof_float*1)
        self.met_2_null0 = blocks.null_sink(gr.sizeof_float*1)
        self.met_2 = doa.hop_phase_meter(4, 5800000000.0, samp_rate, tone_offset - disp_bw/2 + 10e3, tone_offset + disp_bw/2 - 10e3, 20, 20, 5, False, 0)
        self.met_1_null3 = blocks.null_sink(gr.sizeof_float*1)
        self.met_1_null2 = blocks.null_sink(gr.sizeof_float*1)
        self.met_1_null1 = blocks.null_sink(gr.sizeof_float*1)
        self.met_1_null0 = blocks.null_sink(gr.sizeof_float*1)
        self.met_1 = doa.hop_phase_meter(4, 5200000000.0, samp_rate, tone_offset - disp_bw/2 + 10e3, tone_offset + disp_bw/2 - 10e3, 20, 20, 5, False, 0)
        self.met_0_null3 = blocks.null_sink(gr.sizeof_float*1)
        self.met_0_null2 = blocks.null_sink(gr.sizeof_float*1)
        self.met_0_null1 = blocks.null_sink(gr.sizeof_float*1)
        self.met_0_null0 = blocks.null_sink(gr.sizeof_float*1)
        self.met_0 = doa.hop_phase_meter(4, 2400000000.0, samp_rate, tone_offset - disp_bw/2 + 10e3, tone_offset + disp_bw/2 - 10e3, 20, 20, 5, False, 0)
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
        self.connect((self.mon_k1n0, 0), (self.mon_v2s0, 0))
        self.connect((self.mon_k1n1, 0), (self.mon_v2s1, 0))
        self.connect((self.mon_k1n2, 0), (self.mon_v2s2, 0))
        self.connect((self.mon_k1n3, 0), (self.mon_v2s3, 0))
        self.connect((self.mon_s2v0, 0), (self.mon_k1n0, 0))
        self.connect((self.mon_s2v1, 0), (self.mon_k1n1, 0))
        self.connect((self.mon_s2v2, 0), (self.mon_k1n2, 0))
        self.connect((self.mon_s2v3, 0), (self.mon_k1n3, 0))
        self.connect((self.mon_snap_k1n0, 0), (self.mon_probe0, 0))
        self.connect((self.mon_snap_k1n1, 0), (self.mon_probe1, 0))
        self.connect((self.mon_snap_k1n2, 0), (self.mon_probe2, 0))
        self.connect((self.mon_snap_k1n3, 0), (self.mon_probe3, 0))
        self.connect((self.mon_snap_s2v0, 0), (self.mon_snap_k1n0, 0))
        self.connect((self.mon_snap_s2v1, 0), (self.mon_snap_k1n1, 0))
        self.connect((self.mon_snap_s2v2, 0), (self.mon_snap_k1n2, 0))
        self.connect((self.mon_snap_s2v3, 0), (self.mon_snap_k1n3, 0))
        self.connect((self.mon_v2s0, 0), (self.mon_spec0, 0))
        self.connect((self.mon_v2s0, 0), (self.mon_time0, 0))
        self.connect((self.mon_v2s1, 0), (self.mon_spec1, 0))
        self.connect((self.mon_v2s1, 0), (self.mon_time1, 0))
        self.connect((self.mon_v2s2, 0), (self.mon_spec2, 0))
        self.connect((self.mon_v2s2, 0), (self.mon_time2, 0))
        self.connect((self.mon_v2s3, 0), (self.mon_spec3, 0))
        self.connect((self.mon_v2s3, 0), (self.mon_time3, 0))
        self.connect((self.ph_meter, 0), (self.ph_meter_null0, 0))
        self.connect((self.ph_meter, 1), (self.ph_meter_null1, 0))
        self.connect((self.ph_meter, 2), (self.ph_meter_null2, 0))
        self.connect((self.ph_meter, 3), (self.ph_meter_null3, 0))
        self.connect((self.phase_correct_hopping_0, 0), (self.met_0, 0))
        self.connect((self.phase_correct_hopping_0, 2), (self.met_0, 2))
        self.connect((self.phase_correct_hopping_0, 3), (self.met_0, 3))
        self.connect((self.phase_correct_hopping_0, 1), (self.met_0, 1))
        self.connect((self.phase_correct_hopping_0, 0), (self.met_1, 0))
        self.connect((self.phase_correct_hopping_0, 1), (self.met_1, 1))
        self.connect((self.phase_correct_hopping_0, 3), (self.met_1, 3))
        self.connect((self.phase_correct_hopping_0, 2), (self.met_1, 2))
        self.connect((self.phase_correct_hopping_0, 1), (self.met_2, 1))
        self.connect((self.phase_correct_hopping_0, 0), (self.met_2, 0))
        self.connect((self.phase_correct_hopping_0, 3), (self.met_2, 3))
        self.connect((self.phase_correct_hopping_0, 2), (self.met_2, 2))
        self.connect((self.phase_correct_hopping_0, 2), (self.ph_meter, 2))
        self.connect((self.phase_correct_hopping_0, 1), (self.ph_meter, 1))
        self.connect((self.phase_correct_hopping_0, 3), (self.ph_meter, 3))
        self.connect((self.phase_correct_hopping_0, 0), (self.ph_meter, 0))
        self.connect((self.phase_correct_hopping_0, 0), (self.sw_mag_0, 0))
        self.connect((self.phase_correct_hopping_0, 1), (self.sw_mag_1, 0))
        self.connect((self.phase_correct_hopping_0, 2), (self.sw_mag_2, 0))
        self.connect((self.phase_correct_hopping_0, 3), (self.sw_mag_3, 0))
        self.connect((self.phase_correct_hopping_0, 3), (self.wave_sel, 3))
        self.connect((self.phase_correct_hopping_0, 0), (self.wave_sel, 0))
        self.connect((self.phase_correct_hopping_0, 1), (self.wave_sel, 1))
        self.connect((self.phase_correct_hopping_0, 2), (self.wave_sel, 2))
        self.connect((self.spec_sel, 0), (self.qtgui_freq_sink_x_0, 0))
        self.connect((self.spec_sel, 3), (self.qtgui_freq_sink_x_0, 3))
        self.connect((self.spec_sel, 1), (self.qtgui_freq_sink_x_0, 1))
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
        self.connect((self.twinrx_radio_source_0, 4), (self.mon_s2v0, 0))
        self.connect((self.twinrx_radio_source_0, 5), (self.mon_s2v1, 0))
        self.connect((self.twinrx_radio_source_0, 6), (self.mon_s2v2, 0))
        self.connect((self.twinrx_radio_source_0, 7), (self.mon_s2v3, 0))
        self.connect((self.twinrx_radio_source_0, 4), (self.mon_snap_s2v0, 0))
        self.connect((self.twinrx_radio_source_0, 5), (self.mon_snap_s2v1, 0))
        self.connect((self.twinrx_radio_source_0, 6), (self.mon_snap_s2v2, 0))
        self.connect((self.twinrx_radio_source_0, 7), (self.mon_snap_s2v3, 0))
        self.connect((self.twinrx_radio_source_0, 3), (self.spec_sel, 3))
        self.connect((self.twinrx_radio_source_0, 0), (self.spec_sel, 0))
        self.connect((self.twinrx_radio_source_0, 1), (self.spec_sel, 1))
        self.connect((self.twinrx_radio_source_0, 2), (self.spec_sel, 2))
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
        self.settings = Qt.QSettings("GNU Radio", "guru_switch")
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
        self.mon_spec0.set_frequency_range(900000000.0, self.samp_rate)
        self.mon_time0.set_samp_rate(self.samp_rate)
        self.mon_spec1.set_frequency_range(2400000000.0, self.samp_rate)
        self.mon_time1.set_samp_rate(self.samp_rate)
        self.mon_spec2.set_frequency_range(5200000000.0, self.samp_rate)
        self.mon_time2.set_samp_rate(self.samp_rate)
        self.mon_spec3.set_frequency_range(5800000000.0, self.samp_rate)
        self.mon_time3.set_samp_rate(self.samp_rate)

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

    def get_mon_lbl3(self):
        return self.mon_lbl3

    def set_mon_lbl3(self, mon_lbl3):
        self.mon_lbl3 = mon_lbl3
        Qt.QMetaObject.invokeMethod(self._mon_lbl3_label, "setText", Qt.Q_ARG("QString", self.mon_lbl3))

    def get_mon_lbl2(self):
        return self.mon_lbl2

    def set_mon_lbl2(self, mon_lbl2):
        self.mon_lbl2 = mon_lbl2
        Qt.QMetaObject.invokeMethod(self._mon_lbl2_label, "setText", Qt.Q_ARG("QString", self.mon_lbl2))

    def get_mon_lbl1(self):
        return self.mon_lbl1

    def set_mon_lbl1(self, mon_lbl1):
        self.mon_lbl1 = mon_lbl1
        Qt.QMetaObject.invokeMethod(self._mon_lbl1_label, "setText", Qt.Q_ARG("QString", self.mon_lbl1))

    def get_mon_lbl0(self):
        return self.mon_lbl0

    def set_mon_lbl0(self, mon_lbl0):
        self.mon_lbl0 = mon_lbl0
        Qt.QMetaObject.invokeMethod(self._mon_lbl0_label, "setText", Qt.Q_ARG("QString", self.mon_lbl0))

    def get_mode_state(self):
        return self.mode_state

    def set_mode_state(self, mode_state):
        self.mode_state = mode_state
        Qt.QMetaObject.invokeMethod(self._mode_state_label, "setText", Qt.Q_ARG("QString", self.mode_state))

    def get_mode(self):
        return self.mode

    def set_mode(self, mode):
        self.mode = mode
        self.twinrx_radio_source_0.set_mode(self.mode)
        self._mode_callback(self.mode)

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
                   'send: typical %.1f ms, worst %.1f ms (limit 5.5 ms)'
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
            self._show_lbl.setText('SHOWING:  %g GHz  (LAB TONE band) -- its 5 ms dwells only, %s%s'
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
                _v.setText('%+8.3f deg   (average of the last 20 dwells)' % row[_c])
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
            _ph = _m.recent(20)
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

def snipfcn_snippet_switch(self):
    # MON <-> DF: status twice a second from the engine's own counters (never a
    # radio read here: it would wait behind the timed commands), and the control
    # API on udp://:0 ('mode df' | 'mode mon' | 'status').
    import json
    import socket
    import threading
    import numpy as np
    from PyQt5 import QtCore

    _src = self.twinrx_radio_source_0
    _FS = float(self.samp_rate)
    _MONF = [900000000.0, 2400000000.0, 5200000000.0, 5800000000.0]
    self._sw_api_mode = None

    def _readout(x):
        N = len(x)
        S = np.abs(np.fft.fft(x * np.hanning(N).astype(np.float32))) ** 2
        F = np.fft.fftfreq(N, 1.0 / _FS)
        k = int(np.argmax(np.where(np.abs(F) >= 20e3, S, 0)))
        return float(F[k]), float(10 * np.log10(S[k] / (np.median(S) + 1e-30))), float(np.abs(x).max())

    def _sw_poll():
        mi = _src.get_mode_info()
        last = mi["last_request_to_dwell_ms"]
        txt = ("NOW %s%s | switches %d (not used %d) | last: to %s, request -> first dwell %s, %s | "
               "samples: MON %d, DF %d" % (
                   mi["mode"], "" if mi["requested"] == mi["mode"] else "  (switching to %s)" % mi["requested"],
                   mi["switches"], mi["switches_bad"], mi["last_switch_to"] or "-",
                   "%.1f ms" % last if last else "-", mi["last_switch_ok"] if mi["switches"] else "-",
                   mi["mon_dwell_samples"], mi["df_dwell_samples"]))
        self.set_mode_state(txt)
        for c in range(4):
            lk = mi["mon_lock"][c]
            s = "%s | MON samples (engine) %d, MON slots used %d, not used %d" % (
                "LOCKED" if lk else ("LOCK NOT READ YET" if lk is None else "NOT LOCKED"),
                mi["mon_dwell_samples"], mi["mon_slots_verified"], mi["mon_slots_not_used"])
            if mi["mode"] != "MON":
                s = "not in MON (mode %s) | last: " % mi["mode"] + s
            x = np.asarray(getattr(self, "mon_probe%d" % c).level(), dtype=np.complex64)
            if len(x) and mi["mode"] == "MON":
                # a block that overlaps a switch gap (the zeros of DF time) is no MON reading
                if np.count_nonzero(x == 0) > 16:
                    s += " | newest block overlaps a switch: not read"
                else:
                    f, db, pk = _readout(x)
                    s += " | newest %d samples: %s %+.1f kHz %.1f dB | ADC peak %.3f%s" % (
                        len(x), "TONE" if db >= 30 else "no tone, strongest line", f / 1e3, db, pk,
                        "  OVERLOAD" if pk > 0.5 else "")
            getattr(self, "set_mon_lbl%d" % c)(s)
        # the API may have changed the mode: show it on the selector (GUI thread)
        if self._sw_api_mode and self._sw_api_mode != self.mode:
            self.set_mode(self._sw_api_mode)
        self._sw_api_mode = None

    self._sw_timer = QtCore.QTimer()
    self._sw_timer.timeout.connect(_sw_poll)
    self._sw_timer.start(500)

    def _api():
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sk.bind(("", 0))
        except OSError as e:
            print("[switch] control API NOT started (%s)" % e)
            return
        print("[switch] control API on udp://:0  ('mode df' | 'mode mon' | 'status')")
        while True:
            data, peer = sk.recvfrom(256)
            cmd = data.decode(errors="ignore").split()
            try:
                if len(cmd) == 2 and cmd[0] == "mode" and cmd[1] in ("df", "mon"):
                    _src.set_mode(cmd[1])            # the engine takes it at the next slot
                    self._sw_api_mode = cmd[1]       # the selector follows in the GUI thread
                    reply = {"ok": True, "requested": cmd[1]}
                elif cmd and cmd[0] == "status":
                    reply = {"ok": True, "mode": _src.get_mode_info(), "schedule": _src.get_schedule_stats()}
                else:
                    reply = {"ok": False, "error": "commands: 'mode df' | 'mode mon' | 'status'"}
            except Exception as e:
                reply = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
            sk.sendto(json.dumps(reply, default=str).encode(), peer)

    if False:
        threading.Thread(target=_api, daemon=True).start()
    else:
        print("[switch] no control API: the mode changes only with the MODE selector")


def snippets_main_after_init(tb):
    snipfcn_snippet_lo_config(tb)

def snippets_main_after_start(tb):
    snipfcn_snippet_switch(tb)
    snipfcn_snippet_hop(tb)
    snipfcn_snippet_lo_watch(tb)

def snippets_main_after_stop(tb):
    snipfcn_snippet_lo_stop(tb)




def main(top_block_cls=guru_switch, options=None):

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
