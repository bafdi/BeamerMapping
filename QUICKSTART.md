# Quick Start Guide - BeamerMapper

## For End Users (Running Pre-built Executables)

### Windows

1. **Download**: Get `BeamerMapper-windows-exe.zip` from [GitHub Actions](https://github.com/bafdi/BeamerMapping/actions)
2. **Extract**: Unzip the file to any location (e.g., Desktop or Program Files)
3. **Run**: Double-click `BeamerMapper.exe`

**Note**: Windows Defender may show a warning for unsigned executables. Click "More info" → "Run anyway"

### macOS

1. **Download**: Get `BeamerMapper-macos-app.zip` from [GitHub Actions](https://github.com/bafdi/BeamerMapping/actions)
2. **Extract**: Unzip the file
3. **Install**: Drag `BeamerMapper.app` to your Applications folder
4. **Run**: Double-click the app in Applications

**First Run**: macOS may show "unidentified developer" warning. Right-click the app → "Open" → "Open" to bypass.

**For DMG installers** (when available):
1. Double-click `BeamerMapper.dmg`
2. Drag the app icon to the Applications folder
3. Eject the DMG
4. Run from Applications

---

## For Developers (Building from Source)

### Prerequisites
- Python 3.11 or higher
- pip (Python package manager)

### Setup

```bash
# Clone the repository
git clone https://github.com/bafdi/BeamerMapping.git
cd BeamerMapping

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Run from Source

```bash
python run_mapper.py
```

### Build Executables

**macOS - Build .app:**
```bash
./package_mac.sh --py2app
```

**macOS - Build .dmg installer:**
```bash
./package_mac.sh --py2app  # First build the .app
./create_dmg.sh            # Then create DMG
```

**Windows - Build .exe:**
```cmd
package_win.bat
```

See [PACKAGING.md](PACKAGING.md) for detailed build instructions and options.

---

## Getting Pre-built Executables

### From GitHub Actions

1. Go to https://github.com/bafdi/BeamerMapping/actions
2. Click on the most recent successful workflow run (green checkmark)
3. Scroll to "Artifacts" section at the bottom
4. Download:
   - `BeamerMapper-macos-app` for macOS
   - `BeamerMapper-windows-exe` for Windows

### From Releases (when available)

Pre-built executables will be available in the [Releases](https://github.com/bafdi/BeamerMapping/releases) section.

---

## Troubleshooting

### Windows

**Problem**: "Windows protected your PC" warning
- **Solution**: Click "More info" → "Run anyway"

**Problem**: Antivirus flags the .exe
- **Solution**: This is common for unsigned executables. Add an exception in your antivirus settings.

### macOS

**Problem**: "App can't be opened because it is from an unidentified developer"
- **Solution**: Right-click the app → "Open" → "Open"

**Problem**: "App is damaged and can't be opened"
- **Solution**: Run in Terminal: `xattr -cr /Applications/BeamerMapper.app`

**Problem**: App crashes on startup
- **Solution**: Check if you have required permissions for camera/screen recording (System Settings → Privacy & Security)

### Both Platforms

**Problem**: Application won't start
- **Solution**: 
  1. Make sure you have the latest version
  2. Check system requirements (see main README)
  3. Try running from source to see error messages

---

## Support

For issues, questions, or feature requests:
- Open an issue on [GitHub Issues](https://github.com/bafdi/BeamerMapping/issues)
- Check existing documentation in the repository

---

## System Requirements

- **Windows**: Windows 10 or later (64-bit)
- **macOS**: macOS 11 (Big Sur) or later
- **RAM**: 4GB minimum, 8GB recommended
- **Graphics**: OpenGL-compatible graphics card
- **Additional**: Webcam or screen capture capability for live sources
