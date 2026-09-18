[Setup]
AppId={{B4F070BE-D194-423F-86E3-09ACAE145C0A}
AppName=HamNavigator MY SHACK
AppVersion=1.8.0
DefaultDirName={localappdata}\Programs\HamNavigator MY SHACK
DefaultGroupName=HamNavigator MY SHACK
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..
OutputBaseFilename=HamNavigator-MY-SHACK-Setup-1.8.0
SetupIconFile=..\radioassistent.ico
UninstallDisplayIcon={app}\Radioassistent.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
InfoAfterFile=..\..\bygg\klient\LES-MEG.txt
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "norwegian"; MessagesFile: "compiler:Languages\Norwegian.isl"

[Files]
Source: "..\..\bygg\klient\*"; DestDir: "{app}"; Excludes: "release\HamNavigator\settings\*,*.obj,*.pyc,__pycache__\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\bygg\klient\release\HamNavigator\settings\*"; DestDir: "{app}\release\HamNavigator\settings"; Flags: onlyifdoesntexist uninsneveruninstall recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\release\HamNavigator\log"; Flags: uninsneveruninstall

[Tasks]
Name: "desktopicon"; Description: "Lag snarvei på skrivebordet"; Flags: checkedonce

[Icons]
Name: "{group}\HamNavigator MY SHACK"; Filename: "{app}\Radioassistent.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\HamNavigator MY SHACK"; Filename: "{app}\Radioassistent.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Radioassistent.exe"; Description: "Åpne HamNavigator MY SHACK"; Flags: nowait postinstall skipifsilent
