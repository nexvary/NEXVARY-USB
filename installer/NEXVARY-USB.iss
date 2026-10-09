#define MyAppName "NEXVARY USB Studio"
#define MyAppVersion "0.5.1"
#define MyAppPublisher "NEXVARY"
#define MyAppExeName "NEXVARY-USB-Studio.exe"
[Setup]
SourceDir=..
AppId={{C7CE63D3-2B3C-4C64-9865-9B8092CC12CE}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\NEXVARY USB Studio
DefaultGroupName=NEXVARY USB Studio
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=assets\nexvary-usb.ico
OutputDir=installer-output
OutputBaseFilename=NEXVARY-USB-Studio-Setup-v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=no
DisableWelcomePage=no
CloseApplications=yes
InfoBeforeFile=installer\welcome.txt
WizardImageFile=assets\wizard-large.bmp
WizardSmallImageFile=assets\wizard-small.bmp
AppSupportURL=https://github.com/nexvary/NEXVARY-USB/issues
AppUpdatesURL=https://github.com/nexvary/NEXVARY-USB/releases
VersionInfoVersion=0.5.1.0
VersionInfoCompany=NEXVARY
VersionInfoDescription=NEXVARY USB modem and USIM management workstation
[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs
[Icons]
Name: "{autoprograms}\NEXVARY USB Studio"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\NEXVARY USB Studio"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Create Desktop shortcut"; GroupDescription: "Additional shortcuts:"
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch NEXVARY USB Studio"; Flags: nowait postinstall skipifsilent
