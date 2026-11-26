param(
    [Parameter(Mandatory=$true)][string]$Payload,
    [Parameter(Mandatory=$true)][string]$SourceArchive,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [string]$Iscc = (Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Inno Setup 6\ISCC.exe')
)
$ErrorActionPreference = 'Stop'
$payloadPath = (Resolve-Path -LiteralPath $Payload).Path
$sourcePath = (Resolve-Path -LiteralPath $SourceArchive).Path
$releasePath = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $releasePath -Force | Out-Null
& $Iscc /Q '/DReleaseVersion=0.1.1' "/DPayload=$payloadPath" "/DSourceArchive=$sourcePath" "/DReleaseDir=$releasePath" (Join-Path $PSScriptRoot 'setup.iss')
if ($LASTEXITCODE -ne 0) { throw 'OBS installer build failed' }
