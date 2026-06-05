"""Build script that patches os.path to fix Chinese path garbling in PyInstaller."""
import os
import sys
import pathlib

_GARBLED = "git??"
_CORRECT = "git项目"

def _fix_path(p):
    if isinstance(p, str) and _GARBLED in p:
        return p.replace(_GARBLED, _CORRECT)
    return p

_orig_exists = os.path.exists
_orig_isdir = os.path.isdir
_orig_isfile = os.path.isfile
_orig_listdir = os.listdir

def _patched_exists(path):
    return _orig_exists(_fix_path(path))

def _patched_isdir(path):
    return _orig_isdir(_fix_path(path))

def _patched_isfile(path):
    return _orig_isfile(_fix_path(path))

def _patched_listdir(path='.'):
    return _orig_listdir(_fix_path(path))

os.path.exists = _patched_exists
os.path.isdir = _patched_isdir
os.path.isfile = _patched_isfile
os.listdir = _patched_listdir

# Patch os.walk too
_orig_walk = os.walk

def _patched_walk(top, topdown=True, onerror=None, followlinks=False):
    return _orig_walk(_fix_path(top), topdown=topdown, onerror=onerror, followlinks=followlinks)

os.walk = _patched_walk

print(f"[PATCH] os.path patched to fix '{_GARBLED}' -> '{_CORRECT}'")

from PyInstaller.__main__ import run as pyi_run

os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f"[BUILD] CWD: {os.getcwd()}")

sys.argv = ["pyinstaller", "BossSentinel.spec", "--noconfirm"]
pyi_run()
