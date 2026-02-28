; Inno Setup Script for BeamerMapper Windows Installer
; This script creates a professional Windows installer
; 
; Requirements:
; 1. Install Inno Setup from https://jrsoftware.org/isdl.php
; 2. Build the application first using build_windows.bat
; 3. Open this file in Inno Setup and click "Compile"

[Setup]
; Basic application information
AppName=BeamerMapper
AppVersion=1.0.0
AppPublisher=BeamerMapper Team
AppPublisherURL=https://github.com/bafdi/BeamerMapping
AppSupportURL=https://github.com/bafdi/BeamerMapping/issues
AppUpdatesURL=https://github.com/bafdi/BeamerMapping/releases
DefaultDirName={autopf}\BeamerMapper
DefaultGroupName=BeamerMapper
AllowNoIcons=yes
LicenseFile=
InfoBeforeFile=
InfoAfterFile=
; Output configuration
OutputDir=Output
OutputBaseFilename=BeamerMapper-Setup
; Compression
Compression=lzma
SolidCompression=yes
; Windows version requirements
MinVersion=10.0
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; Appearance
WizardStyle=modern
; Uninstaller
UninstallDisplayIcon={app}\BeamerMapper.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Include all files from the dist\BeamerMapper directory
Source: "dist\BeamerMapper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\BeamerMapper"; Filename: "{app}\BeamerMapper.exe"
Name: "{group}\{cm:UninstallProgram,BeamerMapper}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\BeamerMapper"; Filename: "{app}\BeamerMapper.exe"; Tasks: desktopicon

[Run]
Name: "{app}\BeamerMapper.exe"; Description: "{cm:LaunchProgram,BeamerMapper}"; Flags: nowait postinstall skipifsilent
