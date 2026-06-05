# -*- mode: python ; coding: utf-8 -*-
"""
Boss Sentinel PyInstaller 配置文件
使用 onedir 模式避免 PyTorch DLL 加载问题
"""

import os, pathlib, sys
# Resolve PyQt5 plugins path using Python (handles Unicode correctly)
_venv_site = str(pathlib.Path(sys.prefix) / "Lib" / "site-packages")
_qt_plugins = os.path.join(_venv_site, "PyQt5", "Qt5", "plugins")
_qt_translations = os.path.join(_venv_site, "PyQt5", "Qt5", "translations")

a = Analysis(
    ['boss_sentinel\\__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('boss_sentinel', 'boss_sentinel'),
        (_qt_plugins, 'PyQt5/Qt5/plugins'),
        (_qt_translations, 'PyQt5/Qt5/translations'),
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
        # 新增功能模块
        'boss_sentinel.shoulder_surfing',
        'boss_sentinel.intruder_capture',
        'boss_sentinel.pomodoro',
        'boss_sentinel.mqtt_bridge',
        'boss_sentinel.drowsiness_detector',
    ],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=['hooks/runtime_hook_torch.py', 'hooks/runtime_hook_qt.py'],
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
