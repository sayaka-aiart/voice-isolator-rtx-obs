// SPDX-License-Identifier: GPL-2.0-or-later
#include <windows.h>
#include <obs.h>
#include <util/platform.h>
#include <array>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>

namespace fs = std::filesystem;
using namespace std::chrono_literals;

namespace {
constexpr char id[] = "voice_isolator_rtx_native";
constexpr char moduleName[] = "voice-isolator-rtx";

void check(bool condition, const char *message) {
    if (!condition)
        throw std::runtime_error(message);
}

// Public OBS 33 obs_runtime_module_info ABI. Resolve the added entry point only
// on hosts that export it, so this same test executable also runs on OBS 28–32.
struct RuntimeModuleInfo {
    struct {
        const char *binary, *data;
    } path;
    int type;
    const char *name;
};
using LoadPlugins = void (*)(RuntimeModuleInfo *, obs_module_failure_info *);

void checkFailures(obs_module_failure_info &failures) {
    const auto count = failures.count;
    obs_module_failure_info_free(&failures);
    check(count == 0, "Plugin loader reported a failure");
}

void load(const fs::path &plugins, bool modern, bool modernOnly) {
    const auto base = (plugins / "%module%").generic_u8string();
    const auto data = base + "/data", legacy = base + "/bin/64bit";
    if (modern) {
        auto fn = reinterpret_cast<LoadPlugins>(
            GetProcAddress(GetModuleHandleW(L"obs.dll"), "obs_load_plugins"));
        check(fn != nullptr, "Missing modern plugin loader");
        for (const int type : {2, 3}) { // OBS_MODULE_TYPE_PLUGIN, OBS_MODULE_TYPE_LEGACY_PLUGIN
            if (type == 3 && modernOnly)
                break;
            RuntimeModuleInfo info{
                {type == 2 ? base.c_str() : legacy.c_str(), data.c_str()}, type, nullptr};
            obs_module_failure_info failures{};
            fn(&info, &failures);
            checkFailures(failures);
        }
    } else {
        check(!modernOnly, "Modern-only mode requires an OBS 33+ runtime");
        obs_add_module_path(legacy.c_str(), data.c_str());
        obs_module_failure_info failures{};
        obs_load_all_modules2(&failures);
        checkFailures(failures);
    }
}

struct State {
    long long ready, accepted, delivered, discarded;
};
State stats(obs_source_t *filter) {
    calldata_t result{};
    check(proc_handler_call(obs_source_get_proc_handler(filter), "voice_stats", &result),
          "Missing engine status");
    State state{calldata_int(&result, "state"), calldata_int(&result, "accepted"),
                calldata_int(&result, "delivered"), calldata_int(&result, "discarded")};
    calldata_free(&result);
    return state;
}

State testAudio(bool checkAlignment) {
    obs_source_info info{};
    info.id = "isolator_install_probe";
    info.type = OBS_SOURCE_TYPE_INPUT;
    info.output_flags = OBS_SOURCE_AUDIO;
    info.get_name = [](void *) { return "Installation test signal"; };
    info.create = [](obs_data_t *, obs_source_t *self) -> void * { return self; };
    info.destroy = [](void *) {};
    obs_register_source(&info);
    auto *source = obs_source_create_private(info.id, "Test input", nullptr);
    auto *filter = obs_source_create_private(id, "Installed filter", nullptr);
    check(source && filter, "Could not create filter or input");
    obs_source_filter_add(source, filter);
    const auto deadline = std::chrono::steady_clock::now() + 150s;
    while (stats(filter).ready == 0 && std::chrono::steady_clock::now() < deadline)
        std::this_thread::sleep_for(100ms);
    check(stats(filter).ready == 1, "GPU engine did not become ready");
    constexpr unsigned blockFrames = 480, smokeBlocks = 120;
    std::array<float, 4608> samples{};
    for (size_t i = 0; i < samples.size(); ++i)
        samples[i] = static_cast<float>(0.12 * std::sin(i * 2.0 * 3.14159265359 / 48.0));
    obs_source_audio packet{};
    packet.data[0] = packet.data[1] = reinterpret_cast<const uint8_t *>(samples.data());
    packet.speakers = SPEAKERS_STEREO;
    packet.format = AUDIO_FORMAT_FLOAT_PLANAR;
    packet.samples_per_sec = 48000;
    auto timestamp = os_gettime_ns();
    auto send = [&](unsigned frames) {
        packet.frames = frames;
        packet.timestamp = timestamp;
        obs_source_output_audio(source, &packet);
        const auto duration = uint64_t(frames) * 1000000000 / packet.samples_per_sec;
        timestamp += duration;
        std::this_thread::sleep_for(std::chrono::nanoseconds(duration));
    };
    for (unsigned block = 0; block < smokeBlocks; ++block)
        send(blockFrames);
    auto result = stats(filter);
    if (checkAlignment) {
        // Leave 64 slots at the end of the input ring before restarting the 480-frame stream.
        constexpr unsigned ringFrames = 1u << 18;
        for (unsigned block = smokeBlocks; block < ringFrames / blockFrames; ++block)
            send(blockFrames);
        for (const unsigned firstFrames : {blockFrames, static_cast<unsigned>(samples.size())}) {
            const auto before = stats(filter);
            timestamp += 200000000; // A gap starts a new stream with the same synthesis mode.
            send(firstFrames);
            for (unsigned block = 1; block < smokeBlocks; ++block)
                send(blockFrames);
            const auto after = stats(filter);
            const auto delivered = after.delivered - before.delivered;
            // Later model frames add whole 480-sample hops. Only the first packet sets the
            // output phase, even when it crosses the ring end or the 4096-frame read limit.
            check(delivered >= 48000 &&
                      (delivered - firstFrames) % blockFrames == result.delivered % blockFrames,
                  "Output phase does not match the first OBS packet");
        }
    }
    obs_source_filter_remove(source, filter);
    obs_source_release(filter);
    obs_source_release(source);
    check(result.accepted == 57600 && result.delivered >= 48000 && result.discarded == 0,
          "Audio did not traverse the installed GPU filter");
    return result;
}
} // namespace

int wmain(int argc, wchar_t **argv) {
    try {
        check(argc >= 3 && argc <= 5,
              "install-probe PLUGINS_DIR ISOLATED_PROFILE [modern-only] [check-alignment]");
        bool modernOnly = false, checkAlignment = false;
        for (int i = 3; i < argc; ++i) {
            const std::wstring arg = argv[i];
            if (arg == L"modern-only")
                modernOnly = true;
            else if (arg == L"check-alignment")
                checkAlignment = true;
            else
                throw std::runtime_error("Unknown mode");
        }
        const fs::path plugins = fs::absolute(argv[1]);
        check(obs_startup("en-US", fs::absolute(argv[2]).u8string().c_str(), nullptr),
              "OBS startup failed");
        obs_audio_info audio{48000, SPEAKERS_STEREO};
        check(obs_reset_audio(&audio), "OBS audio failed");
        const bool modern = (obs_get_version() >> 24) >= 33;
        load(plugins, modern, modernOnly);
        auto *module = obs_get_module(moduleName);
        check(module != nullptr, "Module was not discovered");
        const auto binary = fs::u8path(obs_get_module_binary_path(module));
        const auto data = fs::u8path(obs_get_module_data_path(module));
        const auto folder = plugins / moduleName;
        const auto expected = (modern ? folder : folder / "bin/64bit") / "voice-isolator-rtx.dll";
        check(fs::equivalent(binary, expected) && fs::equivalent(data, folder / "data"),
              "Wrong layout selected");
        size_t matches = 0;
        const char *type = nullptr;
        for (size_t i = 0; obs_enum_filter_types(i, &type); ++i)
            if (type && std::string(type) == id)
                ++matches;
        check(matches == 1, "Filter was not registered exactly once");
        check(std::string(obs_source_get_display_name(id)) == "Voice Isolator RTX OBS", "Unexpected filter display name");
        auto counts = testAudio(checkAlignment);
        std::cout << "INSTALL_PROBE " << obs_get_version_string() << " "
                  << (modern ? "flat" : "bin/64bit") << " registered=" << matches
                  << " accepted=" << counts.accepted << " delivered=" << counts.delivered
                  << " discarded=" << counts.discarded
                  << (checkAlignment ? " packet_alignment=verified" : "") << std::endl;
        obs_shutdown();
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << std::endl;
        return 1;
    }
}
