import os
import sys
from setuptools import setup, find_packages

APP = ['run_mapper.py']

# Sammle alle Dateien unter presets/ und build/ und mappe sie als data_files für py2app
def collect_data_dirs(root_dirs):
    data_files = []
    for root in root_dirs:
        if not os.path.isdir(root):
            continue
        files = []
        for dirpath, _, filenames in os.walk(root):
            for f in filenames:
                files.append(os.path.join(dirpath, f))
        if files:
            # Zielordner im Bundle: relative zu root, wir verwenden den Ordnernamen
            data_files.append((root, files))
    return data_files

DATA_FILES = collect_data_dirs(['presets', 'build'])

PY2APP_OPTIONS = {
    'argv_emulation': False,
    'packages': ['PyQt6', 'cv2', 'numpy'],
    'includes': ['PyQt6.sip'],
    'plist': {
        'CFBundleName': 'BeamerMapper',
        'CFBundleShortVersionString': '1.0',
    }
}

# Füge das iconfile nur hinzu, falls es existiert
icon_path = 'icon.icns'
if os.path.isfile(icon_path):
    PY2APP_OPTIONS['iconfile'] = icon_path

# package_dir damit setuptools die Packages im src/ findet
PACKAGE_DIR = {'': 'src'}
PACKAGES = find_packages('src')

# Wenn der Benutzer explizit py2app aufruft (python setup.py py2app),
# übergeben wir die py2app-spezifischen Argumente. Dadurch vermeiden wir
# die "Unknown distribution option: 'app'"-Warnung, wenn py2app nicht installiert ist
# oder wenn setup.py ohne Kommando aufgerufen wird.
if 'py2app' in sys.argv:
    setup(
        app=APP,
        data_files=DATA_FILES,
        options={'py2app': PY2APP_OPTIONS},
        package_dir=PACKAGE_DIR,
        packages=PACKAGES,
    )
else:
    # Neutrales Setup, damit `python setup.py` ohne Argumente keine Warnungen auslöst.
    setup(
        name='BeamerMapper',
        version='1.0.0',
        packages=PACKAGES,
        package_dir=PACKAGE_DIR,
        data_files=DATA_FILES,
        description='Projection Mapper GUI application',
    )
