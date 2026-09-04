# -*- mode: python ; coding: utf-8 -*-
#
# Paths use SPECPATH (the directory of this .spec file, injected by
# PyInstaller) so the build works regardless of which cwd pyinstaller
# is invoked from. A relative "icon.ico" would silently get skipped
# if the build was kicked off from anywhere other than the repo root.

import os

ROOT = SPECPATH
ICON = os.path.join(ROOT, 'icon.ico')
SOUNDS = os.path.join(ROOT, 'sounds')
VERSION_FILE = os.path.join(ROOT, 'icon_assets', 'version_info.txt')


a = Analysis(
    [os.path.join(ROOT, 'cac_gui.py')],
    pathex=[ROOT],
    binaries=[],
    # Ship icon.ico and the verdict .wav files inside the onefile exe
    # so the runtime can find them via sys._MEIPASS (see _resource_path
    # in cac_gui.py and sound.py). The same icon.ico is also embedded as
    # the exe's File Explorer icon via the EXE(icon=...) line below —
    # separate concern.
    datas=[(ICON, '.'), (SOUNDS, 'sounds')],
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
    icon=ICON,
    version=VERSION_FILE,
)
