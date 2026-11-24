; Inno Setup script. Build with build_installer.bat (passes AppVersion and optionally GPU=1).
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef DistDir
  #define DistDir "..\dist"
#endif
; Tests build installers with their own id (/DTestAppId="{{...}"), so a test installation can never touch the
; registration of a real one. The real id must never change: it is how a newer Setup finds the old installation.
#ifdef TestAppId
  #define AppIdValue TestAppId
#else
  #define AppIdValue "{{6F0B8F4E-3D1A-4C57-9B7E-5A1C2E9D4F10}"
#endif
#define AppName "Voice Chat Tool"
#define ExeName "VoiceChatTool.exe"
#ifdef GPU
  #define Flavor "GPU"
#else
  #define Flavor "CPU"
#endif

[Setup]
; Never change the real AppId: it lets a newer Setup update an existing installation in place.
AppId={#AppIdValue}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Voice Chat Tool
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#ExeName}
SetupIconFile=..\assets\icon.ico
OutputDir=Output
OutputBaseFilename=VoiceChatTool-Setup-{#AppVersion}-{#Flavor}
Compression=lzma2/normal
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Per-user install by default (no admin needed); the user may choose "for all users".
PrivilegesRequired=lowest
; 'commandline' (not 'dialog'): a dialog asking 'for me / for all users' would also appear in a
; silent update and block it forever. Per-user is the default, /ALLUSERS selects all users.
PrivilegesRequiredOverridesAllowed=commandline
CloseApplications=yes
RestartApplications=no
WizardStyle=modern
VersionInfoVersion={#AppVersion}

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; config.toml is NOT shipped: settings live in %APPDATA%\VoiceChatTool and survive updates.
#ifdef GPU
Source: "{#DistDir}\VoiceChatTool\*"; DestDir: "{app}"; Excludes: "config.toml"; Flags: recursesubdirs ignoreversion
#else
Source: "{#DistDir}\VoiceChatTool\*"; DestDir: "{app}"; Excludes: "config.toml,_internal\nvidia\*,licenses\nvidia\*"; Flags: recursesubdirs ignoreversion
#endif

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#ExeName}"
Name: "{group}\{#AppName} deinstallieren"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeName}"; Description: "{#AppName} starten"; Flags: nowait postinstall skipifsilent
; Silent update started by the program itself (/RELAUNCH=1): start the new version again.
Filename: "{app}\{#ExeName}"; Flags: nowait; Check: RelaunchRequested

[InstallDelete]
; The program folder is replaced as a whole. Setup only overwrites files; it never removes files that a newer
; version no longer has, which left stale libraries of older versions behind (old PyAV/CTranslate2 files ...).
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\licenses"

[Code]
function RelaunchRequested: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

function UninstallKey: String;
begin
  Result := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1');
end;

{ Uninstaller of an installation of this program made in the OTHER mode (for all users <-> only for this user),
  or '' if there is none. Without this, an update that switches the mode leaves the old version behind. }
function OtherModeUninstaller: String;
var
  Value: String;
begin
  Result := '';
  if IsAdminInstallMode then
  begin
    if RegQueryStringValue(HKCU, UninstallKey, 'UninstallString', Value) then
      Result := RemoveQuotes(Value);
  end
  else
  begin
    if RegQueryStringValue(HKLM64, UninstallKey, 'UninstallString', Value) then
      Result := RemoveQuotes(Value);
  end;
  if (Result <> '') and (not FileExists(Result)) then
    Result := '';
end;

procedure RemoveOtherModeInstall;
var
  Uninstaller: String;
  ResultCode: Integer;
  Started: Boolean;
begin
  Uninstaller := OtherModeUninstaller;
  if Uninstaller = '' then
    Exit;
  Log('Removing the existing installation of the other mode: ' + Uninstaller);
  if IsAdminInstallMode then
    Started := Exec(Uninstaller, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
  else
    { an installation for all users can only be removed with administrator rights: Windows asks for permission }
    Started := ShellExec('runas', Uninstaller, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if (not Started) or (ResultCode <> 0) then
  begin
    Log('The other installation could not be removed (started=' + IntToStr(Ord(Started)) + ', code=' + IntToStr(ResultCode) + ').');
    if not WizardSilent then
      MsgBox('Eine ältere Installation von Voice Chat Tool konnte nicht entfernt werden. Entferne sie bitte selbst ' +
             'unter Windows-Einstellungen > Apps, damit nicht zwei Versionen auf dem PC liegen.', mbInformation, MB_OK);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    RemoveOtherModeInstall;
end;

[UninstallDelete]
; Old GPU libraries must not linger after switching from the GPU to the CPU edition.
Type: filesandordirs; Name: "{app}\_internal\nvidia"
