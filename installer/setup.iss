; Virtual Xbox Mapper - Inno Setup 6 installer script.
; Build with installer\build_exe.bat (builds the app, then this installer).
; To compile by hand, build the app first, then:
;   ISCC.exe /DMyAppVersion=<version from src\app_info.py> installer\setup.iss

#define MyAppName "Virtual Xbox Mapper"
#ifndef MyAppVersion
  #define MyAppVersion "2.0.1"
#endif
#define MyAppPublisher "VirtualXboxMapper Project"
#define MyAppURL "https://github.com/gg49999/virtual-xbox-mapper"
#define MyAppExeName "VirtualXboxMapper.exe"
#define ViGEmSetup "ViGEmBus_1.22.0_x64_x86_arm64.exe"

; ---- Guard: never package a stale or missing build ----------------------------
; The installer takes the app from build\dist. If that folder holds an old
; build (for example the original 1.x app), the installer would silently ship
; the old UI - so refuse to compile unless the exe's version resource matches.
#define BuildDir AddBackslash(SourcePath) + "..\build\dist\VirtualXboxMapper"
#define BuildExe BuildDir + "\VirtualXboxMapper.exe"
#if !FileExists(BuildExe)
  #error The app has not been built: build\dist\VirtualXboxMapper\VirtualXboxMapper.exe is missing. Run installer\build_exe.bat first.
#endif
#define BuiltVersion GetVersionNumbersString(BuildExe)
#pragma message "Packaging VirtualXboxMapper.exe version " + BuiltVersion + " as installer version " + MyAppVersion
#if BuiltVersion != MyAppVersion + ".0"
  #error build\dist holds a VirtualXboxMapper.exe whose version does not match this installer (see the message above). It is an old build - rebuild the app with installer\build_exe.bat so the old UI is never shipped.
#endif

[Setup]
; Keep this exact value so new versions upgrade existing installs in place.
AppId={{6C6F9E2A-6B0E-4B7B-9B0B-3E4A6D5B7E10}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\VirtualXboxMapper
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=..\build\installer_output
OutputBaseFilename=VirtualXboxMapper-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Admin rights are needed to install the ViGEmBus driver.
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "vigembus"; Description: "Install the ViGEmBus virtual controller driver (required)"; GroupDescription: "Driver:"; Check: NeedsViGEmBus
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startupicon"; Description: "Start {#MyAppName} when I sign in to Windows"; GroupDescription: "Startup:"; Flags: unchecked

[InstallDelete]
; Remove everything the previous version installed before copying the new
; build, so no stale runtime files or old UI modules survive an upgrade.
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\{#MyAppExeName}"
Type: filesandordirs; Name: "{app}\config"
Type: filesandordirs; Name: "{app}\profiles"
; 1.x created a Start-menu folder; 2.x uses a single shortcut.
Type: filesandordirs; Name: "{group}"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ViGEmSetup}"; DestDir: "{tmp}"; Flags: deleteafterinstall skipifsourcedoesntexist; Tasks: vigembus

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "VirtualXboxMapper"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; \
    Tasks: startupicon; Flags: uninsdeletevalue
; Also remove a Run entry the app itself created (Settings > Start with Windows).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; \
    ValueName: "VirtualXboxMapper"; Flags: uninsdeletevalue

[Run]
; Interactive driver setup for normal installs, silent for /SILENT installs.
Filename: "{tmp}\{#ViGEmSetup}"; StatusMsg: "Installing the ViGEmBus driver..."; \
    Flags: waituntilterminated skipifdoesntexist; Tasks: vigembus; Check: not WizardSilent
Filename: "{tmp}\{#ViGEmSetup}"; Parameters: "/exenoui /qn /norestart"; StatusMsg: "Installing the ViGEmBus driver..."; \
    Flags: waituntilterminated skipifdoesntexist; Tasks: vigembus; Check: WizardSilent
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Close a running instance so its files can be removed.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillApp"

[Code]
function ViGEmBusInstalled: Boolean;
begin
  Result := RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\ViGEmBus');
end;

function NeedsViGEmBus: Boolean;
begin
  Result := not ViGEmBusInstalled;
end;

// ViGEmBus is intentionally left installed on uninstall: other apps may use it.
// Remove it from Settings > Apps if you no longer need it.
