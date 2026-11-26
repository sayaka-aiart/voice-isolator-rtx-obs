# Voice Isolator RTX OBS

[日本語](README.ja.md)

Voice Isolator RTX OBS 1.3.0 is a Windows x64 audio filter for OBS Studio. It isolates speech on a local NVIDIA RTX GPU. It offers 100%, 80% or 50% noise reduction and 0, 5 or 10 ms of synthesis advance.

## Install

Extract `VoiceIsolatorRTX-OBS-1.3.0-Windows-x64.zip`, close OBS and run the included setup as the Windows user who runs OBS. On first installation it downloads only the missing locked libraries and the original Inworld realtime model. A complete shared engine from Voice Isolator RTX needs no network download. Setup verifies local model and library files. A model stored elsewhere can be selected in the wizard or passed with `/MODEL="C:\models\denoiser_realtime.safetensors"`. Open the microphone's **Filters** and add **Voice Isolator RTX OBS**. [Japanese installation guide](release/windows/はじめに.txt)

The module goes to `%ProgramData%\obs-studio\plugins\voice-isolator-rtx`. OBS 28–32 use `bin\64bit`. OBS 33 introduced the flat layout. Both use the same data folder. The filter's internal ID is preserved for existing scenes.

## Build the OBS-only distribution

Use Windows x64, Visual Studio 2022 C++ Build Tools, CMake 3.24+, the OBS 28.0.0 source headers, and a 64-bit OBS installation. In an x64 Visual Studio Developer PowerShell, build from the `v1.3.0` tag. The last command requires Python 3.11+ and Inno Setup 6 with download-page SHA-256 support.

```powershell
.\build.ps1 -ObsSource C:\src\obs-studio-28.0.0
python release/windows/package.py --payload stage/voice-isolator-rtx
```

The command verifies the CPython package, builds the module installer and per-user engine setup, and places the recipient ZIP in `dist`. The corresponding source inside the ZIP comes from the checked-out commit. [OBS 28.0.0 headers](https://github.com/obsproject/obs-studio/tree/28.0.0) · [License map](LICENSES.md)
