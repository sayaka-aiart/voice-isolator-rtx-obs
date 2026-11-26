# Voice Isolator RTX for OBS Studio

[日本語](README.ja.md)

A native Windows x64 microphone filter for OBS Studio. It runs Inworld Voice Isolator on a local NVIDIA RTX GPU. Open the microphone's **Filters** panel and add **Voice Isolator RTX**. The filter provides 100%, 80% and 50% noise reduction and 0, 5 or 10 ms of synthesis advance.

## Install

In the Windows Voice Isolator RTX **1.3.0** distribution, run the setup as the Windows user who runs OBS and select **OBS plugin only**. On first use, setup downloads the shared inference engine dependencies and original model (about 3.77 GB in total), verifies SHA-256 and tests CUDA. The filter module installs in both Windows OBS layouts under `%ProgramData%\obs-studio\plugins\voice-isolator-rtx`. OBS 28–32 use `bin\64bit`; OBS 33 introduced the flat layout. After loading, refresh the filter's status to check the GPU engine.

## Build the filter

On Windows x64, use Visual Studio 2022 C++ Build Tools, CMake 3.24 or newer, the OBS 28.0.0 source headers and a 64-bit OBS installation. Run in a Visual Studio **Developer PowerShell for x64** from this checkout. [OBS 28.0.0 source](https://github.com/obsproject/obs-studio/tree/28.0.0)

```powershell
.\build.ps1 -ObsSource C:\src\obs-studio-28.0.0
```

The script builds the two DLLs and stages the module, worker scripts and notices in `stage\voice-isolator-rtx`. The installed shared inference engine is required to run audio. To build the Windows OBS module installer and include its corresponding source, install Inno Setup 6 and run these commands from the tag you intend to distribute.

```powershell
New-Item -ItemType Directory -Path dist -Force | Out-Null
git archive --format=zip -o dist/VoiceIsolatorRTX-OBS-source.zip HEAD
.\release\build-installer.ps1 -Payload stage\voice-isolator-rtx -SourceArchive dist\VoiceIsolatorRTX-OBS-source.zip -OutputDir dist
```

## Source and licenses

Tag **v0.1.1** contains the source for the OBS module shipped in the **1.3.0** suite. The OBS filter and its native adapter are GPL-2.0-or-later. The original MIT and Apache-2.0 notices are included for shared code and Inworld respectively. The VST3 implementation has its own repository. [License map](LICENSES.md) · [GPL text](LICENSE) · [VST3 source](https://github.com/sayaka-aiart/voice-isolator-rtx-vst3)
