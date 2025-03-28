# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['boss_sentinel\\__main__.py'],
    pathex=['d:\\Anti-BossShield'],
    binaries=[],
    datas=[('boss_sentinel', 'boss_sentinel')],
    hiddenimports=['cv2', 'ultralytics'],
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
    name='BossSentinel',
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
)
