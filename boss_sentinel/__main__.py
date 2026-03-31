"""
Boss Sentinel 入口点
修复含中文路径时 PyTorch DLL 加载失败的问题

PyTorch 2.x 的 _load_dll_libraries() 使用 LoadLibraryExW 加载 DLL，
在含非 ASCII 字符的路径下，DLL 初始化可能失败（WinError 1114）。
解决方案：在 torch 被 import 之前，先用 ctypes.CDLL 预加载所有 DLL。
"""
import os
import sys
import ctypes
import glob

def _preload_torch_dlls():
    """在 torch import 之前预加载所有 DLL，绕过 LoadLibraryExW 的问题"""
    if sys.platform != "win32":
        return

    try:
        import importlib.util
        spec = importlib.util.find_spec("torch")
        if spec is None or spec.origin is None:
            return
        torch_lib = os.path.join(os.path.dirname(spec.origin), "lib")
        if not os.path.isdir(torch_lib):
            return

        # 先用 os.add_dll_directory 注册目录
        try:
            os.add_dll_directory(torch_lib)
        except (OSError, FileNotFoundError):
            pass

        # 预加载所有 DLL（用 ctypes.CDLL，不使用 LoadLibraryExW 的限制标志）
        for dll in sorted(glob.glob(os.path.join(torch_lib, "*.dll"))):
            try:
                ctypes.CDLL(dll)
            except OSError:
                pass
    except Exception:
        pass

# 在任何可能触发 torch import 的模块之前预加载
_preload_torch_dlls()

from boss_sentinel.gui import run_gui

if __name__ == "__main__":
    run_gui()
