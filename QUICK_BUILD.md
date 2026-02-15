# 🚀 BeamerMapper Build - Schnellreferenz

## Windows - 3 Optionen

### ⚡ Option 1: Einzelne .exe (EMPFOHLEN)
```cmd
build_windows_onefile.bat
```
→ Ergebnis: `dist\BeamerMapper.exe` (eine Datei)
→ Am einfachsten zum Verteilen!

### 🏃 Option 2: Ordner (schnellerer Start)
```cmd
build_windows.bat
```
→ Ergebnis: `dist\BeamerMapper\` (Ordner)
→ Als ZIP verteilen

### 🎁 Option 3: Professioneller Installer
```cmd
1. build_windows.bat ausführen
2. Inno Setup installieren
3. installer_windows.iss kompilieren
```
→ Ergebnis: `Output\BeamerMapper-Setup.exe`

## macOS - .dmg Installer

```bash
./build_macos.sh
```
→ Ergebnis: `BeamerMapper-macOS.dmg`
→ **Achtung:** Muss auf macOS ausgeführt werden!

## ✅ Vor dem Build

```bash
python validate_build_env.py
```
Prüft: Python, Dependencies, Tools

## 📦 Verteilung

| Was? | Wie? |
|------|------|
| Einzelne .exe | Einfach die .exe weitergeben |
| Ordner | Als ZIP komprimieren und verteilen |
| Installer | BeamerMapper-Setup.exe verteilen |
| macOS .dmg | BeamerMapper-macOS.dmg verteilen |

## 🆘 Hilfe

| Problem | Lösung |
|---------|--------|
| "python nicht gefunden" | Python installieren + PATH |
| Visual C++ Fehler | Build Tools installieren |
| Antivirus blockiert | Ausnahme hinzufügen |

📖 **Mehr Hilfe:** [BUILD_SUMMARY.md](BUILD_SUMMARY.md)

---
**Tipp:** Für Tests einfach `python run_mapper.py` nutzen - kein Build nötig!
