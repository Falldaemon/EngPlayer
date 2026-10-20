#define MyAppName "EngPlayer"
#define MyAppVersion "0.1.8"
#define MyAppLabel "0.1.8 Beta"
#define MyAppPublisher "Engin Eren"
#define MyAppURL "https://github.com/Falldaemon/EngPlayer"
#define MyAppExeName "EngPlayer.exe"

[Setup]
AppId={{CEEB7FC8-2C74-46D3-AD6D-BE3DF39EC299}
AppName={#MyAppName}
AppVersion={#MyAppLabel}
AppVerName={#MyAppName} {#MyAppLabel}
VersionInfoVersion={#MyAppVersion}.0
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppLabel}
OutputDir=Output
OutputBaseFilename=EngPlayer-{#MyAppVersion}-Beta-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=auto
CloseApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[CustomMessages]
english.DeleteUserData=Do you also want to delete EngPlayer's settings, profiles, favorites and cache?%n%nRecordings in your Videos folder are never deleted.
turkish.DeleteUserData=EngPlayer'ın ayarları, profilleri, favorileri ve önbelleği de silinsin mi?%n%nVideolar klasöründeki kayıtlarınız hiçbir durumda silinmez.
german.DeleteUserData=Sollen auch die Einstellungen, Profile, Favoriten und der Cache von EngPlayer gelöscht werden?%n%nAufnahmen in Ihrem Videos-Ordner werden niemals gelöscht.
french.DeleteUserData=Voulez-vous également supprimer les paramètres, profils, favoris et le cache d'EngPlayer ?%n%nLes enregistrements de votre dossier Vidéos ne sont jamais supprimés.
italian.DeleteUserData=Eliminare anche impostazioni, profili, preferiti e cache di EngPlayer?%n%nLe registrazioni nella cartella Video non vengono mai eliminate.
spanish.DeleteUserData=¿Desea eliminar también la configuración, los perfiles, los favoritos y la caché de EngPlayer?%n%nLas grabaciones de su carpeta Vídeos nunca se eliminan.
brazilianportuguese.DeleteUserData=Deseja também excluir as configurações, perfis, favoritos e o cache do EngPlayer?%n%nAs gravações na sua pasta Vídeos nunca são excluídas.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\EngPlayer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure StopEngPlayer;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM EngPlayerDaemon.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM EngPlayer.exe /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopEngPlayer;
  Result := '';
end;

function InitializeUninstall: Boolean;
begin
  StopEngPlayer;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
  begin
    if MsgBox(CustomMessage('DeleteUserData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(ExpandConstant('{userappdata}\EngPlayer'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\EngPlayer'), True, True, True);
    end;
  end;
end;
