@echo off
REM Build script for Windows .exe installer
REM This script should be run on Windows

echo ================================================
echo BeamerMapper Windows Build Script
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

REM Build the application with PyInstaller
echo.
echo Step 3: Building application with PyInstaller...
pyinstaller BeamerMapper.spec

REM Check if build was successful
if not exist "dist\BeamerMapper\BeamerMapper.exe" (
    echo Error: Build failed - BeamerMapper.exe not found
    exit /b 1
)

echo.
echo ================================================
echo Build complete!
echo ================================================
echo Output location: dist\BeamerMapper\
echo Main executable: dist\BeamerMapper\BeamerMapper.exe
echo.
echo You can now:
echo 1. Distribute the entire dist\BeamerMapper\ folder (contains all dependencies)
echo 2. OR create an installer using NSIS or Inno Setup (see BUILD_GUIDE.md)
echo.
pause
