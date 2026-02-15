#!/usr/bin/env bash
set -euo pipefail

# Script to create a macOS DMG from the .app bundle
# Usage: ./create_dmg.sh [--app-path path/to/BeamerMapper.app]

APP_PATH="dist/BeamerMapper.app"
DMG_NAME="BeamerMapper.dmg"
VOLUME_NAME="BeamerMapper"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Parse arguments
for arg in "$@"; do
  case "$arg" in
    --app-path=*)
      APP_PATH="${arg#*=}"
      ;;
    --help)
      cat <<EOF
Usage: $0 [--app-path path/to/BeamerMapper.app]

Creates a DMG installer for BeamerMapper.

Options:
  --app-path=PATH    Path to the .app bundle (default: dist/BeamerMapper.app)
  --help             Show this help

This script requires macOS and the 'create-dmg' tool.
Install with: brew install create-dmg
EOF
      exit 0
      ;;
  esac
done

echo "Creating DMG for: $APP_PATH"

# Check if app exists
if [ ! -d "$APP_PATH" ]; then
  echo "Error: App bundle not found at $APP_PATH"
  echo "Please build the .app first using: ./package_mac.sh --py2app"
  exit 1
fi

# Check if we're on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
  echo "Error: This script must be run on macOS"
  exit 1
fi

# Check if create-dmg is installed
if ! command -v create-dmg &> /dev/null; then
  echo "Error: create-dmg is not installed"
  echo "Install with: brew install create-dmg"
  echo ""
  echo "Alternative: Using hdiutil (macOS built-in)"
  echo "Creating simple DMG with hdiutil..."
  
  # Create temporary directory for DMG contents
  TMP_DMG_DIR="$PROJECT_DIR/tmp_dmg"
  mkdir -p "$TMP_DMG_DIR"
  
  # Copy app to temporary directory
  cp -R "$APP_PATH" "$TMP_DMG_DIR/"
  
  # Create DMG
  hdiutil create -volname "$VOLUME_NAME" \
    -srcfolder "$TMP_DMG_DIR" \
    -ov -format UDZO \
    "$DMG_NAME"
  
  # Clean up
  rm -rf "$TMP_DMG_DIR"
  
  echo "DMG created: $DMG_NAME"
  exit 0
fi

# Use create-dmg for a nicer DMG with background and layout
create-dmg \
  --volname "$VOLUME_NAME" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 100 \
  --icon "BeamerMapper.app" 175 190 \
  --hide-extension "BeamerMapper.app" \
  --app-drop-link 425 190 \
  "$DMG_NAME" \
  "$APP_PATH"

echo "DMG created successfully: $DMG_NAME"
