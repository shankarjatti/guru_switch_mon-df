// twinrx_engine: radio-clock hopping for the USRP-2945 (X310 + 2x TwinRX).
//
// The timing-critical half of doa.twinrx_radio_source, in C++ so it never
// waits on Python's interpreter lock:
//   * receive thread: X310 -> lock-free ring buffer (4 channels, planar)
//   * scheduler thread: one timed command batch per slot, sent one slot ahead
// Python (the GNU Radio block) only copies samples out of the ring and places
// the hop tags from the slot table this engine keeps.
//
// Everything here repeats what was verified on this unit on 2026-09-28
// (guru/sched_hop_test.py, tune_method_phase_test.py, fast_chain_check.py):
//   * setup: subdev A:0 A:1 B:0 B:1, antennas RX1/RX2/RX1/RX2, LO exported by
//     board B (ch0/ch1 external, ch2 internal + export, ch3 companion), DDC at
//     0 Hz and never commanded while hopping
//   * band change at radio time S: gains at S, channel c's RF tune at
//     S + c*0.4 ms, the same RF tunes again at S + 3 ms (phase-equal to guru's
//     host double tune; a single pass leaves the LO in another phase state)
//   * per slot: read lo_locked at S + lock_check, THEN send slot k+1 (a read
//     issued while a timed command waits is queued behind it)
//   * a slot is valid only if sent with min_slack to spare, finished before
//     S, and locked
//   * sample n is taken at start + n/fs; packet timestamps (which step at 2x
//     on this X310) only detect gaps
//
// Burst mode (burst=1): each batch also carries a timed "send pre-roll + dwell
// samples, then stop" stream command, so the X310 sends nothing while the LO
// relocks. Every burst must start on its commanded sample and hold exactly its
// commanded length; the bursts go on the same continuous timeline (gaps are
// zeros), so the block and everything after it work as in continuous mode.
//
// MON mode (this copy, guru_switch): one more band whose four channels each
// run on their OWN internal LO and frequency (export off, all internal). The
// mode is changed at a slot boundary by the scheduler: the LO routing is sent
// TIMED at the switch slot's S, before its tune (measured 2026-09-30: timed
// routing takes effect at S, never before; the DF phase comes back within
// 0.16 deg; route_burst_test.py / switch_check.py). Consecutive MON slots are
// NOT retuned: their bursts follow each other with no gap (continuous MON).
//
// C API for ctypes; see switch_source.py (guru_switch) / twinrx_radio_source.py.

#include <uhd/usrp/multi_usrp.hpp>
#include <uhd/types/tune_request.hpp>
#include <uhd/utils/thread.hpp>

#include <pthread.h>
#include <sched.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <complex>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace {

using cf = std::complex<float>;
using clk = std::chrono::steady_clock;

constexpr int NCH = 4;
constexpr double STEP = 0.0004;
constexpr double SECOND_PASS = 0.003;
constexpr size_t LO_MASTER = 2;
const char* const DF_SRC[NCH] = {"external", "external", "internal", "companion"};

double host_now() {
    return std::chrono::duration<double>(clk::now().time_since_epoch()).count();
}

struct Slot {
    long id;
    double S;
    double freq;
    double next;
    int valid;      // -1 unknown, 0 invalid, 1 valid
    int why;        // 0 ok, 1 skipped, 2 late, 3 unlocked, 4 burst never came
    int mode;       // 0 DF (shared LO), 1 MON (own LO per channel)
    int band;       // band index (DF bands 0..n_df-1, MON = n_df)
    double pre;     // dwell starts at S + pre (settle - guard, or 0: MON not retuned)
    int tuned;      // 1 = this slot switched/retuned the LOs at S
};

struct Engine {
    // configuration
    std::string args;
    double fs = 1e6;
    std::vector<double> freq, gain, dwell;
    std::vector<std::vector<double>> gains;   // per band, per channel (clamped)
    std::vector<double> trim;
    double settle = 0.01, gpre = 0.00025, lock_check = 0.007, min_slack = 0.008;
    double start_delay = 0.5;
    int rt_prio = 0;
    // Burst mode: the X310 sends only each dwell (plus a short pre-roll that
    // falls inside the switching time and is never used), nothing while the
    // LO relocks. The bursts are put back on the same continuous sample
    // timeline, the switching gaps filled with zeros, so everything after the
    // engine sees exactly what it sees in continuous mode.
    bool burst = false;
    double preroll = 0.00025;
    // per band: every channel's own frequency, and the LO mode (0 DF shared, 1 MON own)
    std::vector<std::array<double, NCH>> fch;
    std::vector<int> bmode;
    size_t n_df = 0;                   // bands 0..n_df-1 are DF; band n_df is MON (if has_mon)
    bool has_mon = false;
    std::atomic<int> want_mode{0};     // requested mode (set_mode); taken at the next slot
    int routed_mode = 0;               // routing last commanded (scheduler thread only)
    // switch record (the scheduler writes, eng_mode_info reads)
    std::atomic<long> n_switches{0}, n_switch_bad{0};
    std::atomic<double> last_req_dev{0}, last_sw_S{0}, last_sw_dwell{0};
    std::atomic<int> last_sw_ok{-1}, last_sw_to{-1}, cur_mode{0};
    std::atomic<long long> mon_dwell_samples{0}, df_dwell_samples{0};
    std::array<double, NCH> mon_gain{{0, 0, 0, 0}};
    // time between the end of the old mode's last dwell and the switch slot's S:
    // the routing is sent UNTIMED in it (measured 2026-09-30: sent timed, every
    // routing call reads the TwinRX back and that read waits behind the timed
    // write, so the host blocked until S and the tune after it went out late)
    double switch_gap = 0.010;
    std::atomic<double> last_route_ms{0}, max_route_ms{0};
    // MON: each channel's own lo_locked as last read by the scheduler (-1 not yet)
    std::atomic<int> mon_lock[NCH] = {{-1}, {-1}, {-1}, {-1}};
    // MON streams CONTINUOUSLY (one timed start, one stop): the receive loop
    // puts the sample index just after the last MON sample here when the stop
    // arrives (end of burst)
    std::atomic<long long> mon_end_n{-1};

    uhd::usrp::multi_usrp::sptr u;
    uhd::rx_streamer::sptr rx;
    size_t spp = 0;
    double start_dev = 0;

    // ring buffer
    size_t ring_n = 1 << 22;                  // samples per channel (~4 s)
    std::vector<cf> ring[NCH];
    std::atomic<uint64_t> w_idx{0}, r_idx{0};
    std::mutex dmx;
    std::condition_variable dcv;

    // state
    std::atomic<bool> run{false};
    std::thread t_rx, t_sched;
    std::mutex smx;
    std::deque<Slot> slots;
    long next_id = 0;
    std::atomic<bool> lost{false};
    std::string lost_why;
    std::mutex lmx;
    std::atomic<long> n_slots{0}, n_valid{0}, n_skipped{0}, n_late{0}, n_unlocked{0};
    std::atomic<long> n_overflow{0}, n_timeout{0}, n_other_err{0};
    std::atomic<double> max_send_ms{0};
    std::atomic<double> avg_send_ms{0};         // running average (EMA, 1/50)
    std::atomic<double> pkt_scale{0};
    std::atomic<double> dev_offset{0};        // radio time - host clock, from the scheduler
    std::atomic<int> rt_sched_ok{-1}, rt_rx_ok{-1};
    std::string log;

    // burst mode: every burst commanded, in time order (sample index of its
    // first sample on the continuous timeline, and its length)
    struct Burst { long id; long long n0; long long len; long long pre; int mode; };
    std::mutex bmx;
    std::deque<Burst> expect;
    std::atomic<long> n_burst_ok{0}, n_burst_missing{0};
    // the last burst as the radio delivered it: samples counted packet by
    // packet, and its first sample's radio time stamp (as a sample index)
    std::atomic<long long> last_burst_got{0}, last_burst_n0{-1}, last_burst_len{0};
    std::atomic<long long> burst_got_min{0}, burst_got_max{0};
    // two independent running counters for the screen: every dwell sample the
    // radio delivered (added packet by packet, pre-roll not included), and +1
    // for every complete dwell burst -- neither is computed from the other
    std::atomic<long long> total_dwell_samples{0}, total_dwells{0};
    std::mutex cmx;          // both totals change together, once per complete burst

    // optional per-slot timing record (TWINRX_ENGINE_TIMING=file): where the
    // scheduler's time goes, written at stop. Times in ms relative to the slot's S.
    struct Tim { long k; int band; double lock_issue, lock_done, send_start, dev_read,
                 band_done, send_end; int late; };
    std::vector<Tim> tim;
    bool tim_on = false;

    void note(const std::string& s) {
        std::lock_guard<std::mutex> g(lmx);
        log += s + "\n";
        std::fprintf(stderr, "[engine] %s\n", s.c_str());
    }
    void lose(const std::string& why) {
        bool exp = false;
        if (lost.compare_exchange_strong(exp, true)) {
            {
                std::lock_guard<std::mutex> g(lmx);
                lost_why = why;
            }
            note("TIMING LOST: " + why + " -- no dwell is used from here on; restart");
        }
    }

    int set_rt(int prio) {
        if (prio <= 0) return -1;
        sched_param sp{};
        sp.sched_priority = prio;
        return pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp) == 0 ? 1 : 0;
    }

    // ---------------------------------------------------------------- setup
    void setup() {
        for (double v : {settle, gpre}) {
            double n = v * fs;
            if (std::fabs(n - std::round(n)) > 1e-6)
                throw std::runtime_error("switching time and guard must be whole samples");
        }
        for (double d : dwell) {
            double n = d * fs;
            if (std::fabs(n - std::round(n)) > 1e-6)
                throw std::runtime_error("every dwell must be a whole number of samples");
        }
        if (burst) {
            double n = preroll * fs;
            if (preroll < 0 || std::fabs(n - std::round(n)) > 1e-6)
                throw std::runtime_error("burst pre-roll must be a whole number of samples");
            // the stream command is the last one of each batch: it must come
            // after the second tune pass, or the radio's command queue (which
            // runs in order) would reach it late
            if (settle - gpre - preroll < SECOND_PASS + 0.0005)
                throw std::runtime_error("burst mode: switching time too short for the "
                                         "second tune pass + guard + pre-roll");
        }
        u = uhd::usrp::multi_usrp::make(args);
        u->set_clock_source("internal", 0);
        // REF OUT on: the X310's 10 MHz for the lab transmitter's CLKIN, so the
        // tone is made from the same clock the samples are counted with (a
        // free-running HackRF drifted 0.54 ppm in 16 min: 50 -> 34 cycles)
        try {
            u->set_clock_source_out(true, 0);
        } catch (const std::exception& e) {
            note(std::string("REF OUT could not be switched on: ") + e.what());
        }
        u->set_rx_subdev_spec(uhd::usrp::subdev_spec_t("A:0 A:1 B:0 B:1"), 0);
        u->set_rx_rate(fs);
        for (int attempt = 1;; ++attempt) {
            try {
                u->set_time_unknown_pps(uhd::time_spec_t(0.0));
                break;
            } catch (const std::exception& e) {
                note("PPS time sync attempt " + std::to_string(attempt) + " failed: " + e.what());
                if (attempt == 3) throw;
            }
        }
        for (size_t ch = 0; ch < NCH; ++ch) {
            u->set_rx_antenna(ch % 2 == 0 ? "RX1" : "RX2", ch);
            u->set_rx_dc_offset(true, ch);
        }
        for (size_t ch = 0; ch < NCH; ++ch) {
            try {
                u->set_rx_lo_export_enabled(false, uhd::usrp::multi_usrp::ALL_LOS, ch);
            } catch (const std::exception& e) {
                note("clearing LO export on ch" + std::to_string(ch) + ": " + e.what());
            }
        }
        // start mode (routed_mode, set by eng_create2): DF = board B exports,
        // MON = every channel on its own internal LO
        const size_t b0 = routed_mode == 1 ? n_df : 0;
        for (size_t ch = 0; ch < NCH; ++ch)
            u->set_rx_lo_source(routed_mode == 1 ? "internal" : DF_SRC[ch],
                                uhd::usrp::multi_usrp::ALL_LOS, ch);
        if (routed_mode == 0)
            u->set_rx_lo_export_enabled(true, uhd::usrp::multi_usrp::ALL_LOS, LO_MASTER);
        cur_mode = routed_mode;

        gains.assign(fch.size(), std::vector<double>(NCH, 0));
        for (size_t b = 0; b < fch.size(); ++b)
            for (size_t ch = 0; ch < NCH; ++ch) {
                auto r = u->get_rx_gain_range(ch);
                const double g = bmode[b] == 1 ? mon_gain[ch] : gain[b] + trim[ch];
                gains[b][ch] = std::max(r.start(), std::min(r.stop(), g));
            }
        for (size_t ch = 0; ch < NCH; ++ch) u->set_rx_gain(gains[b0][ch], ch);
        for (size_t ch = 0; ch < NCH; ++ch) {
            uhd::tune_request_t req(fch[b0][ch]);
            req.rf_freq = fch[b0][ch];
            req.rf_freq_policy = uhd::tune_request_t::POLICY_MANUAL;
            req.dsp_freq = 0.0;
            req.dsp_freq_policy = uhd::tune_request_t::POLICY_MANUAL;
            auto res = u->set_rx_freq(req, ch);
            if (res.actual_dsp_freq != 0.0)
                throw std::runtime_error("DDC not at 0 Hz on ch" + std::to_string(ch));
        }
        uhd::stream_args_t sa("fc32", "sc16");
        sa.channels = {0, 1, 2, 3};
        rx = u->get_rx_stream(sa);
        spp = rx->get_max_num_samps();
        for (auto& r : ring) r.assign(ring_n, cf(0, 0));
    }

    // LO routing for mode m, UNTIMED: only called when nothing timed is waiting
    // in the radio (after the previous dwell ended), so its read-backs return at once.
    void route_now(int m) {
        const double h0 = host_now();
        for (size_t ch = 0; ch < NCH; ++ch)
            u->set_rx_lo_export_enabled(false, uhd::usrp::multi_usrp::ALL_LOS, ch);
        for (size_t ch = 0; ch < NCH; ++ch)
            u->set_rx_lo_source(m == 1 ? "internal" : DF_SRC[ch], uhd::usrp::multi_usrp::ALL_LOS, ch);
        if (m == 0) u->set_rx_lo_export_enabled(true, uhd::usrp::multi_usrp::ALL_LOS, LO_MASTER);
        routed_mode = m;
        const double ms = (host_now() - h0) * 1e3;
        last_route_ms = ms;
        if (ms > max_route_ms) max_route_ms = ms;
    }

    // Band change at radio time T: the usual phase-correct tune (the routing for
    // this band's mode was already sent by the scheduler, see route_now).
    void band_change(size_t i, double T) {
        if (bmode[i] != routed_mode) route_now(bmode[i]);     // not reached: the scheduler routes first
        u->set_command_time(uhd::time_spec_t(T));
        for (size_t ch = 0; ch < NCH; ++ch) u->set_rx_gain(gains[i][ch], ch);
        uhd::tune_request_t req[NCH];
        for (size_t ch = 0; ch < NCH; ++ch) {
            req[ch] = uhd::tune_request_t(fch[i][ch]);
            req[ch].rf_freq = fch[i][ch];
            req[ch].rf_freq_policy = uhd::tune_request_t::POLICY_MANUAL;
            req[ch].dsp_freq_policy = uhd::tune_request_t::POLICY_NONE;
        }
        for (size_t ch = 0; ch < NCH; ++ch) {
            u->set_command_time(uhd::time_spec_t(T + ch * STEP));
            u->set_rx_freq(req[ch], ch);
        }
        u->set_command_time(uhd::time_spec_t(T + SECOND_PASS));
        for (size_t ch = 0; ch < NCH; ++ch) u->set_rx_freq(req[ch], ch);
        u->clear_command_time();
    }

    // -------------------------------------------------------------- receive
    void rx_loop() {
        rt_rx_ok = set_rt(rt_prio > 1 ? rt_prio - 1 : rt_prio);
        uhd::rx_metadata_t md;
        std::vector<cf> tmp[NCH];
        for (auto& t : tmp) t.resize(spp);
        std::vector<void*> bp(NCH);
        bool first = true;
        double prev_ts = 0;
        size_t prev_got = 0;
        std::vector<double> steps;
        while (run) {
            for (int c = 0; c < NCH; ++c) bp[c] = tmp[c].data();
            size_t got = rx->recv(bp, spp, md, 0.1, true);
            if (md.error_code != uhd::rx_metadata_t::ERROR_CODE_NONE) {
                if (md.error_code == uhd::rx_metadata_t::ERROR_CODE_TIMEOUT) {
                    if (!first) ++n_timeout;
                    continue;
                }
                if (md.error_code == uhd::rx_metadata_t::ERROR_CODE_OVERFLOW) ++n_overflow;
                else ++n_other_err;
                lose(std::string("stream error: ") + md.strerror());
                continue;
            }
            if (got == 0) continue;
            double ts = md.time_spec.get_real_secs();
            if (first) {
                first = false;
                if (std::fabs(ts - start_dev) > 1e-6)
                    lose("first packet at " + std::to_string(ts) + " s, commanded start " +
                         std::to_string(start_dev));
            } else {
                double step = (ts - prev_ts) / (prev_got / fs);
                if (pkt_scale.load() == 0) {
                    steps.push_back(step);
                    if (steps.size() == 200) {
                        std::vector<double> s = steps;
                        std::nth_element(s.begin(), s.begin() + 100, s.end());
                        pkt_scale = s[100];
                        note("packet timestamp step scale " + std::to_string(pkt_scale.load()) +
                             " (used only to detect gaps)");
                    }
                } else if (std::fabs(step - pkt_scale.load()) > 0.01 * pkt_scale.load()) {
                    lose("packet timestamps jumped (step x" + std::to_string(step) +
                         ") -- samples lost");
                }
            }
            prev_ts = ts;
            prev_got = got;
            uint64_t w = w_idx.load(std::memory_order_relaxed);
            if (w + got - r_idx.load(std::memory_order_acquire) > ring_n) {
                lose("host ring buffer full -- the flowgraph is not keeping up");
                continue;
            }
            for (size_t k = 0; k < got;) {
                size_t pos = (w + k) % ring_n;
                size_t len = std::min(got - k, ring_n - pos);
                for (int c = 0; c < NCH; ++c)
                    std::memcpy(&ring[c][pos], &tmp[c][k], len * sizeof(cf));
                k += len;
            }
            w_idx.store(w + got, std::memory_order_release);
            dcv.notify_all();
        }
    }

    // ------------------------------------------------------- receive, bursts
    // A slot whose burst never came: it must not be used even if its lock
    // check passed. Called before the samples of that dwell are made visible,
    // so the block (which re-reads the verdicts after every read) cannot tag it.
    void burst_missing(long id) {
        ++n_burst_missing;
        std::lock_guard<std::mutex> g(smx);
        for (auto& s : slots)
            if (s.id == id) {
                if (s.valid == 1) --n_valid;
                s.valid = 0;
                s.why = 4;
            }
    }

    // write len samples (nullptr = zeros) at the ring's write position
    bool ring_put(const std::vector<cf>* src, size_t len) {
        uint64_t w = w_idx.load(std::memory_order_relaxed);
        if (w + len - r_idx.load(std::memory_order_acquire) > ring_n) {
            lose("host ring buffer full -- the flowgraph is not keeping up");
            return false;
        }
        for (size_t k = 0; k < len;) {
            size_t pos = (w + k) % ring_n;
            size_t n = std::min(len - k, ring_n - pos);
            for (int c = 0; c < NCH; ++c) {
                if (src) std::memcpy(&ring[c][pos], &src[c][k], n * sizeof(cf));
                else std::memset(static_cast<void*>(&ring[c][pos]), 0, n * sizeof(cf));
            }
            k += n;
        }
        w_idx.store(w + len, std::memory_order_release);
        dcv.notify_all();
        return true;
    }

    void rx_loop_burst() {
        rt_rx_ok = set_rt(rt_prio > 1 ? rt_prio - 1 : rt_prio);
        uhd::rx_metadata_t md;
        std::vector<cf> tmp[NCH];
        for (auto& t : tmp) t.resize(spp);
        std::vector<void*> bp(NCH);
        bool in_burst = false, any = false;
        Burst cur{};
        long long got_in = 0, dwell_in = 0;
        while (run) {
            for (int c = 0; c < NCH; ++c) bp[c] = tmp[c].data();
            size_t got = rx->recv(bp, spp, md, 0.1, true);
            if (md.error_code != uhd::rx_metadata_t::ERROR_CODE_NONE) {
                if (md.error_code == uhd::rx_metadata_t::ERROR_CODE_TIMEOUT) {
                    // bursts come every slot (a few ms): 100 ms of nothing
                    // while hopping means the radio stopped sending
                    if (any && run) {
                        ++n_timeout;
                        lose("no burst from the radio for 100 ms while hopping");
                    }
                    continue;
                }
                if (md.error_code == uhd::rx_metadata_t::ERROR_CODE_LATE_COMMAND) {
                    // the batch reached the radio after the burst's start
                    // time: no samples for that slot (it is already counted
                    // late); found as missing when the next burst arrives
                    continue;
                }
                if (md.error_code == uhd::rx_metadata_t::ERROR_CODE_OVERFLOW) ++n_overflow;
                else ++n_other_err;
                lose(std::string("stream error: ") + md.strerror());
                continue;
            }
            if (got == 0) continue;
            if (!in_burst) {
                // first packet of a burst: its time stamp is the commanded
                // start -- it must be exactly the sample the scheduler asked for
                const double nf = (md.time_spec.get_real_secs() - start_dev) * fs;
                const long long n0 = std::llround(nf);
                if (std::fabs(nf - n0) > 0.01)
                    lose("burst starts between samples (" + std::to_string(nf) + ")");
                bool found = false;
                std::vector<long> missing;
                {
                    std::lock_guard<std::mutex> g(bmx);
                    while (!expect.empty() && expect.front().n0 < n0) {
                        missing.push_back(expect.front().id);
                        expect.pop_front();
                    }
                    if (!expect.empty() && expect.front().n0 == n0) {
                        cur = expect.front();
                        expect.pop_front();
                        found = true;
                    }
                }
                for (long id : missing) burst_missing(id);
                if (!found) {
                    lose("burst at sample " + std::to_string(n0) + " was never commanded");
                    continue;
                }
                const long long w = static_cast<long long>(w_idx.load());
                if (n0 < w) {
                    lose("burst at sample " + std::to_string(n0) + " overlaps the previous one");
                    continue;
                }
                if (n0 > w && !ring_put(nullptr, static_cast<size_t>(n0 - w))) continue;
                in_burst = true;
                any = true;
                got_in = 0;
                dwell_in = 0;
            }
            if (cur.len >= 0 && got_in + static_cast<long long>(got) > cur.len) {
                lose("burst longer than commanded (" + std::to_string(got_in + got) + " > " +
                     std::to_string(cur.len) + " samples)");
                in_burst = false;
                continue;
            }
            if (!ring_put(tmp, got)) continue;
            // samples of this packet that lie after the burst's pre-roll = dwell samples
            {
                const long long pre = cur.pre;          // 0 on a MON burst that follows MON
                const long long before = std::max(0LL, std::min(got_in, pre));
                const long long after = std::max(0LL, std::min(got_in + static_cast<long long>(got), pre));
                dwell_in += static_cast<long long>(got) - (after - before);
            }
            got_in += got;
            if (cur.len < 0) {
                // continuous MON: every packet counted as it comes; it ends at the stop
                {
                    std::lock_guard<std::mutex> g(cmx);
                    mon_dwell_samples += static_cast<long long>(got);
                }
                if (md.end_of_burst) {
                    in_burst = false;
                    ++n_burst_ok;
                    last_burst_got = got_in;
                    last_burst_n0 = cur.n0;
                    last_burst_len = got_in;
                    mon_end_n = cur.n0 + got_in;
                }
                continue;
            }
            if (got_in == cur.len) {            // complete (end-of-burst on this packet)
                in_burst = false;
                ++n_burst_ok;
                {
                    // this burst's dwell samples (counted packet by packet above)
                    // and +1 dwell, published together: a reading never sees a
                    // half-received burst
                    // DF dwells (MON is continuous, counted above)
                    std::lock_guard<std::mutex> g(cmx);
                    total_dwell_samples += dwell_in;
                    ++total_dwells;
                    df_dwell_samples += dwell_in;
                }
                last_burst_got = got_in;
                last_burst_n0 = cur.n0;
                last_burst_len = cur.len;
                if (burst_got_min.load() == 0 || got_in < burst_got_min.load()) burst_got_min = got_in;
                if (got_in > burst_got_max.load()) burst_got_max = got_in;
            } else if (md.end_of_burst) {
                in_burst = false;
                lose("burst shorter than commanded (" + std::to_string(got_in) + " of " +
                     std::to_string(cur.len) + " samples)");
            }
        }
    }

    // ------------------------------------------------------------ scheduler
    void sched_loop() {
        rt_sched_ok = set_rt(rt_prio);
        tim_on = std::getenv("TWINRX_ENGINE_TIMING") != nullptr;
        double off = 0;
        auto dev_now = [&]() {
            double a = host_now();
            double d = u->get_time_now().get_real_secs();
            off = d - (a + host_now()) / 2.0;
            dev_offset = off;
            return d;
        };
        auto sleep_until = [&](double t) {
            while (run) {
                double r = t - (host_now() + off);
                if (r <= 0) return;
                std::this_thread::sleep_for(std::chrono::duration<double>(
                    r > 0.001 ? r - 0.0005 : 0.0001));
            }
        };
        // Slots are counted in whole samples from the stream start, so every
        // boundary -- switch, dwell start, next switch -- falls on an exact
        // sample and the dwell is the same number of samples on every slot.
        //   retuned slot (every DF slot, the first MON slot after a switch):
        //       S = switch (routing if the mode changes, then the tune),
        //       dwell = [S + settle - guard, + dwell), next S = its end + guard
        //   MON slot after MON: not retuned, dwell = [S, S + dwell), next S = its
        //       end (+ guard if the next slot retunes) -- MON bursts join up
        auto t_of = [&](long long n) { return start_dev + static_cast<double>(n) / fs; };
        const long long gpre_n = std::llround(gpre * fs);
        const long long pre_tune_n = std::llround((settle - gpre) * fs);
        const long long pre_n = std::llround(preroll * fs);
        std::vector<long long> dw_n(fch.size());
        for (size_t i = 0; i < fch.size(); ++i) dw_n[i] = std::llround(dwell[i] * fs);
        long long nS0 = static_cast<long long>(std::ceil(
            (std::max(dev_now(), start_dev) + std::max(start_delay, 0.2) - start_dev) * fs));
        long k = 0;
        size_t df_pos = 0;

        struct Cur { long id; double S; long long nS; size_t i; bool sent; bool late;
                     bool tuned; long long pre; int mode; bool sw; };
        double cur_lock_issue = 0, cur_lock_done = 0;
        const long long gap_n = std::llround(switch_gap * fs);
        // a DF slot at sample nS (sw: it changes the LO routing -- decided by the
        // caller BEFORE the routing is sent)
        auto plan_df = [&](const Cur* prev, long long nS, bool sw) {
            Cur c{};
            if (prev && prev->mode == 1) df_pos = 0;           // DF restarts its cycle
            c.mode = 0;
            c.i = df_pos;
            df_pos = (df_pos + 1) % n_df;
            c.tuned = true;
            c.pre = pre_tune_n;
            c.sw = sw;
            c.nS = nS;
            c.S = t_of(nS);
            return c;
        };
        // the first MON slot: tune at S, then ONE continuous stream from its dwell start
        auto plan_mon_entry = [&](long long nS, bool sw) {
            Cur c{};
            c.mode = 1;
            c.i = n_df;
            c.tuned = true;
            c.pre = pre_tune_n;
            c.sw = sw;
            c.nS = nS;
            c.S = t_of(nS);
            return c;
        };
        // a MON record (every mon_dwell of the continuous stream): no radio command,
        // only its lock read and its verdict
        auto plan_mon_record = [&](long long nS) {
            Cur c{};
            c.mode = 1;
            c.i = n_df;
            c.tuned = false;
            c.pre = 0;
            c.nS = nS;
            c.S = t_of(nS);
            return c;
        };
        auto send = [&](Cur c, long k) {
            const double S = c.S;
            {
                std::lock_guard<std::mutex> g(smx);
                c.id = next_id++;
                slots.push_back(Slot{c.id, S, bmode[c.i] == 1 ? 0.0 : fch[c.i][0], 0.0, -1, 0,
                                     c.mode, static_cast<int>(c.i),
                                     static_cast<double>(c.pre) / fs, c.tuned ? 1 : 0});
            }
            if (c.sw) {
                ++n_switches;
                last_sw_S = S;
                last_sw_dwell = t_of(c.nS + c.pre);
                last_sw_to = c.mode;
                last_sw_ok = -1;
            }
            if (!c.tuned) {                 // MON record: nothing to send
                c.sent = true;
                c.late = false;
                return c;
            }
            const double t_start = host_now();
            if (S - dev_now() < min_slack) {
                ++n_skipped;
                c.sent = false;
                return c;
            }
            double h0 = host_now();
            band_change(c.i, S);
            const double t_band = host_now();
            if (c.mode == 0) {
                const long long n0 = c.nS + c.pre - pre_n;
                const long long len = pre_n + dw_n[c.i];
                {
                    std::lock_guard<std::mutex> g(bmx);
                    expect.push_back(Burst{c.id, n0, len, pre_n, 0});
                }
                uhd::stream_cmd_t sc(uhd::stream_cmd_t::STREAM_MODE_NUM_SAMPS_AND_DONE);
                sc.num_samps = static_cast<size_t>(len);
                sc.stream_now = false;
                sc.time_spec = uhd::time_spec_t(t_of(n0));
                rx->issue_stream_cmd(sc);
            } else {
                // MON: continuous from the first dwell sample until the stop
                const long long n0 = c.nS + c.pre;
                {
                    std::lock_guard<std::mutex> g(bmx);
                    expect.push_back(Burst{c.id, n0, -1, 0, 1});
                }
                mon_end_n = -1;
                uhd::stream_cmd_t sc(uhd::stream_cmd_t::STREAM_MODE_START_CONTINUOUS);
                sc.stream_now = false;
                sc.time_spec = uhd::time_spec_t(t_of(n0));
                rx->issue_stream_cmd(sc);
            }
            double h1 = host_now();
            const double ms = (h1 - h0) * 1e3;
            if (ms > max_send_ms) max_send_ms = ms;
            avg_send_ms = avg_send_ms.load() == 0 ? ms : 0.98 * avg_send_ms.load() + 0.02 * ms;
            c.sent = true;
            c.late = h1 + off >= S;
            if (c.late) ++n_late;
            if (tim_on && tim.size() < 200000)
                tim.push_back(Tim{k, static_cast<int>(c.i), cur_lock_issue, cur_lock_done,
                                  (t_start + off - S) * 1e3, (h0 + off - S) * 1e3,
                                  (t_band + off - S) * 1e3, (h1 + off - S) * 1e3,
                                  c.late ? 1 : 0});
            return c;
        };
        auto finish = [&](const Cur& c, int valid, int why) {
            std::lock_guard<std::mutex> g(smx);
            for (auto& s : slots)
                if (s.id == c.id) { s.valid = valid; s.why = why; }
        };

        Cur cur = routed_mode == 1 ? send(plan_mon_entry(nS0, false), k) : send(plan_df(nullptr, nS0, false), k);
        while (run) {
            // lock read: a tuned slot at S + lock_check (before its first used
            // sample); a MON record 0.5 ms into its 20 ms
            sleep_until(cur.S + (cur.tuned ? lock_check : std::min(0.0005, dwell[cur.i] / 2)));
            if (!run) break;
            ++n_slots;
            int why = 0;
            bool ok = false;
            if (!cur.sent) why = 1;
            else if (cur.late) why = 2;
            else {
                cur_lock_issue = (host_now() + off - cur.S) * 1e3;
                if (cur.mode == 0) {
                    ok = u->get_rx_sensor("lo_locked", LO_MASTER).to_bool();
                } else if (cur.tuned) {
                    ok = true;                  // MON start: every channel's OWN synthesiser
                    for (size_t ch = 0; ch < NCH; ++ch) {
                        const bool l = u->get_rx_sensor("lo_locked", ch).to_bool();
                        mon_lock[ch] = l ? 1 : 0;
                        ok = l && ok;
                    }
                } else {
                    const size_t ch = static_cast<size_t>(k % NCH);   // MON: one channel per record
                    ok = u->get_rx_sensor("lo_locked", ch).to_bool();
                    mon_lock[ch] = ok ? 1 : 0;
                }
                cur_lock_done = (host_now() + off - cur.S) * 1e3;
                if (!ok) { ++n_unlocked; why = 3; }
            }
            finish(cur, ok ? 1 : 0, why);
            if (ok) ++n_valid;
            cur_mode = cur.mode;
            if (cur.sw) {
                last_sw_ok = ok ? 1 : 0;
                if (!ok) ++n_switch_bad;
            }
            ++k;
            const long long end_n = cur.nS + cur.pre + dw_n[cur.i];   // end of this dwell / record
            const int want = has_mon ? want_mode.load() : 0;
            if (cur.mode == 0) {
                if (want == 1) {
                    // DF -> MON: after the last DF dwell has ended, routing (untimed), then MON
                    sleep_until(t_of(end_n) + 0.0002);
                    if (!run) break;
                    route_now(1);
                    cur = send(plan_mon_entry(end_n + gap_n + gpre_n, true), k);
                } else {
                    cur = send(plan_df(&cur, end_n + gpre_n, false), k);
                }
            } else {
                if (want == 0) {
                    // MON -> DF: stop the continuous stream now; it ends where it ends
                    if (cur.sent) {
                        rx->issue_stream_cmd(uhd::stream_cmd_t(uhd::stream_cmd_t::STREAM_MODE_STOP_CONTINUOUS));
                        const double t_stop = host_now();
                        while (run && mon_end_n.load() < 0 && host_now() - t_stop < 0.5)
                            std::this_thread::sleep_for(std::chrono::microseconds(200));
                    }
                    if (!run) break;
                    long long E = mon_end_n.load();
                    if (E < 0) {
                        lose("the MON stream did not stop within 0.5 s");
                        E = static_cast<long long>(std::ceil((dev_now() - start_dev) * fs));
                    }
                    route_now(0);
                    cur = send(plan_df(&cur, E + gap_n + gpre_n, true), k);
                } else {
                    cur = send(plan_mon_record(end_n), k);   // the next 20 ms, pending until its read
                }
            }
        }
        // a MON stream still running at the end: stop it
        if (cur.mode == 1 && cur.sent) {
            try {
                rx->issue_stream_cmd(uhd::stream_cmd_t(uhd::stream_cmd_t::STREAM_MODE_STOP_CONTINUOUS));
            } catch (const std::exception&) {}
        }
    }
};

}  // namespace

extern "C" {

// DF only (as before): nbands shared-LO bands.
void* eng_create2(const char* args, double fs, int nbands, const double* freqs,
                  const double* gains, const double* dwells, const double* trim4,
                  double settle, double gpre, double lock_check, double min_slack,
                  double start_delay, int rt_prio, int burst, double preroll,
                  int has_mon, const double* mon_freq4, const double* mon_gain4, double mon_dwell,
                  int start_mode, char* err, int errlen) {
    auto* e = new Engine();
    try {
        e->args = args;
        e->fs = fs;
        e->n_df = static_cast<size_t>(nbands);
        if (e->n_df == 0) throw std::runtime_error("no DF band");
        for (int b = 0; b < nbands; ++b) {
            e->freq.push_back(freqs[b]);
            e->gain.push_back(gains[b]);
            e->dwell.push_back(dwells[b]);
            e->fch.push_back({{freqs[b], freqs[b], freqs[b], freqs[b]}});
            e->bmode.push_back(0);
        }
        e->has_mon = has_mon != 0;
        if (e->has_mon) {
            if (!burst) throw std::runtime_error("MON mode needs burst mode");
            e->freq.push_back(0.0);
            e->gain.push_back(0.0);
            e->dwell.push_back(mon_dwell);
            e->fch.push_back({{mon_freq4[0], mon_freq4[1], mon_freq4[2], mon_freq4[3]}});
            e->bmode.push_back(1);
            for (int c = 0; c < NCH; ++c) e->mon_gain[c] = mon_gain4[c];
        }
        e->routed_mode = (e->has_mon && start_mode == 1) ? 1 : 0;
        e->want_mode = e->routed_mode;
        e->trim.assign(trim4, trim4 + NCH);
        e->settle = settle;
        e->gpre = gpre;
        e->lock_check = lock_check;
        e->min_slack = min_slack;
        e->start_delay = start_delay;
        e->rt_prio = rt_prio;
        e->burst = burst != 0;
        e->preroll = preroll;
        e->setup();
        return e;
    } catch (const std::exception& ex) {
        std::snprintf(err, errlen, "%s", ex.what());
        delete e;
        return nullptr;
    }
}

void* eng_create(const char* args, double fs, int nbands, const double* freqs,
                 const double* gains, const double* dwells, const double* trim4,
                 double settle, double gpre, double lock_check, double min_slack,
                 double start_delay, int rt_prio, int burst, double preroll,
                 char* err, int errlen) {
    const double z[NCH] = {0, 0, 0, 0};
    return eng_create2(args, fs, nbands, freqs, gains, dwells, trim4, settle, gpre, lock_check,
                       min_slack, start_delay, rt_prio, burst, preroll, 0, z, z, 0.0, 0, err, errlen);
}

void eng_set_switch_gap(void* h, double secs) {
    static_cast<Engine*>(h)->switch_gap = secs > 0 ? secs : 0;
}

// Ask for a mode (0 DF, 1 MON); the scheduler takes it at the next slot it plans.
int eng_set_mode(void* h, int mode) {
    auto* e = static_cast<Engine*>(h);
    if (mode == 1 && !e->has_mon) return -1;
    const int m = mode ? 1 : 0;
    // the same request again (e.g. the GUI selector following an API request)
    // is no new request: it must not move the request time
    if (e->want_mode.load() != m) {
        e->last_req_dev = host_now() + e->dev_offset.load();
        e->want_mode = m;
    }
    return e->want_mode.load();
}

// want, mode of the last finished slot, switches, switches whose first slot was
// not locked/used, last request (radio time), last switch S, its first dwell
// sample time, its verdict (-1 pending, 0 bad, 1 ok), mode switched to,
// MON dwell samples, DF dwell samples (both counted packet by packet)
void eng_mode_info(void* h, double* o) {
    auto* e = static_cast<Engine*>(h);
    o[0] = e->want_mode.load(); o[1] = e->cur_mode.load(); o[2] = e->n_switches.load();
    o[3] = e->n_switch_bad.load(); o[4] = e->last_req_dev.load(); o[5] = e->last_sw_S.load();
    o[6] = e->last_sw_dwell.load(); o[7] = e->last_sw_ok.load(); o[8] = e->last_sw_to.load();
    std::lock_guard<std::mutex> g(e->cmx);
    o[9] = static_cast<double>(e->mon_dwell_samples.load());
    o[10] = static_cast<double>(e->df_dwell_samples.load());
    o[11] = e->last_route_ms.load();
    for (int c = 0; c < NCH; ++c) o[12 + c] = e->mon_lock[c].load();
}

double eng_start(void* h, int hop) {
    auto* e = static_cast<Engine*>(h);
    e->start_dev = e->u->get_time_now().get_real_secs() + 0.2;
    if (e->burst) {
        // no continuous stream: the scheduler commands one burst per dwell.
        // start_dev is still sample 0 of the timeline the bursts are put on.
        if (!hop) {
            e->note("burst mode needs hopping on -- nothing will be received");
            return -1.0;
        }
        e->run = true;
        e->t_rx = std::thread(&Engine::rx_loop_burst, e);
        e->t_sched = std::thread(&Engine::sched_loop, e);
        return e->start_dev;
    }
    uhd::stream_cmd_t cmd(uhd::stream_cmd_t::STREAM_MODE_START_CONTINUOUS);
    cmd.stream_now = false;
    cmd.time_spec = uhd::time_spec_t(e->start_dev);
    e->rx->issue_stream_cmd(cmd);
    e->run = true;
    e->t_rx = std::thread(&Engine::rx_loop, e);
    if (hop) e->t_sched = std::thread(&Engine::sched_loop, e);
    return e->start_dev;
}

// Copy up to max_n samples into the four channel buffers; waits up to
// wait_ms for data. Returns the number copied.
long eng_read(void* h, void* c0, void* c1, void* c2, void* c3, long max_n, double wait_ms) {
    auto* e = static_cast<Engine*>(h);
    uint64_t r = e->r_idx.load(std::memory_order_relaxed);
    uint64_t w = e->w_idx.load(std::memory_order_acquire);
    if (w == r && wait_ms > 0) {
        std::unique_lock<std::mutex> lk(e->dmx);
        e->dcv.wait_for(lk, std::chrono::duration<double, std::milli>(wait_ms), [&] {
            return e->w_idx.load(std::memory_order_acquire) != r || !e->run;
        });
        w = e->w_idx.load(std::memory_order_acquire);
    }
    long n = static_cast<long>(std::min<uint64_t>(w - r, static_cast<uint64_t>(max_n)));
    cf* out[NCH] = {static_cast<cf*>(c0), static_cast<cf*>(c1), static_cast<cf*>(c2),
                    static_cast<cf*>(c3)};
    for (long k = 0; k < n;) {
        size_t pos = (r + k) % e->ring_n;
        size_t len = std::min<size_t>(n - k, e->ring_n - pos);
        for (int c = 0; c < NCH; ++c) std::memcpy(out[c] + k, &e->ring[c][pos], len * sizeof(cf));
        k += len;
    }
    e->r_idx.store(r + n, std::memory_order_release);
    return n;
}

// Slot records with id >= from_id: out rows of 10 doubles
// (id, S, freq, next, valid, why, mode, band, pre, tuned). Returns the number written.
int eng_slots(void* h, long from_id, double* out, int max_rows) {
    auto* e = static_cast<Engine*>(h);
    std::lock_guard<std::mutex> g(e->smx);
    // Never read the radio here: this runs on the flowgraph thread, and a read
    // queues behind any timed command still waiting. The scheduler's host
    // clock offset is enough to drop records more than 5 s old.
    const double now_dev = host_now() + e->dev_offset.load();
    while (e->slots.size() > 64 && e->slots.front().S < now_dev - 5.0)
        e->slots.pop_front();
    int n = 0;
    for (const auto& s : e->slots) {
        if (s.id < from_id) continue;
        if (n >= max_rows) break;
        double* o = out + 10 * n++;
        o[0] = s.id; o[1] = s.S; o[2] = s.freq; o[3] = s.next; o[4] = s.valid; o[5] = s.why;
        o[6] = s.mode; o[7] = s.band; o[8] = s.pre; o[9] = s.tuned;
    }
    return n;
}

// stats: slots, valid, skipped, late, unlocked, max_send_ms, lost, overflow,
// timeout, other_err, pkt_scale, rt_sched_ok, rt_rx_ok, avg_send_ms,
// bursts_ok, bursts_missing (burst mode)
void eng_stats(void* h, double* o) {
    auto* e = static_cast<Engine*>(h);
    o[0] = e->n_slots.load(); o[1] = e->n_valid.load(); o[2] = e->n_skipped.load();
    o[3] = e->n_late.load(); o[4] = e->n_unlocked.load(); o[5] = e->max_send_ms.load();
    o[6] = e->lost ? 1 : 0; o[7] = e->n_overflow.load(); o[8] = e->n_timeout.load();
    o[9] = e->n_other_err.load(); o[10] = e->pkt_scale.load();
    o[11] = e->rt_sched_ok.load(); o[12] = e->rt_rx_ok.load();
    o[13] = e->avg_send_ms.load();
    o[14] = e->n_burst_ok.load(); o[15] = e->n_burst_missing.load();
}

// last burst: samples received (counted), its first sample's index on the
// timeline (from the radio's time stamp), samples commanded, and the smallest
// and largest burst received so far
void eng_burst_info(void* h, double* o) {
    auto* e = static_cast<Engine*>(h);
    o[0] = static_cast<double>(e->last_burst_got.load());
    o[1] = static_cast<double>(e->last_burst_n0.load());
    o[2] = static_cast<double>(e->last_burst_len.load());
    o[3] = static_cast<double>(e->burst_got_min.load());
    o[4] = static_cast<double>(e->burst_got_max.load());
    {
        std::lock_guard<std::mutex> g(e->cmx);
        o[5] = static_cast<double>(e->total_dwell_samples.load());
        o[6] = static_cast<double>(e->total_dwells.load());
    }
    // samples waiting in the ring for the flowgraph (if this grows, it is not keeping up)
    o[7] = static_cast<double>(e->w_idx.load() - e->r_idx.load());
}

int eng_lost_reason(void* h, char* buf, int len) {
    auto* e = static_cast<Engine*>(h);
    std::lock_guard<std::mutex> g(e->lmx);
    std::snprintf(buf, len, "%s", e->lost_why.c_str());
    return e->lost ? 1 : 0;
}

void eng_stop(void* h) {
    auto* e = static_cast<Engine*>(h);
    if (!e->run) return;
    e->run = false;
    e->dcv.notify_all();
    if (e->t_sched.joinable()) e->t_sched.join();
    // burst mode: the last commanded burst ends by itself
    if (!e->burst) {
        try {
            e->rx->issue_stream_cmd(uhd::stream_cmd_t(uhd::stream_cmd_t::STREAM_MODE_STOP_CONTINUOUS));
        } catch (const std::exception& ex) {
            e->note(std::string("stopping the stream: ") + ex.what());
        }
    }
    if (e->t_rx.joinable()) e->t_rx.join();
    if (const char* path = std::getenv("TWINRX_ENGINE_TIMING")) {
        if (FILE* f = std::fopen(path, "w")) {
            std::fprintf(f, "k band lock_issue lock_done send_start dev_read band_done send_end late"
                            "   (ms after the checked slot's S)\n");
            for (const auto& t : e->tim)
                std::fprintf(f, "%ld %d %.3f %.3f %.3f %.3f %.3f %.3f %d\n", t.k, t.band,
                             t.lock_issue, t.lock_done, t.send_start, t.dev_read, t.band_done,
                             t.send_end, t.late);
            std::fclose(f);
        }
    }
}

void eng_destroy(void* h) {
    auto* e = static_cast<Engine*>(h);
    eng_stop(h);
    delete e;
}

}  // extern "C"
