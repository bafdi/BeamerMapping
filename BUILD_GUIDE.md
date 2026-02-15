# Build Anleitung für BeamerMapper

Dieses Dokument erklärt, wie Sie BeamerMapper für macOS (.dmg) und Windows (.exe) erstellen können.

## 📋 Inhaltsverzeichnis

- [Voraussetzungen](#voraussetzungen)
- [macOS .dmg erstellen](#macos-dmg-erstellen)
- [Windows .exe erstellen](#windows-exe-erstellen)
- [Erweiterte Optionen](#erweiterte-optionen)
- [Fehlerbehebung](#fehlerbehebung)

---

## Voraussetzungen

### Für beide Plattformen

- Python 3.8 oder höher installiert
- Git installiert (um das Repository zu klonen)

### Zusätzlich für macOS

- macOS Betriebssystem (für .dmg Erstellung)
- Homebrew installiert (für create-dmg Tool)
- Xcode Command Line Tools

### Zusätzlich für Windows

- Windows Betriebssystem (für .exe Erstellung)
- Microsoft Visual C++ 14.0 oder höher (wird normalerweise mit Visual Studio installiert)

---

## macOS .dmg erstellen

### Schritt 1: Repository klonen (falls noch nicht geschehen)

```bash
git clone https://github.com/bafdi/BeamerMapping.git
cd BeamerMapping
```

### Schritt 2: Virtuelle Umgebung erstellen (empfohlen)

```bash
python3 -m venv venv
source venv/bin/activate
```

### Schritt 3: Build-Skript ausführen

```bash
./build_macos.sh
```

Das Skript wird:
1. Alle benötigten Abhängigkeiten installieren (PyInstaller, etc.)
2. Vorherige Builds bereinigen
3. Die Anwendung mit PyInstaller erstellen
4. Eine .dmg Datei erstellen

### Schritt 4: Ergebnis

Nach erfolgreichem Build finden Sie:
- **BeamerMapper-macOS.dmg** - Die verteilbare Disk-Image-Datei

Die .dmg Datei kann an Benutzer verteilt werden, die sie öffnen und die App in ihren Applications-Ordner ziehen können.

### Manuelle .dmg Erstellung (Alternative)

Falls das Skript nicht funktioniert, können Sie auch manuell vorgehen:

```bash
# Dependencies installieren
pip install pyinstaller

# App erstellen
pyinstaller BeamerMapper.spec

# Einfache DMG erstellen (ohne create-dmg)
hdiutil create -volname "BeamerMapper" -srcfolder "dist/BeamerMapper.app" -ov -format UDZO "BeamerMapper-macOS.dmg"
```

---

## Windows .exe erstellen

### Schritt 1: Repository klonen (falls noch nicht geschehen)

```cmd
git clone https://github.com/bafdi/BeamerMapping.git
cd BeamerMapping
```

### Schritt 2: Virtuelle Umgebung erstellen (empfohlen)

```cmd
python -m venv venv
venv\Scripts\activate
```

### Schritt 3: Build-Skript ausführen

```cmd
build_windows.bat
```

Das Skript wird:
1. Alle benötigten Abhängigkeiten installieren (PyInstaller, etc.)
2. Vorherige Builds bereinigen
3. Die Anwendung mit PyInstaller erstellen

### Schritt 4: Ergebnis

Nach erfolgreichem Build finden Sie:
- **dist\BeamerMapper\** - Ordner mit der ausführbaren Datei und allen Abhängigkeiten
- **dist\BeamerMapper\BeamerMapper.exe** - Die Hauptanwendung

### Verteilungsmöglichkeiten

#### Option 1: Ordner-Distribution (Einfach)

Komprimieren Sie den gesamten `dist\BeamerMapper\` Ordner als ZIP-Datei:

```cmd
cd dist
powershell Compress-Archive -Path BeamerMapper -DestinationPath BeamerMapper-Windows.zip
```

Benutzer können dann:
1. Die ZIP-Datei entpacken
2. `BeamerMapper.exe` direkt ausführen

#### Option 2: Installer mit Inno Setup (Professionell)

Für einen professionellen Windows-Installer:

1. **Inno Setup herunterladen und installieren:**
   - Download von: https://jrsoftware.org/isdl.php
   - Installieren Sie Inno Setup auf Ihrem Windows-Computer

2. **Installer-Skript verwenden:**
   - Die Datei `installer_windows.iss` in Inno Setup öffnen
   - Auf "Compile" klicken
   - Der Installer wird im `Output\` Ordner erstellt

3. **Ergebnis:**
   - Eine `BeamerMapper-Setup.exe` Datei
   - Professioneller Windows-Installer mit Uninstaller

### Manuelle Windows .exe Erstellung (Alternative)

Falls das Batch-Skript nicht funktioniert:

```cmd
REM Dependencies installieren
pip install pyinstaller

REM App erstellen
pyinstaller BeamerMapper.spec
```

Für eine einzelne .exe Datei (alles in einer Datei, größer aber einfacher):

```cmd
pyinstaller --onefile --windowed --name BeamerMapper run_mapper.py
```

---

## Erweiterte Optionen

### App-Icon hinzufügen

1. **Für macOS:** Erstellen Sie eine `.icns` Datei und setzen Sie den Pfad in `BeamerMapper.spec`:
   ```python
   app = BUNDLE(
       ...
       icon='path/to/icon.icns',
       ...
   )
   ```

2. **Für Windows:** Erstellen Sie eine `.ico` Datei und setzen Sie den Pfad in `BeamerMapper.spec`:
   ```python
   exe = EXE(
       ...
       icon='path/to/icon.ico',
       ...
   )
   ```

### Code-Signierung (für Vertrauenswürdigkeit)

#### macOS Code Signing

```bash
codesign --force --sign "Developer ID Application: Ihr Name" dist/BeamerMapper.app
```

#### Windows Code Signing

Benötigt ein Code-Signing-Zertifikat:

```cmd
signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com dist\BeamerMapper\BeamerMapper.exe
```

### Optimierungen

#### Kleinere Executable-Größe

In `BeamerMapper.spec`:
- `upx=True` aktivieren (UPX compression)
- Nicht benötigte Module zu `excludes` hinzufügen

#### Schnellerer Start

- `noarchive=False` für schnelleren Import
- `onefile=False` für schnelleren Start (mehr Dateien)

---

## Fehlerbehebung

### macOS

**Problem:** "create-dmg: command not found"
```bash
brew install create-dmg
```

**Problem:** "xcrun: error: invalid active developer path"
```bash
xcode-select --install
```

**Problem:** App lässt sich nicht öffnen (Sicherheitswarnung)
- Systemeinstellungen → Sicherheit → App trotzdem öffnen
- Oder App signieren (siehe Code-Signierung)

### Windows

**Problem:** "error: Microsoft Visual C++ 14.0 is required"
- Installieren Sie Build Tools for Visual Studio
- Download: https://visualstudio.microsoft.com/downloads/

**Problem:** DLL-Fehler beim Start der .exe
- Stellen Sie sicher, dass alle Dateien im `dist\BeamerMapper\` Ordner mitgeliefert werden
- Oder verwenden Sie `--onefile` Option

**Problem:** Antivirus blockiert die .exe
- Fügen Sie eine Ausnahme für PyInstaller-generierte Dateien hinzu
- Signieren Sie die .exe mit einem Code-Signing-Zertifikat

**Problem:** "ImportError" beim Start
- Fehlende Module zu `hiddenimports` in `BeamerMapper.spec` hinzufügen

### Beide Plattformen

**Problem:** App startet nicht / Schwarzer Bildschirm
- Führen Sie die .exe/.app über Terminal/CMD aus, um Fehler zu sehen:
  - macOS: `./dist/BeamerMapper.app/Contents/MacOS/BeamerMapper`
  - Windows: `dist\BeamerMapper\BeamerMapper.exe`

**Problem:** Presets/Docs fehlen
- Prüfen Sie, ob `datas` in `BeamerMapper.spec` korrekt gesetzt ist
- Die Ordner müssen beim Build vorhanden sein

---

## Weitere Ressourcen

- **PyInstaller Dokumentation:** https://pyinstaller.org/
- **create-dmg (macOS):** https://github.com/create-dmg/create-dmg
- **Inno Setup (Windows):** https://jrsoftware.org/isinfo.php
- **Code Signing:**
  - macOS: https://developer.apple.com/support/code-signing/
  - Windows: https://docs.microsoft.com/windows/win32/seccrypto/cryptography-tools

---

## Support

Bei Problemen:
1. Prüfen Sie die Fehlermeldung im Terminal/CMD
2. Suchen Sie in der PyInstaller Dokumentation
3. Erstellen Sie ein Issue im GitHub Repository

---

**Hinweis:** Der erste Build kann länger dauern, da alle Dependencies heruntergeladen werden müssen. Nachfolgende Builds sind schneller.
