; Inno Setup script for MeshCore Desktop.
; Per-user install (no administrator rights). The language picked on the first page
; becomes the application language: it is written to install.ini, which the app reads once on start.

#define AppName "MeshCore Desktop"
#define AppVersion "0.2.0"
#define AppExe "MeshCoreDesktop.exe"

[Setup]
AppId={{6B0B3C0E-6C5B-4F3E-9D56-3B7E3F1C9A21}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=qbarteczek
AppPublisherURL=https://github.com/qbarteczek/meshcore-desktop
DefaultDirName={localappdata}\Programs\MeshCoreDesktop
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ShowLanguageDialog=yes
UsePreviousLanguage=no
OutputDir=..\dist
OutputBaseFilename=MeshCoreDesktop-Setup-{#AppVersion}
SetupIconFile=..\mcd\app.ico
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "pl"; MessagesFile: "compiler:Languages\Polish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\MeshCoreDesktop\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[INI]
Filename: "{userappdata}\MeshCoreDesktop\install.ini"; Section: "install"; Key: "lang"; String: "{language}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
