// SPDX-License-Identifier: GPL-2.0-or-later
#include "engine_api.h"
#include "bridge.h"
#include <algorithm>
#include <atomic>
#include <memory>
#include <vector>

namespace {
constexpr unsigned capacity = static_cast<unsigned>(isolator::capacity);
constexpr unsigned mask = capacity - 1;
constexpr unsigned maxChannels = 8;
class Engine {
  public:
    explicit Engine(unsigned hz)
        : rate(hz), dry(maxChannels * capacity), stamps(capacity), mono(capacity / 2),
          output(maxChannels * maxBatch), rampSamples(std::max(1u, hz / 200u)) {
        bridge.start(rate);
    }

    unsigned render(float *const *input, float **out, unsigned channels, unsigned n, unsigned strength,
                    unsigned advance, uint64_t inputTime, uint64_t &outTime, bool gap) {
        if (!n || !channels || channels > maxChannels || n > mono.size() || bridge.state() != 1) {
            if (streaming)
                discarded.fetch_add(written - emitted);
            streaming = false;
            pending.store(0, std::memory_order_relaxed);
            return 0;
        }
        // No wall-clock deadline discards a late inference result. Return it on the next
        // OBS callback; its timestamp still describes the input samples it came from.
        if (!streaming || gap || advance != previousAdvance ||
            written + n - emitted > capacity - 2048) {
            if (streaming)
                discarded.fetch_add(written - emitted);
            bridge.reset(written, advance, n);
            emitted = written;
            previousAdvance = advance;
            fade = 0;
            streaming = true;
        }
        for (unsigned i = 0; i < n; ++i) {
            const auto slot = static_cast<unsigned>(written + i) & mask;
            stamps[slot] = inputTime + static_cast<uint64_t>(i) * 1000000000ULL / rate;
            for (unsigned c = 0; c < channels; ++c)
                dry[c * capacity + slot] = input[c] ? input[c][i] : 0.f;
            mono[i] = channels == 1 ? dry[slot] : .5f * (dry[slot] + dry[capacity + slot]);
        }
        bridge.publish(written, static_cast<int>(n), mono.data(), nullptr);
        written += n;
        accepted.fetch_add(n, std::memory_order_relaxed);
        awaitResult(n);
        const auto ready = std::min(written, bridge.wetEnd());
        const auto count = static_cast<unsigned>(std::clamp<int64_t>(ready - emitted, 0, maxBatch));
        if (!count) {
            pending.store(static_cast<unsigned>(written - emitted), std::memory_order_relaxed);
            return 0;
        }
        outTime = stamps[static_cast<unsigned>(emitted) & mask];
        for (unsigned c = 0; c < channels; ++c)
            out[c] = output.data() + c * maxBatch;
        const float target = strength * .01f, step = 1.f / rampSamples;
        for (unsigned i = 0; i < count; ++i) {
            const auto index = emitted + i;
            const unsigned slot = static_cast<unsigned>(index) & mask;
            const float wet = bridge.wet(index);
            amount += std::clamp(target - amount, -step, step);
            fade = std::min(1.f, fade + step);
            for (unsigned c = 0; c < channels; ++c)
                out[c][i] = fade * (amount * wet + (1.f - amount) * dry[c * capacity + slot]);
        }
        emitted += count;
        delivered.fetch_add(count, std::memory_order_relaxed);
        pending.store(static_cast<unsigned>(written - emitted), std::memory_order_relaxed);
        return count;
    }
    VoiceStats stats() const {
        return {bridge.state(), pending.load(), accepted.load(), delivered.load(), discarded.load()};
    }

  private:
    // The worker needs a few milliseconds for the frame a block completes. Waiting for it
    // here returns the result in this callback instead of the next one. The wait takes at
    // most 90% of the block, so the audio thread is back before the next block is due. One
    // that runs out is a strike and a result in time takes a strike back. After three close
    // together the waiting stops, so a GPU that is too slow leaves the timing as it was
    // without the wait, one callback behind. It resumes once the worker's slowest recent
    // frames have been within the allowance for 25 blocks in a row.
    void awaitResult(unsigned n) {
        const int64_t allowance = std::clamp<int64_t>(900000LL * n / rate, 1000, 20000);
        if (strikes < strikeLimit) {
            if (bridge.waitSettled(written, allowance))
                strikes = std::max(0, strikes - 1);
            else if ((strikes += strikeStep) >= strikeLimit)
                strikes = 2 * strikeLimit;
        } else {
            strikes = bridge.peakMicros() <= allowance ? strikes - 1 : 2 * strikeLimit;
        }
    }

    static constexpr unsigned maxBatch = 32768;
    static constexpr int strikeStep = 8, strikeLimit = 24;
    int strikes{};
    isolator::Bridge bridge;
    unsigned rate;
    std::vector<float> dry;
    std::vector<uint64_t> stamps;
    std::vector<float> mono, output;
    unsigned rampSamples, previousAdvance{};
    float amount = 1.f, fade{};
    bool streaming{};
    int64_t written{}, emitted{};
    std::atomic<unsigned> pending{};
    std::atomic<int64_t> accepted{}, delivered{}, discarded{};
};
void *openEngine(unsigned rate) {
    try {
        return new Engine(rate);
    } catch (...) {
        return nullptr;
    }
}
void closeEngine(void *p) {
    delete static_cast<Engine *>(p);
}
unsigned process(void *p, float *const *input, float **output, unsigned channels, unsigned n,
                 unsigned strength, unsigned advance, uint64_t ts, uint64_t &outTime, bool gap) {
    return static_cast<Engine *>(p)->render(input, output, channels, n, strength, advance, ts, outTime,
                                            gap);
}
VoiceStats getStats(void *p) {
    return static_cast<Engine *>(p)->stats();
}
const VoiceEngineApi api{openEngine, closeEngine, process, getStats};
} // namespace
extern "C" __declspec(dllexport) const VoiceEngineApi *VoiceEngineV1() {
    return &api;
}
