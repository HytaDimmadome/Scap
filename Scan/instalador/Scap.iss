; Gera Scap-Setup.exe (instalador único). Compilado pelo GitHub Actions com Inno Setup.
[Setup]
AppName=Scap
AppVersion=1.0.0
AppPublisher=Essie N Pierot
DefaultDirName={autopf}\Scap
DefaultGroupName=Scap
PrivilegesRequired=lowest
OutputDir=..\saida
OutputBaseFilename=Scap-Setup
SetupIconFile=..\gui_assets\emblema.ico
UninstallDisplayIcon={app}\Scap.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
[Tasks]
Name: "desktop"; Description: "Criar atalho na área de trabalho"
[Files]
Source: "..\dist\Scap.exe"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\Scap"; Filename: "{app}\Scap.exe"
Name: "{autodesktop}\Scap"; Filename: "{app}\Scap.exe"; Tasks: desktop
[Run]
Filename: "{app}\Scap.exe"; Description: "Abrir o Scap"; Flags: nowait postinstall skipifsilent
