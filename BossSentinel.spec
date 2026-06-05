# -*- mode: python ; coding: utf-8 -*-
"""
Boss Sentinel PyInstaller 配置文件
使用 onedir 模式避免 PyTorch DLL 加载问题
Web UI 版本 — 无需 PyQt5
"""

import os, pathlib, sys

a = Analysis(
    ['boss_sentinel\\__main__.py'],
    pathex=[],
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
        # Web UI 框架
        'fastapi',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'starlette',
        'starlette.routing',
        'starlette.middleware',
        'starlette.staticfiles',
        'starlette.responses',
        'anyio',
        'anyio._backends',
        'anyio._backends._asyncio',
        'httpcore',
        'httpcore._async',
        'httpcore._sync',
        'httptools',
        'python_multipart',
        # 功能模块
        'boss_sentinel.shoulder_surfing',
        'boss_sentinel.intruder_capture',
        'boss_sentinel.pomodoro',
        'boss_sentinel.mqtt_bridge',
        'boss_sentinel.drowsiness_detector',
        'boss_sentinel.web',
        'boss_sentinel.web.server',
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
        'PyQt5',
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
