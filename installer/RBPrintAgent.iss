#define MyAppName "RB Print Agent"
#define MyAppVersion "2.0.1"
#define MyAppPublisher "R B FRESH MART"
#define MyAppExeName "RB Print Agent.exe"
#define MyAppIcon "rb_fresh_mart.ico"

[Setup]
AppId={{B7E9C2A7-2F43-4D36-9F1B-0A5A4F8E2D91}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\RB Print Agent
DefaultGroupName={#MyAppName}
OutputDir=..\installer-output
OutputBaseFilename=RB-Print-Agent-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
SetupIconFile=..\rb_fresh_mart.ico
UninstallDisplayIcon={app}\{#MyAppIcon}
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\dist\RB Print Agent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\rb_fresh_mart.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\RB Print Agent Settings"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcon}"

[InstallDelete]
Type: files; Name: "{userstartup}\RB Print Agent.lnk"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "RB Print Agent"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Start RB Print Agent now"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM ""{#MyAppExeName}"" /F >NUL 2>&1"; Flags: runhidden

