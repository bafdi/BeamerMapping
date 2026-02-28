#!/bin/bash
# Build script for macOS .dmg installer
# This script should be run on macOS

set -e

echo "================================================"
echo "BeamerMapper macOS Build Script"
echo "================================================"

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "Warning: This script is designed to run on macOS"
    echo "You may encounter issues on other platforms"
fi

# Install dependencies if not already installed
echo "Step 1: Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# Clean previous builds
echo ""
echo "Step 2: Cleaning previous builds..."
rm -rf build dist
rm -rf BeamerMapper.app
rm -rf *.dmg

# Build the application with PyInstaller
echo ""
echo "Step 3: Building application with PyInstaller..."
pyinstaller BeamerMapper.spec

# Check if build was successful
if [ ! -d "dist/BeamerMapper.app" ]; then
    echo "Error: Build failed - BeamerMapper.app not found"
    exit 1
fi

echo ""
echo "Step 4: Creating .dmg installer..."

# Install create-dmg if not already installed
if ! command -v create-dmg &> /dev/null; then
    echo "Installing create-dmg..."
    brew install create-dmg
fi

# Create DMG
create-dmg \
  --volname "BeamerMapper Installer" \
  --window-pos 200 120 \
  --window-size 800 400 \
  --icon-size 100 \
  --icon "BeamerMapper.app" 200 190 \
  --hide-extension "BeamerMapper.app" \
  --app-drop-link 600 185 \
  "BeamerMapper-macOS.dmg" \
  "dist/BeamerMapper.app" \
  2>/dev/null || \
  # Fallback to simple DMG creation if create-dmg fails
  hdiutil create -volname "BeamerMapper" -srcfolder "dist/BeamerMapper.app" -ov -format UDZO "BeamerMapper-macOS.dmg"

echo ""
echo "================================================"
echo "Build complete!"
echo "================================================"
echo "Output file: BeamerMapper-macOS.dmg"
echo ""
echo "You can now distribute this .dmg file."
echo "Users can drag BeamerMapper.app to their Applications folder."
