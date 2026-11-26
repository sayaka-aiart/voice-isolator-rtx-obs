// SPDX-License-Identifier: GPL-2.0-or-later
#include <windows.h>
#include <obs-module.h>
#include <util/platform.h>
#include "engine_api.h"
#include <algorithm>
#include <atomic>
#include <cstdlib>
#include <filesystem>
#include <memory>
#include <string>

OBS_DECLARE_MODULE()
OBS_MODULE_AUTHOR("Local Audio Lab")

namespace {
struct Filter {
    obs_source_t *source{};
    HMODULE library{};
    const VoiceEngineApi *api{};
    void *engine{};
    unsigned rate{}, channels{};
    std::uint64_t nextTimestamp{};
    obs_audio_data output{};
    std::atomic<unsigned> settings{100};
    ~Filter() {
        if (engine)
            api->close(engine);
        if (library)
            FreeLibrary(library);
    }
};
const char *name(void *) {
    return "Voice Isolator RTX";
}

void update(void *data, obs_data_t *settings) {
    auto &f = *static_cast<Filter *>(data);
    const auto selected = obs_data_get_int(settings, "strength");
    const unsigned strength = selected == 50 || selected == 80 ? static_cast<unsigned>(selected) : 100u;
    const unsigned advance =
        static_cast<unsigned>(std::clamp<long long>(obs_data_get_int(settings, "advance"), 0, 2));
    f.settings.store(strength | (advance << 8));
}
void defaults(obs_data_t *settings) {
    obs_data_set_default_int(settings, "strength", 100);
    obs_data_set_default_int(settings, "advance", 0);
}
void statusProc(void *data, calldata_t *args) {
    auto &f = *static_cast<Filter *>(data);
    const auto s = f.engine ? f.api->stats(f.engine) : VoiceStats{-1, 0, 0, 0, 0};
    calldata_set_int(args, "state", s.state);
    calldata_set_int(args, "pending", s.pending);
    calldata_set_int(args, "accepted", s.accepted);
    calldata_set_int(args, "delivered", s.delivered);
    calldata_set_int(args, "discarded", s.discarded);
}
void *create(obs_data_t *s, obs_source_t *source) {
    auto f = std::make_unique<Filter>();
    f->source = source;
    auto audio = obs_get_audio();
    if (!audio)
        return nullptr;
    f->rate = audio_output_get_sample_rate(audio);
    f->channels = static_cast<unsigned>(audio_output_get_channels(audio));
    char *file = obs_module_file("worker/x64/voice-rtx-engine.dll");
    if (file) {
        auto path = std::filesystem::u8path(file);
        bfree(file);
        f->library = LoadLibraryW(path.c_str());
    }
    if (f->library) {
        auto factory =
            reinterpret_cast<VoiceEngineFactory>(GetProcAddress(f->library, "VoiceEngineV1"));
        if (factory) {
            f->api = factory();
            f->engine = f->api->open(f->rate);
        }
    }
    if (!f->engine)
        blog(LOG_WARNING, "[Voice Isolator RTX] Could not open the inference engine.");
    update(f.get(), s);
    proc_handler_add(obs_source_get_proc_handler(source),
                     "void voice_stats(out int state, out int pending, out int accepted, out int "
                     "delivered, out int discarded)",
                     statusProc, f.get());
    return f.release();
}
obs_audio_data *filterAudio(void *data, obs_audio_data *audio) {
    auto &f = *static_cast<Filter *>(data);
    float *planes[MAX_AV_PLANES]{};
    for (unsigned c = 0; c < f.channels; ++c)
        planes[c] = reinterpret_cast<float *>(audio->data[c]);
    const auto ts = audio->timestamp;
    const auto delta = ts >= f.nextTimestamp ? ts - f.nextTimestamp : f.nextTimestamp - ts;
    const bool gap = f.nextTimestamp && delta > 100000000;
    f.nextTimestamp = ts + static_cast<std::uint64_t>(audio->frames) * 1000000000u / f.rate;
    const unsigned s = f.settings.load(std::memory_order_relaxed);
    if (!f.engine)
        return nullptr;
    float *out[MAX_AV_PLANES]{};
    f.output.frames = f.api->process(f.engine, planes, out, f.channels, audio->frames, s & 255,
                                     (s >> 8) & 3, ts, f.output.timestamp, gap);
    if (!f.output.frames)
        return nullptr;
    for (unsigned c = 0; c < f.channels; ++c)
        f.output.data[c] = reinterpret_cast<uint8_t *>(out[c]);
    return &f.output;
}
bool setStrength(obs_properties_t *, obs_property_t *p, void *data) {
    if (!data)
        return false;
    auto &f = *static_cast<Filter *>(data);
    const auto n = std::atoi(obs_property_name(p) + 1);
    auto *s = obs_source_get_settings(f.source);
    obs_data_set_int(s, "strength", n);
    obs_source_update(f.source, s);
    obs_data_release(s);
    obs_source_update_properties(f.source);
    return true;
}
obs_properties_t *properties(void *data) {
    auto *f = static_cast<Filter *>(data);
    auto *p = obs_properties_create();
    const unsigned chosen = f ? (f->settings.load() & 255u) : 100u;
    for (int v : {100, 80, 50}) {
        const auto key = "s" + std::to_string(v);
        const auto label = std::to_string(v) + (v == static_cast<int>(chosen) ? "%  ✓" : "%");
        obs_properties_add_button2(p, key.c_str(), label.c_str(), setStrength, f);
    }
    auto *m = obs_properties_add_list(p, "advance", "合成の前倒し", OBS_COMBO_TYPE_LIST,
                                      OBS_COMBO_FORMAT_INT);
    obs_property_list_add_int(m, "0 ms", 0);
    obs_property_list_add_int(m, "5 ms", 1);
    obs_property_list_add_int(m, "10 ms", 2);
    if (f) {
        const auto s = f->engine ? f->api->stats(f->engine) : VoiceStats{-1, 0, 0, 0, 0};
        std::string line = s.state == 1   ? "GPU 使用可能"
                           : s.state == 0 ? "GPU 準備中"
                                          : "GPU を使用できません";
        obs_properties_add_text(p, "gpu_status", line.c_str(), OBS_TEXT_INFO);
        obs_properties_add_button2(
            p, "refresh_status", "状態を更新",
            [](obs_properties_t *, obs_property_t *, void *d) {
                obs_source_update_properties(static_cast<Filter *>(d)->source);
                return true;
            },
            f);
    }
    return p;
}
} // namespace
MODULE_EXPORT const char *obs_module_description(void) {
    return "Voice Isolator RTX native microphone filter";
}
bool obs_module_load(void) {
    obs_source_info info{};
    info.id = "voice_isolator_rtx_native";
    info.type = OBS_SOURCE_TYPE_FILTER;
    info.output_flags = OBS_SOURCE_AUDIO;
    info.get_name = name;
    info.create = create;
    info.destroy = [](void *data) { delete static_cast<Filter *>(data); };
    info.update = update;
    info.get_defaults = defaults;
    info.get_properties = properties;
    info.filter_audio = filterAudio;
    obs_register_source(&info);
    return true;
}
