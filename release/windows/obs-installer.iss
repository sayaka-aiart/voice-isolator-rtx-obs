[Setup]
AppId={{B67B4259-85B2-401B-9B42-A3FD5D438112}
AppName=Voice Isolator RTX OBS
AppVersion={#Version}
AppPublisher=Local Audio Lab
DefaultDirName={localappdata}\Programs\VoiceIsolatorRTX\OBS-Setup
DisableWelcomePage=no
DisableDirPage=yes
DisableProgramGroupPage=yes
UsePreviousAppDir=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.17763
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
OutputDir={#Output}
OutputBaseFilename=VoiceIsolatorRTX-OBS-{#Version}-Setup-x64
VersionInfoVersion={#Version}.0
VersionInfoDescription=Voice Isolator RTX OBS installer
VersionInfoProductName=Voice Isolator RTX OBS
UninstallDisplayName=Voice Isolator RTX OBS - {cm:Shared}
SetupMutex=Local\VoiceIsolatorRTXSetup
CloseApplications=no
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
ja.Shared=共通エンジンのセットアップ
en.Shared=Shared engine setup
ja.Model=既存モデルの指定（任意）
en.Model=Existing model (optional)
ja.ModelInfo=既存の共通エンジンとモデルを自動で探します。
en.ModelInfo=Setup searches for your installed shared engine and model automatically.
ja.ModelHelp=通常は空欄で「次へ」を押してください。別の場所に保存した denoiser_realtime.safetensors を使う場合は選択してください。SHA-256 が一致するモデルを再利用し、足りないファイルだけを取得します。
en.ModelHelp=Leave this blank for automatic detection. To reuse denoiser_realtime.safetensors from a different folder, select it here. Setup verifies SHA-256 and downloads only missing assets.
ja.Check=GPU環境と既存ファイルを確認しています
en.Check=Checking the GPU environment and existing files
ja.Network=不足しているファイルを取得しています
en.Network=Downloading missing files
ja.GPU=GPUで音声を処理して確認しています
en.GPU=Testing audio processing on the GPU
ja.Admin=OBSを閉じ、プラグインの配置時に管理者確認を許可してください。
en.Admin=Close OBS and allow elevation when the OBS module is installed.
ja.Failed=詳しい原因はログを参照してください。
en.Failed=See the setup log for details.

[Files]
Source: "{#Bootstrap}"; Flags: dontcopy
Source: "{#ModuleSetup}"; DestName: "obs-module-setup.exe"; Flags: dontcopy
#define EngineExcludes "\cache\*,\python\Scripts\*,*.pyc,setup_assets.py"
Source: "{tmp}\engine\*"; DestDir: "{code:EngineDir}"; Excludes: "{#EngineExcludes}"; ExternalSize: 0; Flags: external recursesubdirs ignoreversion; Check: CopyOwnedEngine
Source: "{tmp}\engine\*"; DestDir: "{code:EngineDir}"; Excludes: "{#EngineExcludes}"; ExternalSize: 0; Flags: external recursesubdirs ignoreversion uninsneveruninstall; Check: RepairOtherEngine
Source: "{#Docs}\はじめに.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Docs}\LICENSES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Registry]
Root: HKCU64; Subkey: "Software\Local Audio Lab\Voice Isolator RTX"; ValueType: string; ValueName: "EngineRoot"; ValueData: "{code:EngineDir}"; Flags: uninsdeletevalue; Check: RegisterEngine

[INI]
Filename: "{app}\owner.ini"; Section: "Engine"; Key: "Directory"; String: "{code:EngineDir}"; Check: CopyOwnedEngine

[UninstallDelete]
Type: files; Name: "{app}\owner.ini"

[Code]
var
  ModelPage: TInputFileWizardPage;
  DownloadPage: TDownloadWizardPage;
  Progress: TOutputMarqueeProgressWizardPage;
  Needed: TStringList;
  Engine, LogPath: String;
  Reuse, HadRegisteredEngine, OwnsEngine: Boolean;

function EngineDir(Param: String): String;
begin
  Result := Engine;
end;
function CopyOwnedEngine: Boolean;
begin
  Result := not Reuse and OwnsEngine;
end;
function RepairOtherEngine: Boolean;
begin
  Result := not Reuse and not OwnsEngine;
end;
function RegisterEngine: Boolean;
begin
  Result := not HadRegisteredEngine;
end;
function Q(const S: String): String;
begin
  Result := '"' + S + '"';
end;
procedure InitializeWizard;
begin
  HadRegisteredEngine := RegQueryStringValue(HKCU64, 'Software\Local Audio Lab\Voice Isolator RTX', 'EngineRoot', Engine) and DirExists(Engine);
  if not HadRegisteredEngine then
    Engine := ExpandConstant('{localappdata}\Programs\VoiceIsolatorRTX\engine-1.0.0');
  OwnsEngine := (not HadRegisteredEngine and not FileExists(Engine + '\python\python.exe')) or
    (CompareText(GetIniString('Engine', 'Directory', '', ExpandConstant('{localappdata}\Programs\VoiceIsolatorRTX\OBS-Setup\owner.ini')), Engine) = 0);
  ModelPage := CreateInputFilePage(wpWelcome, CustomMessage('Model'), CustomMessage('ModelInfo'), CustomMessage('ModelHelp'));
  ModelPage.Add('Inworld Voice Isolator', 'SafeTensors|*.safetensors', '.safetensors');
  ModelPage.Values[0] := ExpandConstant('{param:MODEL|}');
  DownloadPage := CreateDownloadPage(CustomMessage('Network'), '', nil);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
  Progress := CreateOutputMarqueeProgressPage(CustomMessage('Check'), '');
  LogPath := AddBackslash(ExtractFileDir(ExpandConstant('{tmp}'))) + 'VoiceIsolatorRTX-OBS-' +
    GetDateTimeString('yyyymmdd-hhnnss', '-', '-') + '.log';
  Needed := TStringList.Create;
end;
procedure DeinitializeSetup;
begin
  if Assigned(Needed) then Needed.Free;
end;
function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := 'Voice Isolator RTX OBS {#Version}' + NewLine + NewLine + CustomMessage('ModelHelp') +
    NewLine + NewLine + CustomMessage('Admin');
end;
procedure RunChecked(const ProgramName, Args, Directory: String);
var Code: Integer;
begin
  if not Exec(ProgramName, Args, Directory, SW_HIDE, ewWaitUntilTerminated, Code) then
    RaiseException(SysErrorMessage(Code));
  if Code <> 0 then RaiseException(Format('%s (%d)', [ExtractFileName(ProgramName), Code]));
end;
procedure QueueAsset(const Name, URL, Hash: String);
begin
  if Needed.IndexOf(Name) >= 0 then DownloadPage.Add(URL, Name, Hash);
end;
function PrepareToInstall(var NeedsRestart: Boolean): String;
var TempDir, StageDir, Python, Script, Args, ModuleExe: String;
    Code: Integer;
    Started: Boolean;
begin
  Result := '';
  TempDir := ExpandConstant('{tmp}');
  StageDir := TempDir + '\engine';
  Python := StageDir + '\python\python.exe';
  Script := '-I -B -X utf8 ' + Q(StageDir + '\setup_assets.py');
  Args := ' ' + Q(Engine) + ' ' + Q(ExpandConstant('{src}')) + ' ' + Q(ModelPage.Values[0]) + ' ' + Q(LogPath);
  try
    Progress.Show;
    try
      Progress.SetText(CustomMessage('Check'), '');
      Progress.Animate;
      ExtractTemporaryFile('bootstrap.zip');
      if DirExists(StageDir) and not DelTree(StageDir, True, True, True) then RaiseException('Cannot reset temporary engine directory');
      if not ForceDirectories(StageDir) then RaiseException('Cannot create staging directory');
      RunChecked(ExpandConstant('{sys}\tar.exe'), '-xf ' + Q(TempDir + '\bootstrap.zip') + ' -C ' + Q(StageDir), TempDir);
      DeleteFile(TempDir + '\reuse.ok');
      RunChecked(Python, Script + ' plan' + Args, StageDir);
      Reuse := FileExists(TempDir + '\reuse.ok');
    finally
      Progress.Hide;
    end;
    Needed.LoadFromFile(TempDir + '\need.txt');
    Log(Format('OBS assets: downloads=%d, complete engine reused=%d.', [Needed.Count, Ord(Reuse)]));
    if Needed.Count > 0 then begin
      DownloadPage.Clear;
#include DownloadsFile
      DownloadPage.Show;
      try
        DownloadPage.Download;
      finally
        DownloadPage.Hide;
      end;
    end;
    if not Reuse then begin
      Progress.Show;
      try
        Progress.SetText(CustomMessage('GPU'), '');
        Progress.Animate;
        RunChecked(Python, Script + ' stage' + Args, StageDir);
      finally
        Progress.Hide;
      end;
    end;
    ExtractTemporaryFile('obs-module-setup.exe');
    ModuleExe := TempDir + '\obs-module-setup.exe';
    Args := '/ALLUSERS /SP- /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG';
    if IsAdmin then Started := Exec(ModuleExe, Args, '', SW_HIDE, ewWaitUntilTerminated, Code)
    else Started := ShellExec('runas', ModuleExe, Args, '', SW_SHOWNORMAL, ewWaitUntilTerminated, Code);
    if not Started then RaiseException(SysErrorMessage(Code));
    if Code <> 0 then RaiseException(Format('OBS setup (%d)', [Code]));
  except
    Result := GetExceptionMessage + #13#10 + CustomMessage('Failed') + #13#10 + LogPath;
    Log(Result);
  end;
end;
