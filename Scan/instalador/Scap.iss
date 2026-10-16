; Gera Scap-Setup.exe (instalador único). Compilado pelo GitHub Actions com Inno Setup.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
[Setup]
AppId={{6B1D2E54-5C41-4A7B-9F0E-5C4A21E0A9D1}
AppName=Scap
AppVersion={#AppVersion}
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
Filename: "{app}\Scap.exe"; Flags: nowait; Check: WizardSilent
