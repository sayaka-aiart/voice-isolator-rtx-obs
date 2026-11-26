#pragma once
#include <cstdint>

// The worker can load the small engine DLL without loading OBS and its dependencies.
struct VoiceStats {
    int state;
    unsigned pending;
    std::int64_t accepted, delivered, discarded;
};
struct VoiceEngineApi {
    void *(*open)(unsigned sampleRate);
    void (*close)(void *);
    unsigned (*process)(void *, float *const *input, float **output, unsigned channels, unsigned frames,
                        unsigned strength, unsigned advance, std::uint64_t timestamp,
                        std::uint64_t &outputTime, bool discontinuity);
    VoiceStats (*stats)(void *);
};
using VoiceEngineFactory = const VoiceEngineApi *(*)();
