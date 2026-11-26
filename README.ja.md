# Voice Isolator RTX OBS

[English](README.md)

Windows x64のOBS Studio用マイクフィルターです。NVIDIA RTXで話し声の環境音を抑えます。除去の強さは100%・80%・50%、合成の前倒しは0・5・10 msから選べます。

## インストール

`VoiceIsolatorRTX-OBS-1.3.0-Windows-x64.zip` をすべて展開し、OBSを終了してセットアップを起動します。既存の共通エンジンとモデルがそろっていれば追加ダウンロードは0件です。別の場所のモデルもセットアップ画面から指定できます。モデルとライブラリを個別に検査し、不足分だけを取得します。導入後、OBSのマイクの「フィルタ」から「Voice Isolator RTX OBS」を追加してください。[導入ガイド](release/windows/はじめに.txt)

OBS 28～32用の `bin\64bit` と、33以降用の直下の両方にプラグインが入ります。共通の配置先は `%ProgramData%\obs-studio\plugins\voice-isolator-rtx` です。既存シーンのフィルターIDを引き継ぎます。

## ビルド

`v1.3.0` をチェックアウトしてください。Windows x64、Visual Studio 2022 C++ビルドツール、CMake 3.24以降、OBS 28.0.0の公開ヘッダー、OBS x64が必要です。配布ZIPの作成にはPython 3.11以降とInno Setup 6を使います。Visual Studioのx64 Developer PowerShellで実行します。

```powershell
.\build.ps1 -ObsSource C:\src\obs-studio-28.0.0
python release/windows/package.py --payload stage/voice-isolator-rtx
```

`dist` にOBS専用のセットアップ、日本語の導入ガイド、ライセンス、対応ソースを含むZIPを生成します。[部品別ライセンス](LICENSES.md)
