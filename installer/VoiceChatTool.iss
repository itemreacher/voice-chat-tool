; Inno Setup script. Build with build_installer.bat (passes AppVersion and optionally GPU=1).
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef DistDir
  #define DistDir "..\dist"
#endif
#define AppName "Voice Chat Tool"
#define ExeName "VoiceChatTool.exe"
#ifdef GPU
  #define Flavor "GPU"
#else
  #define Flavor "CPU"
#endif

[Setup]
; Never change AppId: it lets a newer Setup update an existing installation in place.
AppId={{6F0B8F4E-3D1A-4C57-9B7E-5A1C2E9D4F10}
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
PrivilegesRequiredOverridesAllowed=dialog
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
Source: "{#DistDir}\VoiceChatTool\*"; DestDir: "{app}"; Excludes: "config.toml,_internal\nvidia\*"; Flags: recursesubdirs ignoreversion
#endif

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#ExeName}"
Name: "{group}\{#AppName} deinstallieren"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeName}"; Description: "{#AppName} starten"; Flags: nowait postinstall skipifsilent
; Silent update started by the program itself (/RELAUNCH=1): start the new version again.
Filename: "{app}\{#ExeName}"; Flags: nowait; Check: RelaunchRequested

[Code]
function RelaunchRequested: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

[UninstallDelete]
; Old GPU libraries must not linger after switching from the GPU to the CPU edition.
Type: filesandordirs; Name: "{app}\_internal\nvidia"
