# Voice Isolator RTX OBS

[English](README.md)

## 1. OBSプラグインをビルドする

Windows x64にGit、CMake 3.24以降、64ビット版OBS Studio、Visual Studio 2022 Build Toolsを用意します。Build Toolsでは **「C++によるデスクトップ開発」** を選びます。Visual Studioのx64 Developer PowerShellを開き、同じ親フォルダーに2つのリポジトリを取得します。ビルドにはOBS 28.0.0のヘッダーを使います。

```powershell
git clone https://github.com/sayaka-aiart/voice-isolator-rtx-obs.git
git clone --depth 1 --branch 28.0.0 https://github.com/obsproject/obs-studio.git obs-studio-28.0.0
Set-Location .\voice-isolator-rtx-obs
.\build.ps1 -ObsSource ..\obs-studio-28.0.0
```

`stage\voice-isolator-rtx` にプラグインDLL、GPUアダプター、Pythonワーカーが生成されます。OBSを標準の場所以外にインストールしている場合は、`build.ps1` の `-ObsBin` に `obs.dll` があるフォルダーを指定してください。

## 2. モデルと推論環境を取得・配置する

OBSを使うWindowsユーザーの64ビットPowerShellで作業します。同じユーザーで既存のVoice Isolator RTXが音声を処理できていれば、登録済みの共通エンジンをそのまま使えます。その場合は手順3へ進んでください。

新規に用意する場合は、BF16対応のNVIDIA RTX 30シリーズ以降、CUDA 12.8対応のNVIDIAドライバー、Visual C++ v14ランタイム（x64）が必要です。以下のコードは、プラグインのリポジトリ直下で、同じPowerShellのまま順に実行します。[NVIDIAドライバー](https://www.nvidia.com/Download/index.aspx) · [Visual C++ランタイム](https://aka.ms/vc14/vc_redist.x64.exe)

```powershell
$ErrorActionPreference = 'Stop'
$key = 'HKCU:\Software\Local Audio Lab\Voice Isolator RTX'
$engine = Get-ItemPropertyValue -LiteralPath $key -Name EngineRoot -ErrorAction SilentlyContinue
if (-not $engine) {
    $engine = Join-Path $env:LOCALAPPDATA 'Programs\VoiceIsolatorRTX\engine-1.0.0'
}
$runtime = Join-Path $engine 'python'
$models = Join-Path $engine 'inworld\models'
$assets = Get-Content .\release\windows\assets.lock.json -Raw -Encoding UTF8 | ConvertFrom-Json
New-Item -ItemType Directory -Path $runtime, $models -Force | Out-Null
```

推論環境の標準フォルダーは `%LOCALAPPDATA%\Programs\VoiceIsolatorRTX\engine-1.0.0` です。`EngineRoot` が登録済みならその場所を使います。

| 必要なファイル | 推論環境のルートからの配置先 |
| --- | --- |
| CPython 3.12.10（x64） | `python\python.exe` |
| CUDA版PyTorch・Tritonを含むWindows用ライブラリ | `python\Lib\site-packages\` |
| このリポジトリの `inference\` 内のコード | `inworld\` |
| Inworldのリアルタイムモデル（約233 MB） | `inworld\models\denoiser_realtime.safetensors` |

モデルをすでに持っている場合は、次のコードを実行する前に `$models` が示すフォルダーへコピーしてください。SHA-256が一致すればモデルのダウンロードを省きます。初回のモデルとライブラリ30個の取得量は合計約3.77 GBで、このほかに専用Pythonを取得します。各ファイルの取得先とSHA-256は一覧で確認できます。[Inworldのモデルファイル](https://huggingface.co/inworld/voice-isolator/resolve/9b0285b3fe8403aa8e2f1dbb2165a80a4294c970/denoiser_realtime.safetensors) · [依存ファイル一覧](release/windows/assets.lock.json)

```powershell
function Save-VerifiedFile($asset, $path) {
    if ((Test-Path -LiteralPath $path -PathType Leaf) -and
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -eq $asset.sha256) { return }
    $part = "$path.part"
    curl.exe --fail --location --retry 3 --silent --show-error --output $part $asset.url
    if ($LASTEXITCODE -ne 0) { throw "Download failed for $path" }
    if ((Get-FileHash -LiteralPath $part -Algorithm SHA256).Hash -ne $asset.sha256) {
        throw "SHA-256 mismatch for $path"
    }
    Move-Item -LiteralPath $part -Destination $path -Force
}

$package = Join-Path $env:TEMP 'VoiceIsolatorRTX-python-3.12.10.nupkg'
Save-VerifiedFile $assets.python $package
tar.exe -xf $package -C $runtime --strip-components 1 'tools/*'
if ($LASTEXITCODE -ne 0) { throw 'Could not extract Python' }
@('.', 'Lib', 'DLLs', 'Lib/site-packages', 'import site') |
    Set-Content -LiteralPath "$runtime\python312._pth" -Encoding ascii

Copy-Item -Path .\inference\* -Destination "$engine\inworld" -Recurse -Force
Copy-Item -LiteralPath .\release\windows\prepare.py, .\release\windows\assets.lock.json -Destination $engine -Force
Save-VerifiedFile $assets.model (Join-Path $models $assets.model.filename)

$requirements = Join-Path $engine 'requirements.lock'
$assets.wheels | ForEach-Object { "$($_.package) @ $($_.url) --hash=sha256:$($_.sha256)" } |
    Set-Content -LiteralPath $requirements -Encoding ascii
& "$runtime\python.exe" -I -B -m pip --isolated --disable-pip-version-check install --no-index --no-deps --require-hashes --no-compile --no-cache-dir --no-warn-script-location -r $requirements
if ($LASTEXITCODE -ne 0) { throw 'Could not install the locked wheels' }
```

GPUで音声を処理できることを確認してから、推論環境の場所を現在のユーザーに登録します。

```powershell
$log = Join-Path $env:TEMP 'VoiceIsolatorRTX-engine-check.log'
& "$runtime\python.exe" -I -B -X utf8 "$engine\prepare.py" diagnose $engine $log
if ($LASTEXITCODE -ne 0) { Get-Content -LiteralPath $log -Tail 20; throw 'GPU check failed' }
if (-not (Test-Path -LiteralPath $key)) { New-Item -Path $key -Force | Out-Null }
New-ItemProperty -LiteralPath $key -Name EngineRoot -PropertyType String -Value $engine -Force | Out-Null
```

## 3. OBSにプラグインを配置する

OBSを終了し、同じプラグインのリポジトリ直下で64ビットPowerShellを管理者として開きます。次のコマンドで通常インストール版OBSのプラグインフォルダーに配置します。

```powershell
$plugin = Join-Path $env:ProgramData 'obs-studio\plugins\voice-isolator-rtx'
$legacy = Join-Path $plugin 'bin\64bit'
New-Item -ItemType Directory -Path $legacy -Force | Out-Null
Copy-Item -Path .\stage\voice-isolator-rtx\* -Destination $plugin -Recurse -Force
Copy-Item -LiteralPath .\stage\voice-isolator-rtx\voice-isolator-rtx.dll -Destination $legacy -Force
```

OBS 28～32は `bin\64bit\voice-isolator-rtx.dll` を、OBS 33以降はプラグインフォルダー直下の `voice-isolator-rtx.dll` を読み込みます。どちらも `data` 内のGPUアダプター、ワーカー、ライセンス表記を共用します。OBSを再起動すると、マイクのフィルター一覧で **Voice Isolator RTX OBS** を選べます。
