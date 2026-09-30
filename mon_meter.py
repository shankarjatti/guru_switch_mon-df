"""MON meter: counts EVERY sample of each channel (real count, not a rate x time),
counts stream breaks (UHD tags each restart after an overflow with rx_time), and
on request keeps the newest `keep` samples of each channel for the readout."""
import time

import numpy as np
import pmt
from gnuradio import gr


class blk(gr.sync_block):
    def __init__(self, nch=4, keep=8192):
        gr.sync_block.__init__(self, name="MON meter", in_sig=[np.complex64] * nch, out_sig=None)
        self.nch, self.keep = nch, keep
        self.count = [0] * nch
        self.rx_time_tags = [0] * nch
        self.t_first = None
        self._buf = [[] for _ in range(nch)]
        self._have = [0] * nch
        self.snap = [None] * nch
        self._want = [True] * nch
        self._key = pmt.intern("rx_time")

    def request(self):
        for c in range(self.nch):
            self._want[c] = True

    def work(self, input_items, output_items):
        n = len(input_items[0])
        if self.t_first is None:
            self.t_first = time.monotonic()
        w0 = self.nitems_read(0)
        for c in range(self.nch):
            self.count[c] += n
            self.rx_time_tags[c] += len(self.get_tags_in_range(c, w0, w0 + n, self._key))
            if self._want[c]:
                x = input_items[c]
                self._buf[c].append(x.copy())
                self._have[c] += len(x)
                if self._have[c] >= self.keep:
                    self.snap[c] = np.concatenate(self._buf[c])[-self.keep:]
                    self._buf[c], self._have[c], self._want[c] = [], 0, False
        return n
