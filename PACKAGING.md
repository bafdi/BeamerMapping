# Packaging-Anleitung für BeamerMapper

Diese Anleitung beschreibt, wie du `BeamerMapper` als `.app` (macOS) oder `.exe` (Windows) packst.

## Kurz-Übersicht

| Plattform | Format | Methode | Zeitaufwand |
|-----------|--------|---------|------------|
| **macOS** | `.app` (Bundle) | `./package_mac.sh --py2app` | ~3-5 Min |
| **macOS** | `.dmg` (Installer) | `./create_dmg.sh` (nach .app build) | ~1 Min |
| **macOS** | Binary (onefile) | `./package_mac.sh` | ~2-3 Min |
| **Windows** | `.exe` (onefile) | `package_win.bat` (lokal) | ~3-5 Min |
| **Beide** | Automatisch | GitHub Actions | ~10-15 Min |

---

## Option 1: Lokal bauen (ohne Windows-Maschine nötig)

### macOS: `.app` via py2app

```bash
cd /Users/sebastianpfleiderer/PycharmProjects/BeamerMapper
chmod +x package_mac.sh
./package_mac.sh --py2app
```

**Ergebnis:** `dist/BeamerMapper.app`

**Optional:** Starte die App
```bash
open dist/BeamerMapper.app
```

### macOS: `.dmg` Installer erstellen

Nach dem Erstellen der `.app`, kannst du optional ein DMG-Installer erstellen:

```bash
chmod +x create_dmg.sh
./create_dmg.sh
```

**Ergebnis:** `BeamerMapper.dmg` (Installer-Image für macOS)

Das DMG enthält die .app und ermöglicht es Benutzern, die App per Drag & Drop in ihren Applications-Ordner zu installieren.

### macOS: Binary (onefile) via PyInstaller

```bash
./package_mac.sh
# oder mit OneDir zum Debuggen:
./package_mac.sh --onedir
```

**Ergebnis:** `dist/BeamerMapping` (ausführbares Programm)

### Weitere Flags (macOS & Windows)

```bash
# macOS
./package_mac.sh --help

# Windows
package_win.bat --help
```

**Verfügbare Flags:**
- `--onedir` — OneDir-Build (statt OneFile, schneller zum Debuggen)
- `--no-clean` — Überspringe `--clean` (schneller bei inkrementellen Builds)
- `--console` — Zeige Konsole (stdout/stderr sichtbar)

---

## Option 2: GitHub Actions (empfohlen, keine Windows-Maschine nötig)

### Einmalige Einrichtung

1. Pushe dein Repo zu GitHub (wenn noch nicht geschehen)
   ```bash
   git remote add origin https://github.com/DEIN_USERNAME/BeamerMapping.git
   git push -u origin main
   ```

2. GitHub Actions sollte automatisch aktiviert sein. Prüfe im Repo:
   → **Actions** Tab → sollte Workflow `Build Artifacts (macOS + Windows)` sehen.

### Build starten

**Option A: Automatisch (bei jedem Push)**
- Jedes Mal wenn du zu `main`/`master` pushst, wird ein Build gestartet.

**Option B: Manuell starten**
1. GitHub → Repo → **Actions** Tab
2. Klicke auf `Build Artifacts (macOS + Windows)`
3. Klicke **Run workflow** (rechts oben)
4. Wähle `main` Branch
5. Klick **Run workflow**

### Artefakte herunterladen

Nach ~10-15 Min (wenn Build erfolgreich):
1. Gehe zu **Actions** → letzter Run
2. Scrolle nach unten → **Artifacts**
3. Lade herunter:
   - `BeamerMapping-macos-app` (`.app.zip`)
   - `BeamerMapper-windows-exe` (`.exe`)

---

## Troubleshooting

### Problem: `python: command not found` (macOS/Linux)

**Lösung:** Nutze `python3` statt `python`, oder aliasiere:
```bash
alias python=python3
```

### Problem: PyQt6 platform plugin error (macOS)

Wenn die App startet, aber Qt-Plugin-Fehler zeigt:

**Lösung (kurz):**
```bash
# Manuell Plugins kopieren (falls nötig)
# Das sollte das Skript aber automatisch machen
```

Falls das nicht hilft, melde Issue.

### Problem: `.exe` wird von Windows Defender als verdächtig erkannt

Das ist normal bei ungezeigten Programmen. Mögliche Lösungen:
1. **Code Signing:** Signiere die `.exe` (erfordert Zertifikat)
2. **Microsoft Defender Smartscreen:** Füge Exception hinzu oder warte 48h
3. **VirusTotal:** Prüfe, ob das eine echte Warnung ist

### Problem: GitHub Actions schlägt fehl

**Schritte:**
1. Gehe zu **Actions** → fehlender Run
2. Klick auf Job (macOS oder Windows)
3. Scrolle zu `Run macOS build` / `Run Windows build`
4. Lese die Fehlermeldung
5. Häufig: Fehlende Dependencies → prüfe `requirements.txt`

---

## Für Entwickler: Builds in CI/CD anpassen

### Workflow-Datei

Ort: `.github/workflows/build.yml`

**Wenn du z.B. Signieren/Notarisierung hinzufügen willst:**

#### macOS Notarisierung

```yaml
- name: Sign and notarize macOS app
  run: |
    codesign --deep --force --options runtime \
      --sign "Developer ID Application: Your Name (TEAMID)" \
      dist/BeamerMapper.app
    
    ditto -c -k --sequesterRsrc --keepParent dist/BeamerMapper.app BeamerMapper.app.zip
    xcrun notarytool submit BeamerMapper.app.zip \
      --keychain-profile "AC_PASSWORD_PROFILE" --wait
    xcrun stapler staple dist/BeamerMapper.app
```

#### Windows Code Signing

```yaml
- name: Sign Windows exe
  run: |
    signtool sign /fd SHA256 /a /tr http://timestamp.digicert.com \
      /td SHA256 /v dist/BeamerMapper.exe
```

**Hinweis:** Benötigt GitHub Secrets (z.B. `APPLE_DEVELOPER_ACCOUNT`, `WINDOWS_CERTIFICATE_PASSWORD`).

---

## Zusätzliche Ressourcen

- **py2app Doku:** https://py2app.readthedocs.io/
- **PyInstaller Doku:** https://pyinstaller.org/
- **GitHub Actions:** https://docs.github.com/en/actions

---

## Support

Wenn etwas nicht funktioniert:
1. Prüfe die Logs in GitHub Actions (oder lokales Terminal-Output)
2. Stelle sicher, dass `requirements.txt` alle Dependencies hat
3. Prüfe, ob `icon.icns` (macOS) / `icon.ico` (Windows) existiert (optional, aber empfohlen)


