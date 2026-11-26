[Setup]
AppId={{84F2C516-752E-403B-B8A9-4EAEB7BD9263}
AppName=Voice Isolator RTX for OBS
AppVersion={#ReleaseVersion}
AppPublisher=Local Audio Lab
DefaultDirName={commonappdata}\obs-studio\plugins\voice-isolator-rtx
DisableDirPage=yes
DisableProgramGroupPage=yes
UsePreviousAppDir=no
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
OutputDir={#ReleaseDir}
OutputBaseFilename=VoiceIsolatorRTX-OBS-{#ReleaseVersion}-Setup-x64
VersionInfoVersion={#ReleaseVersion}.0
VersionInfoDescription=Voice Isolator RTX audio filter for OBS Studio
UninstallDisplayName=Voice Isolator RTX for OBS
UninstallFilesDir={code:UninstallerDir}
CreateUninstallRegKey=IsAdminInstallMode
SetupMutex=Local\VoiceIsolatorRTXOBSSetup
CloseApplications=no
RestartApplications=no

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; OBS 33 searches the flat layout first. OBS 28–32 use bin/64bit. Both use data/.
Source: "{#Payload}\voice-isolator-rtx.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Payload}\voice-isolator-rtx.dll"; DestDir: "{app}\bin\64bit"; Flags: ignoreversion
Source: "{#Payload}\data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs
Source: "{#SourceArchive}"; DestDir: "{app}\data\licenses"; DestName: "VoiceIsolatorRTX-OBS-source.zip"; Flags: ignoreversion

[Code]
function UninstallerDir(Param: String): String;
begin
  if IsAdminInstallMode then
    Result := ExpandConstant('{commonpf}\Local Audio Lab\Voice Isolator RTX for OBS')
  else
    Result := ExpandConstant('{app}\setup');
end;
