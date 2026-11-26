# Voice Isolator RTX OBS

[日本語](README.ja.md)

## 1. Build the OBS plugin

On Windows x64, install Git, CMake 3.24 or later, 64-bit OBS Studio, and Visual Studio 2022 Build Tools with the **Desktop development with C++** workload. From an x64 Visual Studio Developer PowerShell, clone both repositories into the same parent directory and build the plugin with the OBS 28.0.0 headers.

```powershell
git clone https://github.com/sayaka-aiart/voice-isolator-rtx-obs.git
git clone --depth 1 --branch 28.0.0 https://github.com/obsproject/obs-studio.git obs-studio-28.0.0
Set-Location .\voice-isolator-rtx-obs
.\build.ps1 -ObsSource ..\obs-studio-28.0.0
```

The build writes the plugin DLL, GPU adapter and Python worker to `stage\voice-isolator-rtx`. If OBS is installed outside its default location, pass `-ObsBin` with the path to the directory containing `obs.dll`.

## 2. Download the model and inference runtime

Use 64-bit PowerShell as the Windows user who runs OBS. If an existing Voice Isolator RTX installation already processes audio for that user, the plugin can use its registered engine. In that case, continue with step 3.

For a new engine, use an NVIDIA RTX 30-series or newer GPU with native BF16 support, a CUDA 12.8-compatible NVIDIA driver and the x64 Visual C++ v14 runtime. Run the following blocks in the same PowerShell session from the plugin repository root. [NVIDIA drivers](https://www.nvidia.com/Download/index.aspx) · [Visual C++ runtime](https://aka.ms/vc14/vc_redist.x64.exe)

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

The default engine directory is `%LOCALAPPDATA%\Programs\VoiceIsolatorRTX\engine-1.0.0`. An existing `EngineRoot` value takes precedence.

| Required files | Location under the engine directory |
| --- | --- |
| CPython 3.12.10 x64 | `python\python.exe` |
| Windows wheels, including PyTorch with CUDA and Triton | `python\Lib\site-packages\` |
| Inference code from this repository's `inference\` directory | `inworld\` |
| Inworld realtime model (233 MB) | `inworld\models\denoiser_realtime.safetensors` |

If you already have the model, copy it into `$models` before running the next block. A matching SHA-256 skips the model download. On a fresh machine the model and 30 wheels total about 3.77 GB, plus the private Python runtime. The manifest pins each download URL and hash. [Inworld model file](https://huggingface.co/inworld/voice-isolator/resolve/9b0285b3fe8403aa8e2f1dbb2165a80a4294c970/denoiser_realtime.safetensors) · [Dependency manifest](release/windows/assets.lock.json)

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

Test the engine on the GPU and register its directory for the current user.

```powershell
$log = Join-Path $env:TEMP 'VoiceIsolatorRTX-engine-check.log'
& "$runtime\python.exe" -I -B -X utf8 "$engine\prepare.py" diagnose $engine $log
if ($LASTEXITCODE -ne 0) { Get-Content -LiteralPath $log -Tail 20; throw 'GPU check failed' }
if (-not (Test-Path -LiteralPath $key)) { New-Item -Path $key -Force | Out-Null }
New-ItemProperty -LiteralPath $key -Name EngineRoot -PropertyType String -Value $engine -Force | Out-Null
```

## 3. Place the plugin files

Close OBS. Open an elevated 64-bit PowerShell in the same plugin repository and copy the staged files to the standard Windows OBS plugin folder.

```powershell
$plugin = Join-Path $env:ProgramData 'obs-studio\plugins\voice-isolator-rtx'
$legacy = Join-Path $plugin 'bin\64bit'
New-Item -ItemType Directory -Path $legacy -Force | Out-Null
Copy-Item -Path .\stage\voice-isolator-rtx\* -Destination $plugin -Recurse -Force
Copy-Item -LiteralPath .\stage\voice-isolator-rtx\voice-isolator-rtx.dll -Destination $legacy -Force
```

OBS 28–32 load `bin\64bit\voice-isolator-rtx.dll`. OBS 33 and later use `voice-isolator-rtx.dll` directly under the plugin folder. Both use the staged `data` directory, which contains the GPU adapter, worker scripts and license notices. After restarting OBS, look for **Voice Isolator RTX OBS** in the microphone's filter list.
