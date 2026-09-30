"""MON meter: only samples of VERIFIED MON dwells (from a mon_on tag to the next
mon_off / mon_bad) are counted and used; the newest `keep` samples lying inside one
verified dwell are kept for the readout. Outputs 4-7 of switch_source."""
import numpy as np
import pmt
from gnuradio import gr


class blk(gr.sync_block):
    def __init__(self, nch=4, keep=8192):
        gr.sync_block.__init__(self, name="MON meter (verified dwells)", in_sig=[np.complex64] * nch,
                               out_sig=None)
        self.nch, self.keep = nch, keep
        self.count = 0              # samples of verified MON dwells, per channel (same for all 4)
        self.dwells = 0
        self.inside = False
        self.snap = [None] * nch
        self._buf = [[] for _ in range(nch)]
        self._have = 0
        self._want = True
        self._on, self._off, self._bad = pmt.intern("mon_on"), pmt.intern("mon_off"), pmt.intern("mon_bad")

    def request(self):
        self._want = True

    def _take(self, items, a, b):
        if b <= a or not self.inside:
            return
        self.count += b - a
        if self._want:
            for c in range(self.nch):
                self._buf[c].append(items[c][a:b].copy())
            self._have += b - a
            if self._have >= self.keep:
                for c in range(self.nch):
                    self.snap[c] = np.concatenate(self._buf[c])[-self.keep:]
                self._buf, self._have, self._want = [[] for _ in range(self.nch)], 0, False

    def _cut(self):
        # a readout never spans two dwells: an unfinished one is dropped
        self._buf, self._have = [[] for _ in range(self.nch)], 0

    def work(self, input_items, output_items):
        n = len(input_items[0])
        w0 = self.nitems_read(0)
        ev = sorted((t.offset - w0, pmt.symbol_to_string(t.key)) for t in self.get_tags_in_range(0, w0, w0 + n)
                    if t.key in (self._on, self._off, self._bad))
        pos = 0
        for off, k in ev:
            self._take(input_items, pos, off)
            pos = off
            self._cut()
            if k == "mon_on":
                self.inside = True
                self.dwells += 1
            else:
                self.inside = False
        self._take(input_items, pos, n)
        return n
