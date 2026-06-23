# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['mido.backends.rtmidi']
hiddenimports += collect_submodules('src')


a = Analysis(
    ['src/loeric/server/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[('static', 'static'), ('src/loeric/config/performance', 'loeric/config/performance')],
    hiddenimports=hiddenimports,
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
    name='loeric',
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
    icon=['loeric-icon.png'],
)
