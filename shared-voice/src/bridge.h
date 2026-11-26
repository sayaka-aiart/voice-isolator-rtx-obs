#pragma once
#include <windows.h>
#include <cstdint>
#include <string>

namespace isolator {
constexpr int64_t capacity = 1 << 18;
constexpr int64_t protocol = 0x495749333804LL;
enum Field { Magic, Stop, State, Epoch, Origin, InputEnd, Consumed, WetEpoch, WetEnd, Pid, AdvanceMode,
             Settled, PeakMicros, FirstPacketFrames, NumFields };
struct alignas(64) Shared {
    volatile LONG64 h[16];
    float input[capacity];
    float output[capacity];
};
static_assert(sizeof(Shared) == 128 + 8 * capacity);

class Bridge {
public:
    ~Bridge() { close(); }
    bool start(double sampleRate);
    void close();
    int state() const;
    void reset(int64_t cursor, int64_t advanceMode, int64_t firstPacketFrames);
    void publish(int64_t first, int count, const float* left, const float* right);
    int64_t wetEnd() const;
    float wet(int64_t pos) const { return shared->output[pos & (capacity - 1)]; }
    bool waitReady();
    void waitWet(int64_t target);
    // Input position up to which the worker has computed everything it can.
    int64_t settled() const;
    // Microseconds the worker's slowest recent frames took from picking up their input.
    // The figure fades by 3% with every batch of frames.
    int64_t peakMicros() const { return shared ? read(PeakMicros) : 0; }
    // Waits until settled() reaches target, for at most 'micros'. False when time ran out.
    bool waitSettled(int64_t target, int64_t micros);
    int64_t origin = 0;
private:
    Shared* shared = nullptr;
    HANDLE mapping = nullptr, inputEvent = nullptr, outputEvent = nullptr, process = nullptr, job = nullptr;
    HANDLE timer = nullptr;
    LONG64 epoch = 0;
    int64_t read(Field field) const { return InterlockedCompareExchange64(&shared->h[field], 0, 0); }
    void store(Field field, int64_t value) { InterlockedExchange64(&shared->h[field], value); }
};
}
