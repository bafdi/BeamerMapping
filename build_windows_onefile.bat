@echo off
REM Simple Windows Build Script - Creates single .exe file
REM This creates one large .exe file instead of a folder with dependencies
REM Use this for easier distribution (one file), but it will be larger and slower to start

echo ================================================
echo BeamerMapper Windows Build Script (Single File)
echo ================================================

REM Install dependencies
echo.
echo Step 1: Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

REM Clean previous builds
echo.
echo Step 2: Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist BeamerMapper.exe del /q BeamerMapper.exe

REM Build single .exe with PyInstaller
echo.
echo Step 3: Building single executable with PyInstaller...
echo This may take a few minutes...
pyinstaller --onefile --windowed --name BeamerMapper ^
  --add-data "presets;presets" ^
  --add-data "docs;docs" ^
  --hidden-import PyQt6.QtCore ^
  --hidden-import PyQt6.QtGui ^
  --hidden-import PyQt6.QtWidgets ^
  run_mapper.py

REM Check if build was successful
if not exist "dist\BeamerMapper.exe" (
    echo Error: Build failed - BeamerMapper.exe not found
    exit /b 1
)

echo.
echo ================================================
echo Build complete!
echo ================================================
echo Output file: dist\BeamerMapper.exe
echo.
echo This is a single executable file - just distribute this one file!
echo Note: It may be slower to start than the folder version.
echo.
pause
