; RuneFetch installer (Inno Setup 6).
;
; This is what makes auto-update safe. A running .exe cannot overwrite itself on
; Windows, and hand-rolled file swapping leaves a half-updated install if it
; fails midway. Inno closes the running app, replaces files transactionally, and
; relaunches — so core/updater.py only has to download this and run it.
;
; Built by .github/workflows/release.yml; MyAppVersion is passed in from the tag:
;   iscc /DMyAppVersion=2.1.0 packaging\RuneFetch.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName      "RuneFetch"
#define MyAppPublisher "DwarvenStack"
#define MyAppURL       "https://github.com/dwarvenstack/RuneFetch"
#define MyAppExeName   "RuneFetch.exe"

[Setup]
; AppId must never change between versions — it is how Windows recognises an
; upgrade rather than a second parallel install.
AppId={{8F3A6E52-1C4D-4B7A-9E23-6D5F8C1A0B94}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases

; Per-user install into LocalAppData: no UAC prompt, which matters because the
; updater runs the installer silently. An admin prompt there would either block
; the update or confuse the user.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist_installer
OutputBaseFilename=RuneFetch-Setup-{#MyAppVersion}
SetupIconFile=..\assets\runefetch_icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
; /TESTINSTALL=1 extracts a test installation without touching registration,
; shortcuts or running user apps. Normal installs keep the standard behavior.
Uninstallable=not IsTestInstall

; Let Restart Manager close a running RuneFetch instead of failing on locked
; files. Paired with /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS from the updater.
CloseApplications=yes
RestartApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\RuneFetch\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";              Filename: "{app}\{#MyAppExeName}"; Check: not IsTestInstall
Name: "{group}\Uninstall {#MyAppName}";    Filename: "{uninstallexe}"; Check: not IsTestInstall
Name: "{userdesktop}\{#MyAppName}";        Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Check: not IsTestInstall

[Run]
; runascurrentuser matters: without it the relaunched app could run at a
; different integrity level than the user's session.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; \
  Flags: nowait postinstall skipifsilent runascurrentuser; Check: not IsTestInstall

; After a silent (auto-)update, relaunch without asking — the user already
; consented in the app's update dialog.
Filename: "{app}\{#MyAppExeName}"; Flags: nowait runascurrentuser; Check: WasSilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function IsTestInstall: Boolean;
begin
  Result := ExpandConstant('{param:TESTINSTALL|0}') = '1';
end;

function WasSilent: Boolean;
begin
  Result := WizardSilent and not IsTestInstall;
end;
