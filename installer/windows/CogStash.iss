#define AppName "CogStash"
#define AppPublisher "CogStash"
#define AppURL "https://github.com/abdul219428/CogStash"
#define AppExeName "CogStash.exe"
#define CliExeName "CogStash-CLI.exe"

#ifndef AppVersion
  #error "AppVersion define is required."
#endif

#ifndef SourceDir
  #error "SourceDir define is required."
#endif

#ifndef VersionInfoVersion
  #define VersionInfoVersion AppVersion
#endif

#ifndef OutputDir
  #define OutputDir SourceDir
#endif

[Setup]
AppId={{A8B61FA0-C1C4-4C8A-8A2E-B9972DB78547}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
VersionInfoVersion={#VersionInfoVersion}
DefaultDirName={localappdata}\Programs\CogStash
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename=CogStash-v{#AppVersion}-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}
ChangesEnvironment=yes
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startup"; Description: "Launch CogStash when I sign in"; GroupDescription: "Additional tasks:"
Name: "addtopath"; Description: "Add CogStash CLI to PATH"; GroupDescription: "Additional tasks:"

[Files]
Source: "{#SourceDir}\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\{#CliExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "{#AppExeName},{#CliExeName}"

[Icons]
Name: "{group}\CogStash"; Filename: "{app}\CogStash.exe"
Name: "{autodesktop}\CogStash"; Filename: "{app}\CogStash.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CogStash.exe"; Description: "Launch CogStash"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{userstartup}\CogStash.bat"
Type: files; Name: "{app}\.cogstash-installed"

[Code]
const
  PathOwnershipKey = 'Software\CogStash\Installer';
  PathOwnershipValue = 'ManagedPath';

function StartupBatchContents(): String;
begin
  Result := '@echo off' + #13#10 + 'start "" "' + ExpandConstant('{app}\CogStash.exe') + '"' + #13#10;
end;

procedure AddAppToUserPath();
var
  OldPath, AppDir: String;
begin
  AppDir := ExpandConstant('{app}\bin');
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OldPath) then
    OldPath := '';
  if Pos(LowerCase(AppDir + ';'), LowerCase(OldPath + ';')) = 0 then
  begin
    if OldPath = '' then
      RegWriteExpandStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', AppDir)
    else
      RegWriteExpandStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OldPath + ';' + AppDir);
    RegWriteStringValue(HKEY_CURRENT_USER, PathOwnershipKey, PathOwnershipValue, AppDir);
  end;
end;

{ Returns PathStr with every exact (case-insensitive) semicolon-delimited
  segment equal to Segment removed.  All other segments are preserved unchanged. }
function RemoveExactPathSegment(const PathStr, Segment: String): String;
var
  Remaining, Part, NewPath, Sep: String;
  SemiPos: Integer;
  SegLower: String;
begin
  SegLower := LowerCase(Segment);
  Remaining := PathStr;
  NewPath := '';
  Sep := '';
  while True do
  begin
    SemiPos := Pos(';', Remaining);
    if SemiPos > 0 then
    begin
      Part := Copy(Remaining, 1, SemiPos - 1);
      Remaining := Copy(Remaining, SemiPos + 1, Length(Remaining));
    end
    else
    begin
      Part := Remaining;
      Remaining := '';
    end;
    if LowerCase(Part) <> SegLower then
    begin
      NewPath := NewPath + Sep + Part;
      Sep := ';';
    end;
    if SemiPos = 0 then
      Break;
  end;
  Result := NewPath;
end;

procedure RemoveInstallerOwnedPath();
var
  OwnedPath, CurrentPath, NewPath: String;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, PathOwnershipKey, PathOwnershipValue, OwnedPath) then
    Exit;
  if RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', CurrentPath) then
  begin
    NewPath := RemoveExactPathSegment(CurrentPath, OwnedPath);
    if NewPath <> CurrentPath then
      RegWriteExpandStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', NewPath);
  end;
  RegDeleteValue(HKEY_CURRENT_USER, PathOwnershipKey, PathOwnershipValue);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SaveStringToFile(ExpandConstant('{app}\.cogstash-installed'), 'installed', False);
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('startup') then
    SaveStringToFile(ExpandConstant('{userstartup}\CogStash.bat'), StartupBatchContents(), False);
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('addtopath') then
    AddAppToUserPath();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveInstallerOwnedPath();
end;
