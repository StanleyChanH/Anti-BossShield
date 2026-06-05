"""
PyQt5 runtime hook — ensure Qt can find platform plugins when running from PyInstaller bundle.
Sets QT_PLUGIN_PATH and adds library path before any Qt widget is created.
"""
import os
import sys


def _setup_qt_plugins():
    """Configure Qt plugin path for frozen (PyInstaller) environment."""
    if not hasattr(sys, '_MEIPASS'):
        return  # Not frozen, skip

    base = sys._MEIPASS
    qt_plugins = os.path.join(base, 'PyQt5', 'Qt5', 'plugins')

    if os.path.isdir(qt_plugins):
        # Set environment variable
        os.environ['QT_PLUGIN_PATH'] = qt_plugins
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(qt_plugins, 'platforms')

        # Also add via Qt API once QApplication is created
        try:
            from PyQt5.QtCore import QCoreApplication
            if QCoreApplication.instance() is not None:
                QCoreApplication.addLibraryPath(qt_plugins)
        except Exception:
            pass


_setup_qt_plugins()
