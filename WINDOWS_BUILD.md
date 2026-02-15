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

**Wählen Sie eine Option:**

**Option A: Ordner mit Dateien (Empfohlen - schneller Start)**
```cmd
build_windows.bat
```
Ergebnis: `dist\BeamerMapper\BeamerMapper.exe` + Dependencies

**Option B: Einzelne .exe Datei (Einfacher zu verteilen)**
```cmd
build_windows_onefile.bat
```
Ergebnis: `dist\BeamerMapper.exe` (eine große Datei)

Das war's! Die .exe ist jetzt erstellt.

---

## 📦 Verteilung

Nach dem Build haben Sie mehrere Optionen:

### Option A: Einzelne .exe Datei (Am einfachsten)

Wenn Sie `build_windows_onefile.bat` verwendet haben:
- Verteilen Sie einfach `dist\BeamerMapper.exe`
- Fertig! Nur eine Datei zum Verteilen

### Option B: Ordner als ZIP verteilen

Wenn Sie `build_windows.bat` verwendet haben:
1. Rechtsklick auf den Ordner `dist\BeamerMapper`
2. "Senden an" → "ZIP-komprimierter Ordner"
3. Benennen Sie die ZIP-Datei z.B. `BeamerMapper-Windows.zip`
4. Verteilen Sie diese ZIP-Datei

**Benutzer müssen:**
- ZIP entpacken
- `BeamerMapper.exe` ausführen

### Option C: Installer erstellen (Professionell)

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

## 🔄 Welche Option soll ich wählen?

| Methode | Vorteile | Nachteile | Am besten für |
|---------|----------|-----------|---------------|
| **Einzelne .exe** | ✅ Nur 1 Datei<br>✅ Am einfachsten | ⚠️ Größer (150-200MB)<br>⚠️ Langsamerer Start | Schnelle Weitergabe per E-Mail/Chat |
| **Ordner (ZIP)** | ✅ Kleinere Dateien<br>✅ Schnellerer Start | ⚠️ Viele Dateien<br>⚠️ Muss entpackt werden | Wenn Dateigröße wichtig ist |
| **Installer** | ✅ Professionell<br>✅ Startmenü/Desktop<br>✅ Uninstaller | ⚠️ Mehr Arbeit<br>⚠️ Benötigt Inno Setup | Öffentliche Distribution |

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
