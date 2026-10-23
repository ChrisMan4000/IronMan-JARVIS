; Inno Setup recipe (https://jrsoftware.org/isinfo.php) for the optional Windows installer.
; Build: download the repo ZIP, unzip it, open this file in Inno Setup, press Compile.
; It packs the repo (not .git, not this folder) and then runs install-jarvis.ps1 in a normal PowerShell window.
; The installer is NOT code-signed, so Windows SmartScreen will warn about it ("More info" > "Run anyway").
[Setup]
AppName=IronMan J.A.R.V.I.S.
AppVersion=1.0
AppPublisher=ChrisMan4000
DefaultDirName={localappdata}\IronMan-JARVIS
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=.
OutputBaseFilename=IronMan-JARVIS-Installer
Compression=lzma2
SolidCompression=yes

[Files]
Source: "..\*"; DestDir: "{app}"; Excludes: "installer\*,.git\*"; Flags: recursesubdirs createallsubdirs

[Run]
Filename: "powershell.exe"; Parameters: "-NoExit -ExecutionPolicy Bypass -File ""{app}\install-jarvis.ps1"""; Description: "Run the Jarvis setup now (asks before every optional part)"; Flags: postinstall nowait runasoriginaluser
