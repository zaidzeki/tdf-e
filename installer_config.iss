[Setup]
AppName=TDF-Encrypt
AppVersion=1.0
DefaultDirName={autopf}\TDF-Encrypt
DefaultGroupName=TDF-Encrypt
UninstallDisplayIcon={app}\app.exe
OutputDir=installer_output
OutputBaseFilename=TDF-Encrypt
Compression=lzma2/max
SolidCompression=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "build\app.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\TDF-Encrypt"; Filename: "{app}\app.exe"
Name: "{autodesktop}\TDF-Encrypt"; Filename: "{app}\app.exe"; Tasks: desktopicon

[Registry]
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\app.exe"; ValueType: string; ValueName: ""; ValueData: "{app}\app.exe"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\app.exe"; ValueType: string; ValueName: "Path"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Flags: preservestringtype
[Run]
Filename: "{app}\app.exe"; Description: "TDF-Encrypt"; Flags: nowait postinstall skipifsilent