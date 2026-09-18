[Setup]
AppId={{B4F070BE-D194-423F-86E3-09ACAE145C0A}
AppName=HamNavigator MY SHACK
#define ClientVersion Trim(FileRead(FileOpen("..\klient\VERSION")))
AppVersion={#ClientVersion}
AppPublisher=LB7YK RadioLab
AppPublisherURL=https://lb7yk.no
VersionInfoDescription=HamNavigator MY SHACK installasjon
DefaultDirName={localappdata}\Programs\HamNavigator MY SHACK
DefaultGroupName=HamNavigator MY SHACK
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..
OutputBaseFilename=HamNavigator-MY-SHACK-Setup-{#ClientVersion}
SetupIconFile=hamnavigator.ico
UninstallDisplayIcon={app}\Radioassistent.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
InfoAfterFile=..\..\bygg\klient\LES-MEG.txt
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "swedish"; MessagesFile: "compiler:Languages\Swedish.isl"; InfoAfterFile: "installer-sv.txt"
Name: "english"; MessagesFile: "compiler:Default.isl"; InfoAfterFile: "installer-en.txt"
Name: "norwegian"; MessagesFile: "compiler:Languages\Norwegian.isl"

[Files]
Source: "prepare_update.py"; Flags: dontcopy
Source: "..\..\bygg\klient\*"; DestDir: "{app}"; Excludes: "release\HamNavigator\settings\*,*.obj,*.pyc,__pycache__\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\bygg\klient\release\HamNavigator\settings\*"; DestDir: "{app}\release\HamNavigator\settings"; Excludes: "resources\url_help\en\help_en.html,resources\url_help\ru\help_ru.html"; Flags: onlyifdoesntexist uninsneveruninstall recursesubdirs createallsubdirs
Source: "..\..\bygg\klient\release\HamNavigator\settings\resources\url_help\en\help_en.html"; DestDir: "{app}\release\HamNavigator\settings\resources\url_help\en"; Flags: ignoreversion
Source: "..\..\bygg\klient\release\HamNavigator\settings\resources\url_help\ru\help_ru.html"; DestDir: "{app}\release\HamNavigator\settings\resources\url_help\ru"; Flags: ignoreversion

[Dirs]
Name: "{app}\release\HamNavigator\log"; Flags: uninsneveruninstall

[CustomMessages]
swedish.DesktopShortcut=Skapa en genväg på skrivbordet
swedish.OpenHamNavigator=Öppna HamNavigator MY SHACK
english.DesktopShortcut=Create a desktop shortcut
norwegian.DesktopShortcut=Lag snarvei på skrivebordet
english.OpenHamNavigator=Open HamNavigator MY SHACK
norwegian.OpenHamNavigator=Åpne HamNavigator MY SHACK

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; Flags: checkedonce

[Icons]
Name: "{group}\HamNavigator MY SHACK"; Filename: "{app}\Radioassistent.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\HamNavigator MY SHACK"; Filename: "{app}\Radioassistent.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\radio_assistant.py"" --no-resume"; WorkingDir: "{app}"; Description: "{cm:OpenHamNavigator}"; Flags: nowait postinstall skipifsilent

#include "prepare-update.iss"
