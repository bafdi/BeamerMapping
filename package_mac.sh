#!/usr/bin/env bash
set -euo pipefail

# Packaging-Skript für macOS.
# - Standard: PyInstaller build (onefile).
# - Optional: py2app build (echtes .app bundle) via --py2app Flag.
# Zusätzliche Flags:
#   --onedir     : Erzeuge einen OneDir-Build (statt OneFile)
#   --no-clean   : Überspringe --clean bei PyInstaller
#   --console    : Öffne mit Konsole (don't use --noconsole)
#   --help       : Zeige diese Hilfe

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv_pack"
VENV_PY2APP_DIR="$PROJECT_DIR/.venv_py2app"
DIST_DIR="$PROJECT_DIR/dist"

# Argumente parsen
USE_PY2APP=false
ONEDIR=false
NO_CLEAN=false
FORCE_CONSOLE=false

usage() {
  cat <<EOF
Usage: $0 [--py2app] [--onedir] [--no-clean] [--console] [--help]

  --py2app     Build a macOS .app using py2app (uses .venv_py2app)
  --onedir     Create a OneDir PyInstaller build (no --onefile)
  --no-clean   Don't pass --clean to PyInstaller (faster incremental)
  --console    Keep console (don't add --noconsole)
  --help       Show this help
EOF
}

for arg in "$@"; do
  case "$arg" in
    --py2app)
      USE_PY2APP=true
      ;;
    --onedir)
      ONEDIR=true
      ;;
    --no-clean)
      NO_CLEAN=true
      ;;
    --console)
      FORCE_CONSOLE=true
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      # ignore unknown args for now
      ;;
  esac
done

echo "Projekt: $PROJECT_DIR"

if [ "$USE_PY2APP" = true ]; then
  echo "Starte py2app-Build (echtes .app bundle)"
  # Erstelle/verwende eigene venv für py2app
  if [ ! -d "$VENV_PY2APP_DIR" ]; then
    python3 -m venv "$VENV_PY2APP_DIR"
  fi
  # shellcheck source=/dev/null
  source "$VENV_PY2APP_DIR/bin/activate"

  pip install --upgrade pip setuptools wheel
  if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    pip install -r "$PROJECT_DIR/requirements.txt"
  fi
  pip install py2app

  # führe py2app (setup.py) aus
  if [ ! -f "$PROJECT_DIR/setup.py" ]; then
    echo "Fehler: setup.py nicht gefunden. Bitte setup.py für py2app anlegen."
    exit 1
  fi

  # Clean alten dist/build falls vorhanden
  rm -rf "$PROJECT_DIR/build" "$PROJECT_DIR/dist"
  python3 "$PROJECT_DIR/setup.py" py2app

  echo "py2app fertig. Ergebnis: $PROJECT_DIR/dist"
  exit 0
fi

# --- Standard-Pfad: PyInstaller ---

echo "Starte PyInstaller-Build (Standard: onefile)"

# 1) Virtuelle Umgebung einrichten (wiederverwenden falls vorhanden)
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# 2) Abhängigkeiten installieren
pip install --upgrade pip setuptools wheel
if [ -f "$PROJECT_DIR/requirements.txt" ]; then
  pip install -r "$PROJECT_DIR/requirements.txt"
fi
pip install pyinstaller pyinstaller-hooks-contrib

# 3) Build-Ordner
mkdir -p "$DIST_DIR"

# 4) Sammle zusätzliche Ressourcen (PyQt6 plugins, cv2 libs)
PYINSTALLER_ADDITIONS=()

# Trennzeichen für --add-data / --add-binary auf macOS ist ':'
SEP=":"

# Versuche PyQt6 plugins-Ordner zu finden
PYQT_PLUGINS=$(python3 - <<PY
import os
try:
    import PyQt6
    p = os.path.join(os.path.dirname(PyQt6.__file__), 'Qt', 'plugins')
    print(p)
except Exception:
    pass
PY
)

if [ -n "$PYQT_PLUGINS" ] && [ -d "$PYQT_PLUGINS" ]; then
  echo "Gefundener PyQt6 plugins-Ordner: $PYQT_PLUGINS"
  PYINSTALLER_ADDITIONS+=("--add-data" "$PYQT_PLUGINS${SEP}PyQt6/Qt/plugins")
else
  echo "PyQt6 plugins-Ordner nicht gefunden; falls du Qt-Plugin-Fehler bekommst, füge ihn manuell hinzu."
fi

# Versuche OpenCV (cv2) Package-Ordner zu finden
CV2_DIR=$(python3 - <<PY
import os
try:
    import cv2
    print(os.path.dirname(cv2.__file__))
except Exception:
    pass
PY
)

if [ -n "$CV2_DIR" ] && [ -d "$CV2_DIR" ]; then
  echo "Gefundener cv2-Ordner: $CV2_DIR"
  # Füge cv2 Verzeichnis als binary hinzu (PyInstaller behandelt native libs besser als binaries)
  PYINSTALLER_ADDITIONS+=("--add-binary" "$CV2_DIR${SEP}cv2")
else
  echo "cv2-Ordner nicht gefunden; falls OpenCV-Probleme auftreten, überprüfe die Installation."
fi

# Optional: Icon vorhanden?
ICON_ARG=()
if [ -f "$PROJECT_DIR/icon.icns" ]; then
  ICON_ARG+=("--icon" "$PROJECT_DIR/icon.icns")
else
  echo "Kein icon.icns im Projektordner gefunden; Icon wird nicht gesetzt."
fi

# 5) Baue mit PyInstaller
# Hinweis: --add-data nutzt auf macOS ':' als Trennzeichen (src:dest)
PYINSTALLER_CMD=(pyinstaller --noconfirm --name BeamerMapper)

# default: add --clean unless NO_CLEAN
if [ "$NO_CLEAN" = false ]; then
  PYINSTALLER_CMD+=(--clean)
fi

# default: onefile unless ONEDIR set
if [ "$ONEDIR" = false ]; then
  PYINSTALLER_CMD+=(--onefile)
fi

# GUI-App: keine Konsole (unless FORCE_CONSOLE)
if [ "$FORCE_CONSOLE" = false ]; then
  PYINSTALLER_CMD+=(--noconsole)
fi

# Füge standardmäßig Presets und build-Ordner ein (falls vorhanden)
if [ -d "$PROJECT_DIR/presets" ]; then
  PYINSTALLER_CMD+=(--add-data "$PROJECT_DIR/presets${SEP}presets")
fi
if [ -d "$PROJECT_DIR/build" ]; then
  PYINSTALLER_CMD+=(--add-data "$PROJECT_DIR/build${SEP}build")
fi

# Verberge diesen hidden import, häufig benötigt für PyQt6
PYINSTALLER_CMD+=(--hidden-import=PyQt6.sip --hidden-import=PyQt6.QtSvg)

# Füge dynamisch gefundene Zusatz-Args hinzu
for ((i=0;i<${#PYINSTALLER_ADDITIONS[@]};i+=2)); do
  PYINSTALLER_CMD+=("${PYINSTALLER_ADDITIONS[i]}" "${PYINSTALLER_ADDITIONS[i+1]}")
done

# Icon
if [ ${#ICON_ARG[@]} -gt 0 ]; then
  PYINSTALLER_CMD+=("${ICON_ARG[0]}" "${ICON_ARG[1]}")
fi

# Ziel-Script
PYINSTALLER_CMD+=("$PROJECT_DIR/run_mapper.py")

# Echo und Ausführung
printf 'PyInstaller-Aufruf:'
for arg in "${PYINSTALLER_CMD[@]}"; do printf ' %q' "$arg"; done
printf '\n'

# Führe den Befehl aus (array-Formate erhalten korrekt Anführungszeichen)
"${PYINSTALLER_CMD[@]}"


echo "Fertig. Artefakt(en) liegen in: $DIST_DIR"

echo "--- Hinweise für .app-Bundle mit py2app (optional) ---"
echo "Du kannst dieses Skript mit dem Parameter --py2app aufrufen, um stattdessen ein echtes macOS .app via py2app zu bauen."
echo "Wenn du Signieren / Notarisieren brauchst, sag Bescheid und ich liefere die Befehle."
