# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['cac_gui.py'],
    pathex=[],
    binaries=[],
    # Ship icon.ico inside the onefile exe so the runtime can find it
    # via sys._MEIPASS (see _resource_path in cac_gui.py). The same
    # icon.ico is also embedded as the exe's File Explorer icon via
    # the EXE(icon=...) line below — separate concern.
    datas=[('icon.ico', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BarScanner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)
