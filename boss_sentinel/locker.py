import ctypes

class WindowsLocker:
    """Windows系统锁屏工具"""

    @staticmethod
    def lock() -> bool:
        """锁定Windows系统"""
        try:
            ctypes.windll.user32.LockWorkStation()
            return True
        except Exception as e:
            print(f"锁定系统失败: {e}")
            return False
