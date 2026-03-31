# -*- mode: python ; coding: utf-8 -*-
"""
Boss Sentinel PyInstaller 配置文件
使用 onedir 模式避免 PyTorch DLL 加载问题
"""

a = Analysis(
    ['boss_sentinel\\__main__.py'],
    pathex=['d:\\Anti-BossShield'],
    binaries=[],
    datas=[
        ('boss_sentinel', 'boss_sentinel'),
    ],
    hiddenimports=[
        'cv2',
        'numpy',
        'torch',
        'torchvision',
        'ultralytics',
        'facenet_pytorch',
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
    ],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=['hooks/runtime_hook_torch.py'],
    excludes=[
        'tkinter',
        'matplotlib',
        'IPython',
        'jupyter',
        'notebook',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BossSentinel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='BossSentinel',
)
