"""Windows screen locking utility for Boss Sentinel."""

import ctypes
import logging
import platform
from typing import Optional

logger = logging.getLogger(__name__)


class WindowsLocker:
    """Windows system screen locker.

    Uses the Windows LockWorkStation API via ctypes to lock the
    current workstation.  On non-Windows platforms every call to
    :meth:`lock` logs a warning and returns ``False``.
    """

    _IS_WINDOWS: bool = platform.system() == "Windows"

    @staticmethod
    def lock() -> bool:
        """Lock the Windows workstation.

        Returns:
            ``True`` if the lock request was successfully submitted,
            ``False`` on any error or when running on a non-Windows
            platform.
        """
        if not WindowsLocker._IS_WINDOWS:
            logger.warning(
                "LockWorkStation is only available on Windows; "
                "current platform is %s",
                platform.system(),
            )
            return False

        try:
            result: Optional[int] = ctypes.windll.user32.LockWorkStation()
            if result:
                logger.info("Screen lock request submitted successfully")
                return True
            else:
                logger.error("LockWorkStation returned failure (result=%s)", result)
                return False
        except Exception as e:
            logger.exception("Failed to lock system: %s", e)
            return False
