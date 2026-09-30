#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Guru MON: USRP-2945, every channel its own LO and band (monitoring)
# Author: shankar
# Description: Monitoring: 4 independent LOs
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
from gnuradio import gr
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import uhd
import time
from gnuradio.qtgui import Range, RangeWidget
import mon_meter
import mon_tools

from gnuradio import qtgui

class guru_mon(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "Guru MON: USRP-2945, every channel its own LO and band (monitoring)")
        Qt.QWidget.__init__(self)
        self.setWindowTitle("Guru MON: USRP-2945, every channel its own LO and band (monitoring)")
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

        self.settings = Qt.QSettings("GNU Radio", "guru_mon")

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
        self.tone_band = tone_band = 2400000000.0
        self.tx_state = tx_state = mon_tools.tx_freq(tone_band)
        self.subdev = subdev = 'A:0 A:1 B:0 B:1'
        self.samp_rate = samp_rate = 2000000
        self.mon3 = mon3 = 'starting'
        self.mon2 = mon2 = 'starting'
        self.mon1 = mon1 = 'starting'
        self.mon0 = mon0 = 'starting'
        self.g3 = g3 = 69.0
        self.g2 = g2 = 60.0
        self.g1 = g1 = 46.0
        self.g0 = g0 = 40.0
        self.f3 = f3 = 5800000000.0
        self.f2 = f2 = 5200000000.0
        self.f1 = f1 = 2400000000.0
        self.f0 = f0 = 900000000.0

        ##################################################
        # Blocks
        ##################################################
        self._g3_range = Range(0, 93, 1, 69.0, 100)
        self._g3_win = RangeWidget(self._g3_range, self.set_g3, 'ch3 RX gain (dB)', "counter_slider", float)
        self.top_grid_layout.addWidget(self._g3_win, 6, 2, 1, 1)
        for r in range(6, 7):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(2, 3):
            self.top_grid_layout.setColumnStretch(c, 1)
        self._g2_range = Range(0, 93, 1, 60.0, 100)
        self._g2_win = RangeWidget(self._g2_range, self.set_g2, 'ch2 RX gain (dB)', "counter_slider", float)
        self.top_grid_layout.addWidget(self._g2_win, 6, 0, 1, 1)
        for r in range(6, 7):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(0, 1):
            self.top_grid_layout.setColumnStretch(c, 1)
        self._g1_range = Range(0, 93, 1, 46.0, 100)
        self._g1_win = RangeWidget(self._g1_range, self.set_g1, 'ch1 RX gain (dB)', "counter_slider", float)
        self.top_grid_layout.addWidget(self._g1_win, 2, 2, 1, 1)
        for r in range(2, 3):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(2, 3):
            self.top_grid_layout.setColumnStretch(c, 1)
        self._g0_range = Range(0, 93, 1, 40.0, 100)
        self._g0_win = RangeWidget(self._g0_range, self.set_g0, 'ch0 RX gain (dB)', "counter_slider", float)
        self.top_grid_layout.addWidget(self._g0_win, 2, 0, 1, 1)
        for r in range(2, 3):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(0, 1):
            self.top_grid_layout.setColumnStretch(c, 1)
        self._f3_tool_bar = Qt.QToolBar(self)
        self._f3_tool_bar.addWidget(Qt.QLabel('ch3 frequency (Hz)' + ": "))
        self._f3_line_edit = Qt.QLineEdit(str(self.f3))
        self._f3_tool_bar.addWidget(self._f3_line_edit)
        self._f3_line_edit.returnPressed.connect(
            lambda: self.set_f3(eng_notation.str_to_num(str(self._f3_line_edit.text()))))
        self.top_grid_layout.addWidget(self._f3_tool_bar, 6, 3, 1, 1)
        for r in range(6, 7):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(3, 4):
            self.top_grid_layout.setColumnStretch(c, 1)
        self._f2_tool_bar = Qt.QToolBar(self)
        self._f2_tool_bar.addWidget(Qt.QLabel('ch2 frequency (Hz)' + ": "))
        self._f2_line_edit = Qt.QLineEdit(str(self.f2))
        self._f2_tool_bar.addWidget(self._f2_line_edit)
        self._f2_line_edit.returnPressed.connect(
            lambda: self.set_f2(eng_notation.str_to_num(str(self._f2_line_edit.text()))))
        self.top_grid_layout.addWidget(self._f2_tool_bar, 6, 1, 1, 1)
        for r in range(6, 7):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(1, 2):
            self.top_grid_layout.setColumnStretch(c, 1)
        self._f1_tool_bar = Qt.QToolBar(self)
        self._f1_tool_bar.addWidget(Qt.QLabel('ch1 frequency (Hz)' + ": "))
        self._f1_line_edit = Qt.QLineEdit(str(self.f1))
        self._f1_tool_bar.addWidget(self._f1_line_edit)
        self._f1_line_edit.returnPressed.connect(
            lambda: self.set_f1(eng_notation.str_to_num(str(self._f1_line_edit.text()))))
        self.top_grid_layout.addWidget(self._f1_tool_bar, 2, 3, 1, 1)
        for r in range(2, 3):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(3, 4):
            self.top_grid_layout.setColumnStretch(c, 1)
        self._f0_tool_bar = Qt.QToolBar(self)
        self._f0_tool_bar.addWidget(Qt.QLabel('ch0 frequency (Hz)' + ": "))
        self._f0_line_edit = Qt.QLineEdit(str(self.f0))
        self._f0_tool_bar.addWidget(self._f0_line_edit)
        self._f0_line_edit.returnPressed.connect(
            lambda: self.set_f0(eng_notation.str_to_num(str(self._f0_line_edit.text()))))
        self.top_grid_layout.addWidget(self._f0_tool_bar, 2, 1, 1, 1)
        for r in range(2, 3):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(1, 2):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.uhd_usrp_source_0 = uhd.usrp_source(
            ",".join(("addr=192.168.10.2", "", "master_clock_rate=200e6")),
            uhd.stream_args(
                cpu_format="fc32",
                args='',
                channels=list(range(0,4)),
            ),
        )
        self.uhd_usrp_source_0.set_subdev_spec(subdev, 0)
        self.uhd_usrp_source_0.set_time_source('internal', 0)
        self.uhd_usrp_source_0.set_clock_source('internal', 0)
        self.uhd_usrp_source_0.set_center_freq(f0, 0)
        self.uhd_usrp_source_0.set_gain(g0, 0)
        self.uhd_usrp_source_0.set_antenna('RX1', 0)
        self.uhd_usrp_source_0.set_lo_source('internal', uhd.ALL_LOS, 0)
        self.uhd_usrp_source_0.set_lo_export_enabled(False, uhd.ALL_LOS, 0)
        self.uhd_usrp_source_0.set_center_freq(f1, 1)
        self.uhd_usrp_source_0.set_gain(g1, 1)
        self.uhd_usrp_source_0.set_antenna('RX2', 1)
        self.uhd_usrp_source_0.set_lo_source('internal', uhd.ALL_LOS, 1)
        self.uhd_usrp_source_0.set_lo_export_enabled(False, uhd.ALL_LOS, 1)
        self.uhd_usrp_source_0.set_center_freq(f2, 2)
        self.uhd_usrp_source_0.set_gain(g2, 2)
        self.uhd_usrp_source_0.set_antenna('RX1', 2)
        self.uhd_usrp_source_0.set_lo_source('internal', uhd.ALL_LOS, 2)
        self.uhd_usrp_source_0.set_lo_export_enabled(False, uhd.ALL_LOS, 2)
        self.uhd_usrp_source_0.set_center_freq(f3, 3)
        self.uhd_usrp_source_0.set_gain(g3, 3)
        self.uhd_usrp_source_0.set_antenna('RX2', 3)
        self.uhd_usrp_source_0.set_lo_source('internal', uhd.ALL_LOS, 3)
        self.uhd_usrp_source_0.set_lo_export_enabled(False, uhd.ALL_LOS, 3)
        self.uhd_usrp_source_0.set_clock_rate(200e6, uhd.ALL_MBOARDS)
        self.uhd_usrp_source_0.set_samp_rate(samp_rate)
        # No synchronization enforced.
        self._tx_state_tool_bar = Qt.QToolBar(self)

        if None:
            self._tx_state_formatter = None
        else:
            self._tx_state_formatter = lambda x: str(x)

        self._tx_state_tool_bar.addWidget(Qt.QLabel('TRANSMITTER' + ": "))
        self._tx_state_label = Qt.QLabel(str(self._tx_state_formatter(self.tx_state)))
        self._tx_state_tool_bar.addWidget(self._tx_state_label)
        self.top_grid_layout.addWidget(self._tx_state_tool_bar, 0, 2, 1, 2)
        for r in range(0, 1):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(2, 4):
            self.top_grid_layout.setColumnStretch(c, 1)
        # Create the options list
        self._tone_band_options = [900000000.0, 2400000000.0, 5200000000.0, 5800000000.0]
        # Create the labels list
        self._tone_band_labels = ['900 MHz (ch0)', '2400 MHz (ch1)', '5200 MHz (ch2)', '5800 MHz (ch3)']
        # Create the combo box
        self._tone_band_tool_bar = Qt.QToolBar(self)
        self._tone_band_tool_bar.addWidget(Qt.QLabel('LAB TONE (HackRF) BAND - only tells the HackRF where to send' + ": "))
        self._tone_band_combo_box = Qt.QComboBox()
        self._tone_band_tool_bar.addWidget(self._tone_band_combo_box)
        for _label in self._tone_band_labels: self._tone_band_combo_box.addItem(_label)
        self._tone_band_callback = lambda i: Qt.QMetaObject.invokeMethod(self._tone_band_combo_box, "setCurrentIndex", Qt.Q_ARG("int", self._tone_band_options.index(i)))
        self._tone_band_callback(self.tone_band)
        self._tone_band_combo_box.currentIndexChanged.connect(
            lambda i: self.set_tone_band(self._tone_band_options[i]))
        # Create the radio buttons
        self.top_grid_layout.addWidget(self._tone_band_tool_bar, 0, 0, 1, 2)
        for r in range(0, 1):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(0, 2):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.time3 = qtgui.time_sink_c(
            400, #size
            samp_rate, #samp_rate
            "LO3 ch3 - time (real samples, I and Q)", #name
            1 #number of inputs
        )
        self.time3.set_update_time(0.10)
        self.time3.set_y_axis(-0.1, 0.1)

        self.time3.set_y_label('Amplitude', "")

        self.time3.enable_tags(False)
        self.time3.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.time3.enable_autoscale(True)
        self.time3.enable_grid(True)
        self.time3.enable_axis_labels(True)
        self.time3.enable_control_panel(False)
        self.time3.enable_stem_plot(False)


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
                    self.time3.set_line_label(i, "Re{{Data {0}}}".format(i/2))
                else:
                    self.time3.set_line_label(i, "Im{{Data {0}}}".format(i/2))
            else:
                self.time3.set_line_label(i, labels[i])
            self.time3.set_line_width(i, widths[i])
            self.time3.set_line_color(i, colors[i])
            self.time3.set_line_style(i, styles[i])
            self.time3.set_line_marker(i, markers[i])
            self.time3.set_line_alpha(i, alphas[i])

        self._time3_win = sip.wrapinstance(self.time3.pyqwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._time3_win, 7, 3, 2, 1)
        for r in range(7, 9):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(3, 4):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.time2 = qtgui.time_sink_c(
            400, #size
            samp_rate, #samp_rate
            "LO2 ch2 - time (real samples, I and Q)", #name
            1 #number of inputs
        )
        self.time2.set_update_time(0.10)
        self.time2.set_y_axis(-0.1, 0.1)

        self.time2.set_y_label('Amplitude', "")

        self.time2.enable_tags(False)
        self.time2.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.time2.enable_autoscale(True)
        self.time2.enable_grid(True)
        self.time2.enable_axis_labels(True)
        self.time2.enable_control_panel(False)
        self.time2.enable_stem_plot(False)


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
                    self.time2.set_line_label(i, "Re{{Data {0}}}".format(i/2))
                else:
                    self.time2.set_line_label(i, "Im{{Data {0}}}".format(i/2))
            else:
                self.time2.set_line_label(i, labels[i])
            self.time2.set_line_width(i, widths[i])
            self.time2.set_line_color(i, colors[i])
            self.time2.set_line_style(i, styles[i])
            self.time2.set_line_marker(i, markers[i])
            self.time2.set_line_alpha(i, alphas[i])

        self._time2_win = sip.wrapinstance(self.time2.pyqwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._time2_win, 7, 1, 2, 1)
        for r in range(7, 9):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(1, 2):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.time1 = qtgui.time_sink_c(
            400, #size
            samp_rate, #samp_rate
            "LO1 ch1 - time (real samples, I and Q)", #name
            1 #number of inputs
        )
        self.time1.set_update_time(0.10)
        self.time1.set_y_axis(-0.1, 0.1)

        self.time1.set_y_label('Amplitude', "")

        self.time1.enable_tags(False)
        self.time1.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.time1.enable_autoscale(True)
        self.time1.enable_grid(True)
        self.time1.enable_axis_labels(True)
        self.time1.enable_control_panel(False)
        self.time1.enable_stem_plot(False)


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
                    self.time1.set_line_label(i, "Re{{Data {0}}}".format(i/2))
                else:
                    self.time1.set_line_label(i, "Im{{Data {0}}}".format(i/2))
            else:
                self.time1.set_line_label(i, labels[i])
            self.time1.set_line_width(i, widths[i])
            self.time1.set_line_color(i, colors[i])
            self.time1.set_line_style(i, styles[i])
            self.time1.set_line_marker(i, markers[i])
            self.time1.set_line_alpha(i, alphas[i])

        self._time1_win = sip.wrapinstance(self.time1.pyqwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._time1_win, 3, 3, 2, 1)
        for r in range(3, 5):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(3, 4):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.time0 = qtgui.time_sink_c(
            400, #size
            samp_rate, #samp_rate
            "LO0 ch0 - time (real samples, I and Q)", #name
            1 #number of inputs
        )
        self.time0.set_update_time(0.10)
        self.time0.set_y_axis(-0.1, 0.1)

        self.time0.set_y_label('Amplitude', "")

        self.time0.enable_tags(False)
        self.time0.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, "")
        self.time0.enable_autoscale(True)
        self.time0.enable_grid(True)
        self.time0.enable_axis_labels(True)
        self.time0.enable_control_panel(False)
        self.time0.enable_stem_plot(False)


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
                    self.time0.set_line_label(i, "Re{{Data {0}}}".format(i/2))
                else:
                    self.time0.set_line_label(i, "Im{{Data {0}}}".format(i/2))
            else:
                self.time0.set_line_label(i, labels[i])
            self.time0.set_line_width(i, widths[i])
            self.time0.set_line_color(i, colors[i])
            self.time0.set_line_style(i, styles[i])
            self.time0.set_line_marker(i, markers[i])
            self.time0.set_line_alpha(i, alphas[i])

        self._time0_win = sip.wrapinstance(self.time0.pyqwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._time0_win, 3, 1, 2, 1)
        for r in range(3, 5):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(1, 2):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.spec3 = qtgui.freq_sink_c(
            4096, #size
            firdes.WIN_BLACKMAN_hARRIS, #wintype
            f3, #fc
            samp_rate, #bw
            "LO3 ch3 - spectrum", #name
            1
        )
        self.spec3.set_update_time(0.10)
        self.spec3.set_y_axis(-140, 0)
        self.spec3.set_y_label('Relative Gain', 'dB')
        self.spec3.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.spec3.enable_autoscale(False)
        self.spec3.enable_grid(True)
        self.spec3.set_fft_average(0.2)
        self.spec3.enable_axis_labels(True)
        self.spec3.enable_control_panel(False)



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
                self.spec3.set_line_label(i, "Data {0}".format(i))
            else:
                self.spec3.set_line_label(i, labels[i])
            self.spec3.set_line_width(i, widths[i])
            self.spec3.set_line_color(i, colors[i])
            self.spec3.set_line_alpha(i, alphas[i])

        self._spec3_win = sip.wrapinstance(self.spec3.pyqwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._spec3_win, 7, 2, 2, 1)
        for r in range(7, 9):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(2, 3):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.spec2 = qtgui.freq_sink_c(
            4096, #size
            firdes.WIN_BLACKMAN_hARRIS, #wintype
            f2, #fc
            samp_rate, #bw
            "LO2 ch2 - spectrum", #name
            1
        )
        self.spec2.set_update_time(0.10)
        self.spec2.set_y_axis(-140, 0)
        self.spec2.set_y_label('Relative Gain', 'dB')
        self.spec2.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.spec2.enable_autoscale(False)
        self.spec2.enable_grid(True)
        self.spec2.set_fft_average(0.2)
        self.spec2.enable_axis_labels(True)
        self.spec2.enable_control_panel(False)



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
                self.spec2.set_line_label(i, "Data {0}".format(i))
            else:
                self.spec2.set_line_label(i, labels[i])
            self.spec2.set_line_width(i, widths[i])
            self.spec2.set_line_color(i, colors[i])
            self.spec2.set_line_alpha(i, alphas[i])

        self._spec2_win = sip.wrapinstance(self.spec2.pyqwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._spec2_win, 7, 0, 2, 1)
        for r in range(7, 9):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(0, 1):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.spec1 = qtgui.freq_sink_c(
            4096, #size
            firdes.WIN_BLACKMAN_hARRIS, #wintype
            f1, #fc
            samp_rate, #bw
            "LO1 ch1 - spectrum", #name
            1
        )
        self.spec1.set_update_time(0.10)
        self.spec1.set_y_axis(-140, 0)
        self.spec1.set_y_label('Relative Gain', 'dB')
        self.spec1.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.spec1.enable_autoscale(False)
        self.spec1.enable_grid(True)
        self.spec1.set_fft_average(0.2)
        self.spec1.enable_axis_labels(True)
        self.spec1.enable_control_panel(False)



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
                self.spec1.set_line_label(i, "Data {0}".format(i))
            else:
                self.spec1.set_line_label(i, labels[i])
            self.spec1.set_line_width(i, widths[i])
            self.spec1.set_line_color(i, colors[i])
            self.spec1.set_line_alpha(i, alphas[i])

        self._spec1_win = sip.wrapinstance(self.spec1.pyqwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._spec1_win, 3, 2, 2, 1)
        for r in range(3, 5):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(2, 3):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.spec0 = qtgui.freq_sink_c(
            4096, #size
            firdes.WIN_BLACKMAN_hARRIS, #wintype
            f0, #fc
            samp_rate, #bw
            "LO0 ch0 - spectrum", #name
            1
        )
        self.spec0.set_update_time(0.10)
        self.spec0.set_y_axis(-140, 0)
        self.spec0.set_y_label('Relative Gain', 'dB')
        self.spec0.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.spec0.enable_autoscale(False)
        self.spec0.enable_grid(True)
        self.spec0.set_fft_average(0.2)
        self.spec0.enable_axis_labels(True)
        self.spec0.enable_control_panel(False)



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
                self.spec0.set_line_label(i, "Data {0}".format(i))
            else:
                self.spec0.set_line_label(i, labels[i])
            self.spec0.set_line_width(i, widths[i])
            self.spec0.set_line_color(i, colors[i])
            self.spec0.set_line_alpha(i, alphas[i])

        self._spec0_win = sip.wrapinstance(self.spec0.pyqwidget(), Qt.QWidget)
        self.top_grid_layout.addWidget(self._spec0_win, 3, 0, 2, 1)
        for r in range(3, 5):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(0, 1):
            self.top_grid_layout.setColumnStretch(c, 1)
        self.mon_meter = mon_meter.blk(nch=4, keep=8192)
        self._mon3_tool_bar = Qt.QToolBar(self)

        if None:
            self._mon3_formatter = None
        else:
            self._mon3_formatter = lambda x: str(x)

        self._mon3_tool_bar.addWidget(Qt.QLabel('LO3  ch3 B/RX2' + ": "))
        self._mon3_label = Qt.QLabel(str(self._mon3_formatter(self.mon3)))
        self._mon3_tool_bar.addWidget(self._mon3_label)
        self.top_grid_layout.addWidget(self._mon3_tool_bar, 5, 2, 1, 2)
        for r in range(5, 6):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(2, 4):
            self.top_grid_layout.setColumnStretch(c, 1)
        self._mon2_tool_bar = Qt.QToolBar(self)

        if None:
            self._mon2_formatter = None
        else:
            self._mon2_formatter = lambda x: str(x)

        self._mon2_tool_bar.addWidget(Qt.QLabel('LO2  ch2 B/RX1' + ": "))
        self._mon2_label = Qt.QLabel(str(self._mon2_formatter(self.mon2)))
        self._mon2_tool_bar.addWidget(self._mon2_label)
        self.top_grid_layout.addWidget(self._mon2_tool_bar, 5, 0, 1, 2)
        for r in range(5, 6):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(0, 2):
            self.top_grid_layout.setColumnStretch(c, 1)
        self._mon1_tool_bar = Qt.QToolBar(self)

        if None:
            self._mon1_formatter = None
        else:
            self._mon1_formatter = lambda x: str(x)

        self._mon1_tool_bar.addWidget(Qt.QLabel('LO1  ch1 A/RX2' + ": "))
        self._mon1_label = Qt.QLabel(str(self._mon1_formatter(self.mon1)))
        self._mon1_tool_bar.addWidget(self._mon1_label)
        self.top_grid_layout.addWidget(self._mon1_tool_bar, 1, 2, 1, 2)
        for r in range(1, 2):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(2, 4):
            self.top_grid_layout.setColumnStretch(c, 1)
        self._mon0_tool_bar = Qt.QToolBar(self)

        if None:
            self._mon0_formatter = None
        else:
            self._mon0_formatter = lambda x: str(x)

        self._mon0_tool_bar.addWidget(Qt.QLabel('LO0  ch0 A/RX1' + ": "))
        self._mon0_label = Qt.QLabel(str(self._mon0_formatter(self.mon0)))
        self._mon0_tool_bar.addWidget(self._mon0_label)
        self.top_grid_layout.addWidget(self._mon0_tool_bar, 1, 0, 1, 2)
        for r in range(1, 2):
            self.top_grid_layout.setRowStretch(r, 1)
        for c in range(0, 2):
            self.top_grid_layout.setColumnStretch(c, 1)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.uhd_usrp_source_0, 1), (self.mon_meter, 1))
        self.connect((self.uhd_usrp_source_0, 3), (self.mon_meter, 3))
        self.connect((self.uhd_usrp_source_0, 2), (self.mon_meter, 2))
        self.connect((self.uhd_usrp_source_0, 0), (self.mon_meter, 0))
        self.connect((self.uhd_usrp_source_0, 0), (self.spec0, 0))
        self.connect((self.uhd_usrp_source_0, 1), (self.spec1, 0))
        self.connect((self.uhd_usrp_source_0, 2), (self.spec2, 0))
        self.connect((self.uhd_usrp_source_0, 3), (self.spec3, 0))
        self.connect((self.uhd_usrp_source_0, 0), (self.time0, 0))
        self.connect((self.uhd_usrp_source_0, 1), (self.time1, 0))
        self.connect((self.uhd_usrp_source_0, 2), (self.time2, 0))
        self.connect((self.uhd_usrp_source_0, 3), (self.time3, 0))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("GNU Radio", "guru_mon")
        self.settings.setValue("geometry", self.saveGeometry())
        event.accept()

    def get_tone_band(self):
        return self.tone_band

    def set_tone_band(self, tone_band):
        self.tone_band = tone_band
        self._tone_band_callback(self.tone_band)
        self.set_tx_state(self._tx_state_formatter(mon_tools.tx_freq(self.tone_band)))

    def get_tx_state(self):
        return self.tx_state

    def set_tx_state(self, tx_state):
        self.tx_state = tx_state
        Qt.QMetaObject.invokeMethod(self._tx_state_label, "setText", Qt.Q_ARG("QString", self.tx_state))

    def get_subdev(self):
        return self.subdev

    def set_subdev(self, subdev):
        self.subdev = subdev

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.uhd_usrp_source_0.set_samp_rate(self.samp_rate)
        self.spec0.set_frequency_range(self.f0, self.samp_rate)
        self.time0.set_samp_rate(self.samp_rate)
        self.spec1.set_frequency_range(self.f1, self.samp_rate)
        self.time1.set_samp_rate(self.samp_rate)
        self.spec2.set_frequency_range(self.f2, self.samp_rate)
        self.time2.set_samp_rate(self.samp_rate)
        self.spec3.set_frequency_range(self.f3, self.samp_rate)
        self.time3.set_samp_rate(self.samp_rate)

    def get_mon3(self):
        return self.mon3

    def set_mon3(self, mon3):
        self.mon3 = mon3
        Qt.QMetaObject.invokeMethod(self._mon3_label, "setText", Qt.Q_ARG("QString", self.mon3))

    def get_mon2(self):
        return self.mon2

    def set_mon2(self, mon2):
        self.mon2 = mon2
        Qt.QMetaObject.invokeMethod(self._mon2_label, "setText", Qt.Q_ARG("QString", self.mon2))

    def get_mon1(self):
        return self.mon1

    def set_mon1(self, mon1):
        self.mon1 = mon1
        Qt.QMetaObject.invokeMethod(self._mon1_label, "setText", Qt.Q_ARG("QString", self.mon1))

    def get_mon0(self):
        return self.mon0

    def set_mon0(self, mon0):
        self.mon0 = mon0
        Qt.QMetaObject.invokeMethod(self._mon0_label, "setText", Qt.Q_ARG("QString", self.mon0))

    def get_g3(self):
        return self.g3

    def set_g3(self, g3):
        self.g3 = g3
        self.uhd_usrp_source_0.set_gain(self.g3, 3)

    def get_g2(self):
        return self.g2

    def set_g2(self, g2):
        self.g2 = g2
        self.uhd_usrp_source_0.set_gain(self.g2, 2)

    def get_g1(self):
        return self.g1

    def set_g1(self, g1):
        self.g1 = g1
        self.uhd_usrp_source_0.set_gain(self.g1, 1)

    def get_g0(self):
        return self.g0

    def set_g0(self, g0):
        self.g0 = g0
        self.uhd_usrp_source_0.set_gain(self.g0, 0)

    def get_f3(self):
        return self.f3

    def set_f3(self, f3):
        self.f3 = f3
        self.uhd_usrp_source_0.set_center_freq(self.f3, 3)
        Qt.QMetaObject.invokeMethod(self._f3_line_edit, "setText", Qt.Q_ARG("QString", eng_notation.num_to_str(self.f3)))
        self.spec3.set_frequency_range(self.f3, self.samp_rate)

    def get_f2(self):
        return self.f2

    def set_f2(self, f2):
        self.f2 = f2
        self.uhd_usrp_source_0.set_center_freq(self.f2, 2)
        Qt.QMetaObject.invokeMethod(self._f2_line_edit, "setText", Qt.Q_ARG("QString", eng_notation.num_to_str(self.f2)))
        self.spec2.set_frequency_range(self.f2, self.samp_rate)

    def get_f1(self):
        return self.f1

    def set_f1(self, f1):
        self.f1 = f1
        self.uhd_usrp_source_0.set_center_freq(self.f1, 1)
        Qt.QMetaObject.invokeMethod(self._f1_line_edit, "setText", Qt.Q_ARG("QString", eng_notation.num_to_str(self.f1)))
        self.spec1.set_frequency_range(self.f1, self.samp_rate)

    def get_f0(self):
        return self.f0

    def set_f0(self, f0):
        self.f0 = f0
        self.uhd_usrp_source_0.set_center_freq(self.f0, 0)
        Qt.QMetaObject.invokeMethod(self._f0_line_edit, "setText", Qt.Q_ARG("QString", eng_notation.num_to_str(self.f0)))
        self.spec0.set_frequency_range(self.f0, self.samp_rate)

def snipfcn_snippet_mon_setup(self):
    # MON mode, in order: export off, all LOs internal, tune each channel twice
    self._mon_setup = mon_tools.mon_setup(self.uhd_usrp_source_0, [self.f0, self.f1, self.f2, self.f3], [self.g0, self.g1, self.g2, self.g3])

def snipfcn_snippet_mon_poll(self):
    # Twice a second: every channel's own lock sensor, samples counted, stream
    # breaks, strongest line of the newest 8192 samples, ADC peak. Every 5 s the
    # same line goes to the log.
    import time
    from PyQt5 import QtCore

    self._mon_last_log = 0.0
    FS = float(self.samp_rate)

    def _mon_poll():
        m = self.mon_meter
        now = time.monotonic()
        el = (now - m.t_first) if m.t_first else 0.0
        log = now - self._mon_last_log >= 5.0
        for c in range(4):
            lk = mon_tools.lo_locked(self.uhd_usrp_source_0, c)
            lock = "LOCKED" if lk else ("LOCK UNKNOWN" if lk is None else "NOT LOCKED")
            brk = max(m.rx_time_tags[c] - 1, 0)
            txt = "%s | %.4f GHz | samples %d (%.3f MS/s) | stream breaks %d" % (
                lock, self.uhd_usrp_source_0.get_center_freq(c) / 1e9, m.count[c],
                (m.count[c] / el / 1e6) if el > 0 else 0.0, brk)
            x = m.snap[c]
            if x is not None:
                r = mon_tools.readout(x, FS)
                txt += " | newest %d samples: %s %+.1f kHz %.1f dB | ADC peak %.3f%s" % (len(x),
                    "TONE" if r["tone"] else "no tone, strongest line", r["f"] / 1e3, r["db"],
                    r["peak"], "  OVERLOAD" if r["peak"] > 0.5 else "")
            getattr(self, "set_mon%d" % c)(txt)
            if log:
                print("[mon] %s ch%d %s" % (time.strftime("%H:%M:%S"), c, txt))
        if log:
            self._mon_last_log = now
        m.request()

    self._mon_timer = QtCore.QTimer()
    self._mon_timer.timeout.connect(_mon_poll)
    self._mon_timer.start(500)


def snippets_main_after_init(tb):
    snipfcn_snippet_mon_setup(tb)

def snippets_main_after_start(tb):
    snipfcn_snippet_mon_poll(tb)




def main(top_block_cls=guru_mon, options=None):

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

    qapp.aboutToQuit.connect(quitting)
    qapp.exec_()

if __name__ == '__main__':
    main()
