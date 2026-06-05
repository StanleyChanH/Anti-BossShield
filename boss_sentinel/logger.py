"""Logging utility for Boss Sentinel with rotating file handler."""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional


# Mirror standard logging level constants so callers can use
# SentinelLogger.log("msg", level=SentinelLogger.INFO).
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL


class SentinelLogger:
    """Sentinel system logger backed by :mod:`logging`.

    Uses a :class:`~logging.handlers.RotatingFileHandler` so log files
    are automatically rotated when they grow too large.

    The public :meth:`log` method preserves backward compatibility with
    the previous hand-rolled implementation while delegating to the
    thread-safe :mod:`logging` infrastructure under the hood.
    """

    # Keep the same timestamp format as the original implementation.
    _LOG_FORMAT: str = "[%(asctime)s] %(message)s"
    _DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

    def __init__(
        self,
        log_file: str = "sentinel_log.txt",
        max_bytes: int = 1_048_576,  # 1 MB
        backup_count: int = 5,
    ) -> None:
        """Initialise the logger.

        Creates the log file's parent directory (if needed) and appends
        a startup banner.

        Args:
            log_file: Path to the log file.
            max_bytes: Maximum size in bytes before rotation (default 1 MB).
            backup_count: Number of rotated backup files to keep (default 5).
        """
        self.log_file: str = log_file

        log_dir = os.path.dirname(self.log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        # Build a dedicated logger instance so we don't pollute the root
        # logger and don't interfere with other libraries' logging config.
        self._logger: logging.Logger = logging.getLogger(f"sentinel.{log_file}")
        self._logger.setLevel(logging.DEBUG)

        # Avoid adding duplicate handlers when SentinelLogger is
        # instantiated multiple times for the same file (e.g. during
        # hot-reload).
        if not self._logger.handlers:
            formatter = logging.Formatter(self._LOG_FORMAT, datefmt=self._DATE_FORMAT)

            file_handler = RotatingFileHandler(
                self.log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)

            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

        # Startup banner (written directly, not through the logger, to
        # match the original two-newline separator).
        self._write_startup_banner()

    # -- internal helpers --------------------------------------------------

    def _write_startup_banner(self) -> None:
        """Append a startup separator to the log file."""
        timestamp = datetime.now().strftime(self._DATE_FORMAT)
        banner = f"\n\n=== 哨兵系统启动 {timestamp} ===\n"
        try:
            with open(self.log_file, "a", encoding="utf-8") as fh:
                fh.write(banner)
        except OSError:
            pass  # best-effort; don't crash on banner failure

    # -- public API --------------------------------------------------------

    def log(
        self,
        message: str,
        level: int = logging.INFO,
        print_console: bool = True,
    ) -> None:
        """Record a log message.

        Maintains backward compatibility with the previous
        ``log(message, print_console=True)`` signature while routing
        through the standard :mod:`logging` module.

        Args:
            message: The log message text.
            level: Logging level (default ``logging.INFO``).
            print_console: Kept for backward compatibility; the console
                handler is always attached so this parameter is accepted
                but no longer controls behaviour.
        """
        self._logger.log(level, message)
