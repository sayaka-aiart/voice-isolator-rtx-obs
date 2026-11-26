# Licenses and corresponding source

| Part | Terms and provenance |
| --- | --- |
| OBS module, native audio adapter, build and packaging files | GPL-2.0-or-later. See [LICENSE](LICENSE). The distributed native binaries are `voice-isolator-rtx.dll` and `data/worker/x64/voice-rtx-engine.dll`. |
| Shared IPC bridge and Python GPU worker under `shared-voice` | Original code by Voice Isolator RTX contributors, used under the [MIT license](shared-voice/LICENSE). The native adapter links the bridge. The shared GPU warm-up code comes from [the VST3 implementation](https://github.com/sayaka-aiart/voice-isolator-rtx-vst3/tree/8562723b6be83f7c4b6b8b16e7b2cadb48f6115f). The OBS worker also handles OBS input packet timing. |
| Inworld Voice Isolator upstream implementation and separately downloaded model | Apache-2.0. Keep the [Inworld license](shared-voice/licenses/Inworld-LICENSE.txt) and [original NOTICE](shared-voice/licenses/Inworld-NOTICE.txt). The local worker uses streaming and CUDA optimizations. [Pinned model revision](https://huggingface.co/inworld/voice-isolator/tree/9b0285b3fe8403aa8e2f1dbb2165a80a4294c970) |
| OBS Studio | The module uses the public libobs API. OBS Studio is a separate application. [OBS source and license](https://github.com/obsproject/obs-studio/blob/28.0.0/COPYING) |

You may use, modify and redistribute the OBS filter under the accompanying GPL. Preserve the applicable copyright, license and attribution notices. When distributing binaries, supply the corresponding source for the version you distribute as required by the license. Each OBS 1.3.0 ZIP includes its matching source archive. [Revision 3 source](https://github.com/sayaka-aiart/voice-isolator-rtx-obs/tree/v1.3.0-r3) · [Revision 2 source](https://github.com/sayaka-aiart/voice-isolator-rtx-obs/tree/v1.3.0-r2) · [Original 1.3.0 source](https://github.com/sayaka-aiart/voice-isolator-rtx-obs/tree/v1.3.0)

The local shared engine optimizations in the top level of `inference` use the shared MIT license. The original implementation under `inference/inworld/voice_isolation` is Apache-2.0. CPython and the downloaded PyTorch, CUDA, Triton and other runtime dependencies retain their respective terms. [Windows distribution notices](release/windows/LICENSES.txt)
