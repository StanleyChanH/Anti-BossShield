import win32api
import win32con
from typing import NoReturn, Union

class WindowsLocker:
    """Windows系统锁屏工具"""
    
    @staticmethod
    def lock() -> bool:
        """锁定Windows系统"""
        try:
            # 模拟按下Win+L组合键
            win32api.keybd_event(win32con.VK_LWIN, 0, 0, 0)
            win32api.keybd_event(ord('L'), 0, 0, 0)
            win32api.keybd_event(ord('L'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_LWIN, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except Exception as e:
            print(f"锁定系统失败: {e}")
            return False

    @staticmethod
    def is_locked() -> Union[bool, None]:
        """检查系统是否已锁定(需要管理员权限)"""
        try:
            # 尝试获取桌面窗口句柄
            desktop = win32api.GetDesktopWindow()
            return win32api.GetWindowText(desktop) == ""
        except Exception as e:
            print(f"检查锁屏状态失败: {e}")
            return None