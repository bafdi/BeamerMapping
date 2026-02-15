# Windows Build - Schnellstart

Diese Anleitung zeigt Ihnen, wie Sie auf Ihrem Windows-Laptop eine .exe-Datei für BeamerMapper erstellen.

## ⚡ Schnellstart (5 Minuten)

### 1. Python installieren (falls noch nicht vorhanden)
- Download: https://www.python.org/downloads/
- **Wichtig:** Aktivieren Sie "Add Python to PATH" während der Installation!

### 2. Repository öffnen
Öffnen Sie die Eingabeaufforderung (CMD) oder PowerShell:
```cmd
cd C:\Pfad\zum\BeamerMapping
```

Oder: Rechtsklick im Ordner → "Terminal hier öffnen"

### 3. Build ausführen
```cmd
build_windows.bat
```

Das war's! Die .exe wird erstellt in: `dist\BeamerMapper\BeamerMapper.exe`

---

## 📦 Verteilung

Nach dem Build haben Sie 2 Optionen:

### Option A: Ordner als ZIP verteilen (Einfach)

1. Rechtsklick auf den Ordner `dist\BeamerMapper`
2. "Senden an" → "ZIP-komprimierter Ordner"
3. Benennen Sie die ZIP-Datei z.B. `BeamerMapper-Windows.zip`
4. Verteilen Sie diese ZIP-Datei

**Benutzer müssen:**
- ZIP entpacken
- `BeamerMapper.exe` ausführen

### Option B: Installer erstellen (Professionell)

Für einen richtigen Windows-Installer:

1. **Inno Setup installieren:**
   - Download: https://jrsoftware.org/isdl.php
   - Installieren Sie das Programm

2. **Installer kompilieren:**
   - Öffnen Sie `installer_windows.iss` mit Inno Setup
   - Klicken Sie auf "Compile" (oder F9)
   - Fertig! Der Installer ist in `Output\BeamerMapper-Setup.exe`

3. **Verteilen:**
   - Nur die `BeamerMapper-Setup.exe` Datei verteilen
   - Benutzer führen den Installer aus wie jedes andere Programm

---

## 🔧 Häufige Probleme

### "python ist kein gültiger Befehl"
→ Python ist nicht im PATH. Neu installieren mit "Add Python to PATH"

### "pip ist kein gültiger Befehl"
```cmd
python -m pip install --upgrade pip
```

### Visual C++ Fehler
- Installieren Sie "Microsoft C++ Build Tools"
- Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/

### Antivirus blockiert die .exe
- Normal bei PyInstaller
- Fügen Sie eine Ausnahme hinzu oder signieren Sie die .exe

### App startet nicht
Öffnen Sie CMD im dist\BeamerMapper Ordner und führen Sie aus:
```cmd
BeamerMapper.exe
```
So sehen Sie die Fehlermeldung.

---

## 💡 Tipps

### Kleinere .exe-Datei
Bearbeiten Sie `BeamerMapper.spec` und fügen Sie nicht benötigte Module zu `excludes` hinzu.

### Alles-in-einer .exe
Für eine einzelne große .exe-Datei statt Ordner:
```cmd
pyinstaller --onefile --windowed --name BeamerMapper run_mapper.py
```

### Icon hinzufügen
1. Erstellen oder herunterladen Sie eine `.ico` Datei
2. In `BeamerMapper.spec` setzen: `icon='pfad/zur/icon.ico'`

---

## 📚 Weitere Hilfe

Vollständige Anleitung: [BUILD_GUIDE.md](BUILD_GUIDE.md)

Bei Problemen: https://github.com/bafdi/BeamerMapping/issues
