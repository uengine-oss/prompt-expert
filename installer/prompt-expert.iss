; Inno Setup 6 script for prompt-expert. Build with installer\build_installer.ps1
; (it passes /DAppVersion and expects dist\prompt-expert from build.ps1).

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppName "prompt-expert"
#define AppExe "prompt-expert.exe"

[Setup]
AppId={{4B0E1C23-E482-4A2D-B9EC-5506165177F9}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=uEngine
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install: no admin prompt, and the keyboard hook runs at the user's own integrity level.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=prompt-expert-Setup-{#AppVersion}
SetupIconFile=winwhisper.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
korean.Overlay=녹음 중 화면에 애니메이션 표시 (MacWhisper처럼 파형이 움직이는 작은 창)
korean.CopyPath=탐색기 우클릭 메뉴에 Copy Path / Recent Paths / Open Paths 추가
korean.Autostart=Windows 시작 시 자동 실행
korean.SmallModel=항상 가벼운 모델 사용 (small, 기본은 GPU: large-v3-turbo / CPU: small)
korean.Options=추가 옵션:
korean.LaunchNow=prompt-expert 실행
english.Overlay=Show a recording animation on screen (live waveform pill, like MacWhisper)
english.CopyPath=Add Copy Path / Recent Paths / Open Paths to the Explorer right-click menu
english.Autostart=Start prompt-expert when Windows starts
english.SmallModel=Always use small (default: large-v3-turbo on GPU / small on CPU)
english.Options=Options:
english.LaunchNow=Launch prompt-expert

[Tasks]
Name: "overlay"; Description: "{cm:Overlay}"; GroupDescription: "{cm:Options}"
Name: "copypath"; Description: "{cm:CopyPath}"; GroupDescription: "{cm:Options}"
Name: "autostart"; Description: "{cm:Autostart}"; GroupDescription: "{cm:Options}"
Name: "smallmodel"; Description: "{cm:SmallModel}"; GroupDescription: "{cm:Options}"; Flags: unchecked
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\prompt-expert\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Same value the tray menu's "Windows 시작 시 실행" toggles.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "prompt-expert"; ValueData: """{app}\{#AppExe}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
; The app writes these into its own config.json (other keys are left alone).
Filename: "{app}\{#AppExe}"; Parameters: "--set overlay=true"; Tasks: overlay; Flags: runhidden waituntilterminated
Filename: "{app}\{#AppExe}"; Parameters: "--set overlay=false"; Tasks: not overlay; Flags: runhidden waituntilterminated
Filename: "{app}\{#AppExe}"; Parameters: "--set model=small"; Tasks: smallmodel; Flags: runhidden waituntilterminated
; Explorer menu commands point at {app}, so they are (re)written on every install.
Filename: "{app}\{#AppExe}"; Parameters: "--install-shell-menu"; Tasks: copypath; Flags: runhidden waituntilterminated
Filename: "{app}\{#AppExe}"; Parameters: "--uninstall-shell-menu"; Tasks: not copypath; Flags: runhidden waituntilterminated
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchNow}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#AppExe}"; Parameters: "--uninstall-shell-menu"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveShellMenu"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure StopApp();
var
  ResultCode, I: Integer;
begin
  // A running copy keeps its DLLs locked, which breaks upgrades and leaves files behind on uninstall.
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  for I := 1 to 20 do
  begin
    Exec(ExpandConstant('{sys}\cmd.exe'), '/c tasklist /FI "IMAGENAME eq {#AppExe}" | find /I "{#AppExe}"',
         '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if ResultCode <> 0 then
      Break;
    Sleep(250);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopApp();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopApp();
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // The tray menu's toggle may have added this even if the install task was not chosen.
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'prompt-expert');
end;
