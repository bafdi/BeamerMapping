# PyInstaller spec file for BeamerMapper (example)
# Generated template - passe `datas`/`binaries`/`hiddenimports` an dein Projekt an.

# ...existing code...

block_cipher = None

a = Analysis([
    './run_mapper.py'
],
    pathex=['.'],
    binaries=[],
    datas=[
        ('presets', 'presets'),
        ('build', 'build')
    ],
    hiddenimports=[
        'PyQt6.sip',
        'cv2',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='BeamerMapper',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon='icon.ico'
)

# für OneDir: coll = COLLECT(...)
# für OneFile PyInstaller erzeugt ein self-extracting exe

# ...existing code...

