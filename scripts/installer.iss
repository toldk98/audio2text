; Audio2Text — Inno Setup installer
; Requires Inno Setup 6+
; Run from project root: iscc scripts\installer.iss /dVERSION=v0.3.x

#define MyAppName "Audio2Text"
#define MyAppNameShort "audio2text"
#define MyAppPublisher "toldk98"
#define MyAppURL "https://github.com/toldk98/audio2text"
#define MyAppExeName "audio2text.bat"

#ifndef VERSION
  #define VERSION "v0.3.x"
#endif

[Setup]
AppId={{B3A7F2E1-8D5C-4A9E-9F1A-2E6C8D0F3A7B}
AppName={#MyAppName}
AppVersion={#VERSION}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppNameShort}
DefaultGroupName={#MyAppName}
OutputDir=..
OutputBaseFilename=Audio2Text-Setup-{#VERSION}-windows-x86_64
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
DisableDirPage=no
DisableProgramGroupPage=yes
CloseApplications=no
MinVersion=10.0
UninstallDisplayName={#MyAppName} {#VERSION}

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "uk"; MessagesFile: "compiler:Languages\Ukrainian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\*.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\gui\*"; DestDir: "{app}\gui"; Flags: ignoreversion recursesubdirs
Source: "..\dist\*.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\*.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\audio2text-env.tar.gz"; DestDir: "{app}"; Flags: nocompression ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Comment: "{cm:AppComment}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon; Comment: "{cm:AppComment}"

[Run]
Filename: "{tmp}\unpack_env.bat"; Parameters: """{app}"" ""{#VERSION}"""; Flags: hidewizard; StatusMsg: "{cm:ExtractingEnv}"
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram}"; Flags: postinstall nowait skipifsilent unchecked

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{app}\audio2text-env"""; Flags: runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  UnpackBatch: string;

procedure CreateUnpackBatch;
begin
  UnpackBatch := ExpandConstant('{tmp}\unpack_env.bat');
  SaveStringToFile(UnpackBatch,
    '@echo off' + #13#10 +
    'set DIR=%~1' + #13#10 +
    'set VERSION=%~2' + #13#10 +
    'set ENV_DIR=%DIR%\audio2text-env' + #13#10 +
    'set VERSION_FILE=%ENV_DIR%\.version' + #13#10 +
    'if exist "%VERSION_FILE%" (' + #13#10 +
    '  findstr /x "%VERSION%" "%VERSION_FILE%" >nul 2>nul' + #13#10 +
    '  if not errorlevel 1 exit /b 0' + #13#10 +
    ')' + #13#10 +
    'if exist "%ENV_DIR%" (' + #13#10 +
    '  attrib -R "%ENV_DIR%" /s /d 2>nul' + #13#10 +
    '  rmdir /s /q "%ENV_DIR%"' + #13#10 +
    ')' + #13#10 +
    'mkdir "%ENV_DIR%"' + #13#10 +
    'echo Rozpakuvannia seredovyshcha...' + #13#10 +
    'tar -xzf "%DIR%\audio2text-env.tar.gz" -C "%ENV_DIR%"' + #13#10 +
    'if errorlevel 1 (' + #13#10 +
    '  echo [ERROR] Extraction failed' + #13#10 +
    '  pause' + #13#10 +
    '  exit /b 1' + #13#10 +
    ')' + #13#10 +
    'echo %VERSION%>"%VERSION_FILE%"' + #13#10 +
    'exit /b 0' + #13#10,
    False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    CreateUnpackBatch;
  end;
end;

[CustomMessages]
en.AppComment=Transcribe audio to text with WhisperX
uk.AppComment=Транскрипція аудіо в текст (WhisperX)
en.AdditionalIcons=Additional shortcuts:
uk.AdditionalIcons=Додаткові ярлики:
en.DesktopIcon=Create a desktop shortcut
uk.DesktopIcon=Створити ярлик на робочому столі
en.ExtractingEnv=Extracting environment (may take a few minutes)...
uk.ExtractingEnv=Розпакування середовища (може зайняти кілька хвилин)...
en.LaunchProgram=Launch Audio2Text
uk.LaunchProgram=Запустити Audio2Text
