# Build Scripts Übersicht

Diese Datei gibt einen schnellen Überblick über alle verfügbaren Build-Optionen.

## 🚀 Schnellstart

### Windows
```cmd
build_windows.bat              # Empfohlen: Erstellt Ordner mit .exe
build_windows_onefile.bat      # Erstellt einzelne .exe Datei
```

### macOS
```bash
./build_macos.sh               # Erstellt .dmg Installer
```

## 📁 Verfügbare Dateien

### Build-Skripte
| Datei | Platform | Beschreibung |
|-------|----------|--------------|
| `build_macos.sh` | macOS | Erstellt .app und .dmg für macOS |
| `build_windows.bat` | Windows | Erstellt .exe mit Dependencies in Ordner |
| `build_windows_onefile.bat` | Windows | Erstellt einzelne .exe Datei (größer) |

### Konfiguration
| Datei | Beschreibung |
|-------|--------------|
| `BeamerMapper.spec` | PyInstaller Konfiguration (beide Plattformen) |
| `installer_windows.iss` | Inno Setup Skript für Windows-Installer |
| `requirements-build.txt` | Build-Dependencies |

### Dokumentation
| Datei | Beschreibung |
|-------|--------------|
| `BUILD_GUIDE.md` | Vollständige Build-Anleitung (Deutsch) |
| `WINDOWS_BUILD.md` | Schnellstart für Windows-Benutzer |
| `validate_build_env.py` | Überprüft Build-Umgebung |

## 🎯 Welches Build-Skript soll ich verwenden?

### Für Windows

**Option 1: `build_windows.bat` (Empfohlen)**
- ✅ Schnellerer Start der App
- ✅ Kleinere Dateigröße
- ⚠️ Muss als Ordner verteilt werden (viele Dateien)
- 💡 Am besten mit ZIP oder Inno Setup Installer

**Option 2: `build_windows_onefile.bat`**
- ✅ Nur eine Datei zum Verteilen
- ✅ Einfacher für Benutzer
- ⚠️ Größere Datei (~150-200 MB)
- ⚠️ Langsamerer Start (Dateien müssen extrahiert werden)

**Option 3: Inno Setup Installer**
- ✅ Professionellster Ansatz
- ✅ Installer/Uninstaller
- ✅ Desktop-Icon, Startmenü-Eintrag
- ⚠️ Erfordert zuerst `build_windows.bat`, dann Inno Setup

### Für macOS

**`build_macos.sh`**
- Erstellt standard macOS .dmg Installer
- Benutzer können die App in Applications ziehen
- Muss auf macOS ausgeführt werden

## 📦 Ergebnisse

Nach dem Build finden Sie:

### Windows (Ordner-Version)
```
dist/
  BeamerMapper/
    BeamerMapper.exe      ← Hauptdatei
    + viele DLL und Dependency-Dateien
```

### Windows (Einzeldatei)
```
dist/
  BeamerMapper.exe        ← Eine Datei, ca. 150-200 MB
```

### Windows (Inno Setup)
```
Output/
  BeamerMapper-Setup.exe  ← Professioneller Installer
```

### macOS
```
BeamerMapper-macOS.dmg    ← Verteilen Sie diese Datei
dist/
  BeamerMapper.app/       ← Oder diese App direkt
```

## 🔍 Umgebung überprüfen

Vor dem Build können Sie überprüfen, ob alles korrekt installiert ist:

```bash
python validate_build_env.py
```

Dieses Skript prüft:
- ✓ Python-Version
- ✓ Pip verfügbar
- ✓ Runtime-Dependencies
- ✓ Build-Dependencies
- ✓ Erforderliche Ordner
- ✓ Platform-spezifische Tools

## 💡 Tipps

### Schneller iterieren
- Beim Testen: Nutzen Sie `python run_mapper.py` (kein Build nötig)
- Nur für Distribution: Erstellen Sie .exe/.dmg

### Kleinere Dateien
- Bearbeiten Sie `BeamerMapper.spec`
- Fügen Sie ungenutzte Module zu `excludes` hinzu
- Nutzen Sie `upx=True` für Kompression

### Icon hinzufügen
1. Erstellen Sie `.ico` (Windows) oder `.icns` (macOS)
2. Setzen Sie `icon='pfad/zu/icon'` in `BeamerMapper.spec`

### Code signieren
- **macOS:** `codesign --sign "Developer ID" BeamerMapper.app`
- **Windows:** Benötigt Code-Signing-Zertifikat

## 📚 Weitere Hilfe

- Vollständige Anleitung: [BUILD_GUIDE.md](BUILD_GUIDE.md)
- Windows-Quickstart: [WINDOWS_BUILD.md](WINDOWS_BUILD.md)
- Bei Problemen: https://github.com/bafdi/BeamerMapping/issues

## 🐛 Häufige Probleme

| Problem | Lösung |
|---------|--------|
| "python nicht gefunden" | Python zum PATH hinzufügen |
| Visual C++ Fehler | Build Tools installieren |
| Antivirus blockiert | Ausnahme hinzufügen oder signieren |
| DLL-Fehler | Ganzen Ordner dist/BeamerMapper/ verteilen |
| Import-Fehler | Modul zu hiddenimports in .spec hinzufügen |

Siehe [BUILD_GUIDE.md](BUILD_GUIDE.md#fehlerbehebung) für detaillierte Lösungen.
