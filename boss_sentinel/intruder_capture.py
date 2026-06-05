"""Intruder photo capture for Boss Sentinel.

Saves timestamped frames with a watermark overlay whenever an intruder
is detected.  Includes a configurable cooldown to avoid flooding the
filesystem with near-duplicate images.
"""

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Default cooldown between consecutive captures (seconds)
_DEFAULT_CAPTURE_COOLDOWN: float = 5.0

# Watermark text constants (OpenCV)
_FONT = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE = 0.6
_FONT_COLOR_TIMESTAMP = (255, 255, 255)   # white
_FONT_COLOR_INTRUDER = (0, 0, 255)        # red
_FONT_THICKNESS = 2
_LINE_TYPE = cv2.LINE_AA


class IntruderCapture:
    """Capture and persist intruder frames with a timestamp watermark.

    The class enforces a cooldown period between successive saves so
    that rapid, repeated detections do not fill up disk space.

    Example::

        capturer = IntruderCapture(save_dir="intruder_photos")
        path = capturer.capture(frame, timestamp=datetime.now())
        if path:
            print(f"Intruder photo saved to {path}")
    """

    def __init__(
        self,
        save_dir: str = "intruder_photos",
        cooldown: float = _DEFAULT_CAPTURE_COOLDOWN,
    ) -> None:
        """Initialise the intruder capture module.

        Args:
            save_dir: Directory where intruder photos are stored.
                Created automatically if it does not exist.
            cooldown: Minimum number of seconds between consecutive
                captures.  Any :meth:`capture` call that arrives within
                the cooldown window returns ``None``.
        """
        self._save_dir = Path(save_dir)
        self._save_dir.mkdir(parents=True, exist_ok=True)
        self._cooldown = cooldown
        self._last_capture_time: float = 0.0

        logger.info(
            "IntruderCapture initialised (save_dir=%s, cooldown=%.1fs)",
            self._save_dir,
            self._cooldown,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture(
        self,
        frame: np.ndarray,
        timestamp: Optional[datetime] = None,
    ) -> Optional[str]:
        """Save an intruder frame to disk with a watermark overlay.

        If called within the cooldown period of the previous capture,
        the frame is silently dropped and ``None`` is returned.

        Args:
            frame: A BGR image (OpenCV ``numpy`` array).
            timestamp: The datetime to stamp on the image.  Defaults to
                ``datetime.now()``.

        Returns:
            The absolute path of the saved image, or ``None`` if the
            capture was suppressed by the cooldown.
        """
        now = time.monotonic()
        if now - self._last_capture_time < self._cooldown:
            logger.debug("Capture suppressed by cooldown (%.1fs remaining)", self._cooldown - (now - self._last_capture_time))
            return None

        ts = timestamp or datetime.now()

        watermarked = self._add_watermark(frame.copy(), ts)

        filename = ts.strftime("intruder_%Y%m%d_%H%M%S_%f") + ".jpg"
        filepath = self._save_dir / filename

        success = cv2.imwrite(str(filepath), watermarked, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not success:
            logger.error("Failed to write intruder photo to %s", filepath)
            return None

        self._last_capture_time = now
        logger.info("Intruder photo saved: %s", filepath)
        return str(filepath.resolve())

    def get_recent_captures(self, count: int = 10) -> List[str]:
        """Return paths of the most recent intruder photos.

        Files are sorted by modification time in descending order (newest
        first).

        Args:
            count: Maximum number of paths to return.

        Returns:
            A list of absolute file paths, newest first.
        """
        if not self._save_dir.exists():
            return []

        files = list(self._save_dir.glob("intruder_*.jpg"))
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return [str(f.resolve()) for f in files[:count]]

    def cleanup_old(self, max_age_days: int = 30) -> int:
        """Delete intruder photos older than *max_age_days*.

        Args:
            max_age_days: Maximum age in days.  Files whose modification
                time is older than this threshold are removed.

        Returns:
            The number of files removed.
        """
        if not self._save_dir.exists():
            return 0

        cutoff = datetime.now() - timedelta(days=max_age_days)
        cutoff_ts = cutoff.timestamp()
        removed = 0

        for f in self._save_dir.glob("intruder_*.jpg"):
            try:
                if f.stat().st_mtime < cutoff_ts:
                    f.unlink()
                    removed += 1
            except OSError:
                logger.warning("Could not delete old capture: %s", f)

        if removed:
            logger.info("Cleaned up %d old intruder photo(s) (older than %d days)", removed, max_age_days)
        return removed

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _add_watermark(frame: np.ndarray, dt: datetime) -> np.ndarray:
        """Overlay timestamp and "INTRUDER" text on the frame.

        The timestamp is drawn in the top-left corner and the "INTRUDER"
        label is drawn immediately below it.

        Args:
            frame: A BGR image to annotate **in-place** (caller should
                pass a copy if the original must be preserved).
            dt: The datetime to render.

        Returns:
            The annotated frame (same reference as *frame*).
        """
        ts_text = dt.strftime("%Y-%m-%d %H:%M:%S")
        intruder_text = "INTRUDER"

        # Timestamp — top-left with small margin
        cv2.putText(
            frame,
            ts_text,
            org=(10, 25),
            fontFace=_FONT,
            fontScale=_FONT_SCALE,
            color=_FONT_COLOR_TIMESTAMP,
            thickness=_FONT_THICKNESS,
            lineType=_LINE_TYPE,
        )

        # INTRUDER label — below the timestamp
        cv2.putText(
            frame,
            intruder_text,
            org=(10, 55),
            fontFace=_FONT,
            fontScale=_FONT_SCALE,
            color=_FONT_COLOR_INTRUDER,
            thickness=_FONT_THICKNESS,
            lineType=_LINE_TYPE,
        )

        return frame
