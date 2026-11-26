param(
    [Parameter(Mandatory=$true)][string]$ObsSource,
    [string]$ObsBin = "$env:ProgramFiles\obs-studio\bin\64bit",
    [string]$BuildDir = (Join-Path $PSScriptRoot 'build'),
    [string]$StageDir = (Join-Path $PSScriptRoot 'stage')
)
$ErrorActionPreference = 'Stop'
$obsHeaders = (Resolve-Path -LiteralPath $ObsSource).Path
$libobs = (Resolve-Path -LiteralPath (Join-Path $ObsBin 'obs.dll')).Path
$build = [IO.Path]::GetFullPath($BuildDir)
$imports = Join-Path $build 'obs-import'
New-Item -ItemType Directory -Path $imports -Force | Out-Null
$dump = & dumpbin.exe /nologo /exports $libobs
if ($LASTEXITCODE -ne 0) { throw 'dumpbin could not read obs.dll' }
$exports = foreach ($line in $dump) {
    if ($line -match '^\s*\d+\s+[0-9A-Fa-f]+\s+[0-9A-Fa-f]+\s+([A-Za-z_][A-Za-z0-9_]*)\b') { $Matches[1] }
}
if ($exports -notcontains 'obs_register_source_s') { throw 'Missing libobs exports' }
$def = Join-Path $imports 'obs.def'
$lib = Join-Path $imports 'obs.lib'
@('LIBRARY obs.dll','EXPORTS') + $exports | Set-Content -Encoding ascii -LiteralPath $def
& lib.exe /nologo /machine:x64 "/def:$def" "/out:$lib"
if ($LASTEXITCODE -ne 0) { throw 'obs.lib creation failed' }
@('#pragma once','#define OBS_INSTALL_PREFIX ""','#define OBS_DATA_PATH "data"','#define OBS_PLUGIN_PATH "obs-plugins"','#define OBS_PLUGIN_DESTINATION "64bit"','#define OBS_RELEASE_CANDIDATE 0','#define OBS_BETA 0') | Set-Content -Encoding ascii -LiteralPath (Join-Path $imports 'obsconfig.h')
& cmake -S $PSScriptRoot -B $build -G 'Visual Studio 17 2022' -A x64 "-DOBS_SOURCE=$obsHeaders" "-DOBS_CONFIG_DIR=$imports" "-DOBS_IMPORT_LIBRARY=$lib"
if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed' }
& cmake --build $build --config Release --parallel
if ($LASTEXITCODE -ne 0) { throw 'C++ build failed' }
& cmake --install $build --config Release --prefix ([IO.Path]::GetFullPath($StageDir))
if ($LASTEXITCODE -ne 0) { throw 'CMake install failed' }
