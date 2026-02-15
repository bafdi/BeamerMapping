@echo off
REM Einfaches Packaging-Skript für Windows (PyInstaller)
REM Unterstützte Flags:
REM   --onedir     Erzeuge OneDir (statt OneFile)
REM   --no-clean   Überspringe --clean bei PyInstaller
REM   --console    Öffne mit Konsole (zeige stderr/stdout)
REM   --help       Zeige diese Hilfe

SETLOCAL ENABLEDELAYEDEXPANSION

SET PROJECT_DIR=%~dp0
SET VENV_DIR=%PROJECT_DIR%.venv_pack
SET DIST_DIR=%PROJECT_DIR%dist

SET ONEDIR=0
SET NO_CLEAN=0
SET FORCE_CONSOLE=0

REM Parse arguments
FOR %%A IN (%*) DO (
  IF "%%A"=="--onedir" SET ONEDIR=1
  IF "%%A"=="--no-clean" SET NO_CLEAN=1
  IF "%%A"=="--console" SET FORCE_CONSOLE=1
  IF "%%A"=="--help" (
    echo Usage: %0 [--onedir] [--no-clean] [--console] [--help]
    echo.
    echo   --onedir     Create a OneDir PyInstaller build (no --onefile)
    echo   --no-clean   Don't pass --clean to PyInstaller (faster incremental)
    echo   --console    Keep console (don't add --noconsole)
    echo   --help       Show this help
    exit /b 0
  )
)

echo Projekt: %PROJECT_DIR%
echo Starte PyInstaller-Build (Standard: onefile)

REM 1) Virtuelle Umgebung erstellen
IF NOT EXIST "%VENV_DIR%" (
  echo Erstelle virtuelle Umgebung...
  python -m venv "%VENV_DIR%"
)

REM 2) Abhängigkeiten installieren
echo Aktiviere venv und installiere Dependencies...
call "%VENV_DIR%\Scripts\activate.bat"

pip install --upgrade pip setuptools wheel
IF EXIST "%PROJECT_DIR%requirements.txt" (
  pip install -r "%PROJECT_DIR%requirements.txt"
)
pip install pyinstaller pyinstaller-hooks-contrib

REM 3) Build-Ordner
IF NOT EXIST "%DIST_DIR%" mkdir "%DIST_DIR%"

REM 4) Baue mit PyInstaller
set "PYINSTALLER_CMD=pyinstaller --noconfirm --name BeamerMapper"

REM default: add --clean unless NO_CLEAN
if %NO_CLEAN% equ 0 (
  set "PYINSTALLER_CMD=!PYINSTALLER_CMD! --clean"
)

REM default: onefile unless ONEDIR set
if %ONEDIR% equ 0 (
  set "PYINSTALLER_CMD=!PYINSTALLER_CMD! --onefile"
)

REM GUI-App: keine Konsole (unless FORCE_CONSOLE)
if %FORCE_CONSOLE% equ 0 (
  set "PYINSTALLER_CMD=!PYINSTALLER_CMD! --noconsole"
)

REM Füge standardmäßig Presets und build-Ordner ein (falls vorhanden)
IF EXIST "%PROJECT_DIR%presets" (
  set "PYINSTALLER_CMD=!PYINSTALLER_CMD! --add-data "%PROJECT_DIR%presets;presets""
)
IF EXIST "%PROJECT_DIR%build" (
  set "PYINSTALLER_CMD=!PYINSTALLER_CMD! --add-data "%PROJECT_DIR%build;build""
)

REM Hidden imports für PyQt6
set "PYINSTALLER_CMD=!PYINSTALLER_CMD! --hidden-import=PyQt6.sip --hidden-import=PyQt6.QtSvg"

REM Icon (falls vorhanden)
IF EXIST "%PROJECT_DIR%icon.ico" (
  set "PYINSTALLER_CMD=!PYINSTALLER_CMD! --icon "%PROJECT_DIR%icon.ico""
)

REM Einstiegspunkt
set "PYINSTALLER_CMD=!PYINSTALLER_CMD! "%PROJECT_DIR%run_mapper.py""

echo PyInstaller-Aufruf: !PYINSTALLER_CMD!
!PYINSTALLER_CMD!

echo Fertig. Artefakt(en) liegen in: %DIST_DIR%
ENDLOCAL

