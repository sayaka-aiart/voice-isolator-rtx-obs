# Voice Isolator RTX for OBS Studio

[English](README.md)

Windows x64 の OBS で使うマイク用ノイズ除去フィルターです。Inworld Voice Isolator を PC 内の RTX GPU で実行します。OBS の音声ミキサーでマイクを右クリックし、「フィルタ」→「＋」→「Voice Isolator RTX」を選びます。除去の強さは 100%・80%・50%、合成の前倒しは 0・5・10 ms です。

## インストール

配布版 **1.3.0** の ZIP を展開し、普段 OBS を使う Windows ユーザーでセットアップを起動します。「OBS プラグインのみ」を選ぶと、共通エンジンとモデルも自動で入ります。初回に必要なライブラリとモデルは合計約3.77 GBです。モデルの SHA-256 を照合し、短い音声を GPU で処理して確認します。OBS の配置時に管理者確認が表示される場合があります。

エンジンの標準のモデル配置先は `%LOCALAPPDATA%\Programs\VoiceIsolatorRTX\engine-1.0.0\inworld\models\denoiser_realtime.safetensors` です。フィルターは `%ProgramData%\obs-studio\plugins\voice-isolator-rtx` に入ります。OBS 28～32 用の `bin\64bit` と OBS 33 以降用の直下に同じ DLL を配置し、data を共用します。フィルターの「状態を更新」で「GPU 使用可能」を確認できます。

## ビルドとライセンス

Visual Studio 2022 の x64 Developer PowerShell からビルドできます。必要なツール・コマンド・出力先は英語版に記載しています。[ビルド手順](README.md#build-the-filter)

タグ **v0.1.1** が配布版 **1.3.0** に収録した OBS モジュールの対応ソースです。OBS フィルターとネイティブアダプターは GPL-2.0-or-later です。共通コードの MIT 表記と、Inworld の Apache-2.0 ライセンス・NOTICE も収録しています。[部品別ライセンス](LICENSES.md) · [GPL 本文](LICENSE) · [VST3 のソース](https://github.com/sayaka-aiart/voice-isolator-rtx-vst3)
