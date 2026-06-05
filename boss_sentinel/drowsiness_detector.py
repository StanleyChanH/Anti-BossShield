"""Drowsiness/Fatigue Detector using Eye Aspect Ratio (EAR).

Uses mediapipe face mesh (468 landmarks) for accurate EAR when available,
otherwise falls back to YOLOv8 5-keypoint approximation.

Ear formula: (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
"""

import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Mediapipe face-mesh landmark indices for the six key eye points.
LEFT_EYE: List[int] = [33, 160, 158, 133, 153, 144]
RIGHT_EYE: List[int] = [362, 385, 387, 263, 373, 380]

@dataclass
class DrowsinessResult:
    """Single-frame drowsiness analysis result.

    Attributes:
        is_drowsy: True when the subject's EAR is below threshold for
            *consecutive_frames* consecutive frames.
        ear_value: The computed Eye Aspect Ratio for this frame
            (average of both eyes).  ``-1.0`` when unavailable.
        blink_rate: Estimated blinks per minute based on recent history.
        alert_level: One of ``"normal"``, ``"drowsy"``, ``"critical"``.
        consecutive_drowsy_frames: How many successive frames have been
            classified as drowsy so far.
    """

    is_drowsy: bool
    ear_value: float
    blink_rate: float
    alert_level: str
    consecutive_drowsy_frames: int


class DrowsinessDetector:
    """Detect drowsiness / fatigue via Eye Aspect Ratio (EAR).

    Two operation modes:
    * **Full mesh** (mediapipe installed): uses 468-point face mesh for
      per-eye 6-point EAR computation.
    * **YOLOv8 keypoints** (fallback): uses the 5 facial keypoints
      returned by the YOLOv8-face model as a rough proxy.

    Args:
        ear_threshold: EAR value below which a single frame is considered
            drowsy.  Typical values are 0.2 -- 0.25.
        consecutive_frames: Number of *consecutive* drowsy frames required
            before :pyattr:`is_drowsy` becomes ``True``.
        alert_cooldown: Minimum seconds between two alert triggers from
            :meth:`should_alert`.
    """

    def __init__(
        self,
        ear_threshold: float = 0.2,
        consecutive_frames: int = 30,
        alert_cooldown: float = 60.0,
    ) -> None:
        self.ear_threshold = ear_threshold
        self.consecutive_frames = consecutive_frames
        self.alert_cooldown = alert_cooldown

        # Internal state
        self._consecutive_drowsy_frames: int = 0
        self._last_alert_time: float = 0.0

        # Blink detection state
        self._ear_history: List[float] = []  # recent EARs
        self._eyes_were_closed: bool = False
        self._blink_times: List[float] = []  # timestamps of detected blinks
        self._ear_history_max: int = 300  # ~10 s at 30 fps

        # Mediapipe lazily loaded reference
        self._mp_face_mesh = None
        self._mp_face_mesh_loaded: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def supports_detection() -> bool:
        """Return ``True`` if the *mediapipe* package is importable.

        When this returns ``False`` the detector can still operate in
        YOLOv8-keypoint fallback mode (less accurate).
        """
        try:
            import mediapipe  # noqa: F401

            return True
        except ImportError:
            return False

    def compute_ear(self, eye_points: List[Tuple[float, float]]) -> float:
        """Compute Eye Aspect Ratio from six (x, y) landmark points.

        The six points are ordered as::

            p1 ---- p4
            | \\  / |
            p2  ..  p5
            | /  \\ |
            p3 ---- p6

        EAR = (||p2 - p6|| + ||p3 - p5||) / (2 * ||p1 - p4||)

        Args:
            eye_points: A list of exactly 6 ``(x, y)`` tuples.

        Returns:
            The computed EAR value.  Returns ``-1.0`` when the input is
            invalid.
        """
        if len(eye_points) != 6:
            logger.warning(
                "compute_ear requires exactly 6 points, got %d", len(eye_points)
            )
            return -1.0

        pts = np.asarray(eye_points, dtype=np.float64)

        p1, p2, p3, p4, p5, p6 = pts

        vertical_a = np.linalg.norm(p2 - p6)
        vertical_b = np.linalg.norm(p3 - p5)
        horizontal = np.linalg.norm(p1 - p4)

        if horizontal < 1e-6:
            logger.debug("Horizontal eye distance near zero, returning -1.0")
            return -1.0

        ear = (vertical_a + vertical_b) / (2.0 * horizontal)
        return float(ear)

    def update(
        self,
        face_landmarks: Optional[object] = None,
        face_box: Optional[List[float]] = None,
    ) -> DrowsinessResult:
        """Analyse one frame and return a :class:`DrowsinessResult`.

        Accepts either mediapipe face-mesh landmarks (preferred) or a
        ``keypoints`` attribute from the YOLOv8 detector output.

        Args:
            face_landmarks: One of the following:
                * A mediapipe ``NormalizedLandmarkList`` / ``LandmarkList``
                  (468 points).
                * An object with a ``keypoints`` attribute containing a list
                  of 5 ``(x, y)`` points (YOLOv8 output dict).
                * ``None`` — the call is a no-op returning a normal result.
            face_box: Optional ``[x1, y1, x2, y2]`` bounding box (reserved
                for future region-of-interest filtering).

        Returns:
            A :class:`DrowsinessResult` describing the drowsiness state.
        """
        ear_value = -1.0

        # --- Try mediapipe full mesh first ---
        ear_value = self._try_mediapipe_ear(face_landmarks)

        # --- Fallback: YOLOv8 5-keypoint approximation ---
        if ear_value < 0.0:
            ear_value = self._try_yolo_ear(face_landmarks)

        # --- No usable data ---
        if ear_value < 0.0:
            return DrowsinessResult(
                is_drowsy=False,
                ear_value=-1.0,
                blink_rate=0.0,
                alert_level="normal",
                consecutive_drowsy_frames=self._consecutive_drowsy_frames,
            )

        # --- Update state ---
        is_frame_drowsy = ear_value < self.ear_threshold

        if is_frame_drowsy:
            self._consecutive_drowsy_frames += 1
        else:
            self._consecutive_drowsy_frames = 0

        is_drowsy = self._consecutive_drowsy_frames >= self.consecutive_frames
        alert_level = self._classify_alert_level(
            ear_value, self._consecutive_drowsy_frames
        )

        # --- Blink tracking ---
        self._update_blink_tracking(ear_value)
        blink_rate = self._compute_blink_rate()

        return DrowsinessResult(
            is_drowsy=is_drowsy,
            ear_value=ear_value,
            blink_rate=blink_rate,
            alert_level=alert_level,
            consecutive_drowsy_frames=self._consecutive_drowsy_frames,
        )

    def should_alert(self, result: DrowsinessResult) -> bool:
        """Decide whether an alert should be raised for *result*.

        Returns ``True`` only when the result indicates drowsiness **and**
        the cooldown period has elapsed since the last alert.

        Args:
            result: A :class:`DrowsinessResult` from :meth:`update`.
        """
        if not result.is_drowsy:
            return False

        now = time.time()
        if (now - self._last_alert_time) < self.alert_cooldown:
            return False

        self._last_alert_time = now
        return True

    def reset(self) -> None:
        """Reset all internal state to initial values."""
        self._consecutive_drowsy_frames = 0
        self._last_alert_time = 0.0
        self._eyes_were_closed = False
        self._blink_times.clear()
        self._ear_history.clear()
        logger.debug("DrowsinessDetector state reset")

    # ------------------------------------------------------------------
    # Private helpers — mediapipe
    # ------------------------------------------------------------------

    def _try_mediapipe_ear(self, face_landmarks: Optional[object]) -> float:
        """Attempt to compute EAR from mediapipe 468-point landmarks.

        Returns ``-1.0`` if mediapipe is unavailable or *face_landmarks*
        does not contain mediapipe data.
        """
        if not self._try_load_mediapipe():
            return -1.0

        try:
            import mediapipe as mp  # type: ignore

            # Accept NormalizedLandmarkList or plain iterable
            lm = face_landmarks
            if hasattr(lm, "landmark"):
                lm = lm.landmark

            left_pts = self._extract_eye_points(lm, LEFT_EYE)
            right_pts = self._extract_eye_points(lm, RIGHT_EYE)

            if left_pts is None or right_pts is None:
                return -1.0

            left_ear = self.compute_ear(left_pts)
            right_ear = self.compute_ear(right_pts)

            if left_ear < 0.0 or right_ear < 0.0:
                return -1.0

            return (left_ear + right_ear) / 2.0

        except Exception as exc:
            logger.debug("mediapipe EAR extraction failed: %s", exc)
            return -1.0

    def _try_load_mediapipe(self) -> bool:
        """Lazily import mediapipe; cache the import result."""
        if self._mp_face_mesh_loaded:
            return self._mp_face_mesh is not None

        self._mp_face_mesh_loaded = True
        try:
            import mediapipe as mp  # type: ignore

            self._mp_face_mesh = mp
            return True
        except ImportError:
            self._mp_face_mesh = None
            return False

    @staticmethod
    def _extract_eye_points(
        landmarks: object, indices: List[int]
    ) -> Optional[List[Tuple[float, float]]]:
        """Pull out ``(x, y)`` pairs for the given landmark *indices*.

        Handles both mediapipe ``Landmark`` proto (has ``.x``, ``.y``) and
        plain ``(x, y)`` iterables.
        """
        try:
            points: List[Tuple[float, float]] = []
            for idx in indices:
                lm = landmarks[idx]
                if hasattr(lm, "x") and hasattr(lm, "y"):
                    points.append((float(lm.x), float(lm.y)))
                else:
                    # Assume (x, y) sequence
                    points.append((float(lm[0]), float(lm[1])))
            return points
        except (IndexError, TypeError, AttributeError) as exc:
            logger.debug("Failed to extract eye points: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Private helpers — YOLOv8 keypoints
    # ------------------------------------------------------------------

    def _estimate_ear_from_yolo_keypoints(
        self, keypoints: list
    ) -> float:
        """Estimate EAR from YOLOv8-face 5 keypoints.

        The YOLOv8-face model typically outputs 5 keypoints in the
        following order::

            0: left_eye
            1: right_eye
            2: nose_tip
            3: left_mouth_corner
            4: right_mouth_corner

        Because five points are insufficient for a true EAR calculation,
        this method uses the vertical distance from eye to nose relative
        to inter-eye distance as a proxy.  The result is mapped to an
        approximate EAR range [0, 0.4].

        Args:
            keypoints: List of 5 ``(x, y)`` points.

        Returns:
            Estimated EAR value, or ``-1.0`` on failure.
        """
        if keypoints is None or len(keypoints) < 5:
            return -1.0

        try:
            left_eye = np.asarray(keypoints[0][:2], dtype=np.float64)
            right_eye = np.asarray(keypoints[1][:2], dtype=np.float64)
            nose = np.asarray(keypoints[2][:2], dtype=np.float64)

            inter_eye_dist = np.linalg.norm(left_eye - right_eye)
            if inter_eye_dist < 1e-6:
                return -1.0

            left_eye_nose = np.linalg.norm(left_eye - nose)
            right_eye_nose = np.linalg.norm(right_eye - nose)
            avg_vert = (left_eye_nose + right_eye_nose) / 2.0

            # Normalize and map to approximate EAR range.
            # Typical ratio when eyes are open: ~0.6-0.8
            # When eyes are closed:           ~0.3-0.5
            ratio = avg_vert / inter_eye_dist

            # Linear map: ratio 0.3 -> EAR ~0.0, ratio 0.8 -> EAR ~0.35
            estimated_ear = max(0.0, min(0.4, (ratio - 0.3) * 0.7))

            return float(estimated_ear)

        except (IndexError, TypeError, ValueError) as exc:
            logger.debug("YOLOv8 EAR estimation failed: %s", exc)
            return -1.0

    def _try_yolo_ear(self, face_landmarks: Optional[object]) -> float:
        """Attempt to compute EAR from YOLOv8 keypoints attached to *face_landmarks*.

        Accepts either:
        * A dict with a ``'keypoints'`` key (as produced by
          :class:`~boss_sentinel.detector.FaceDetector`).
        * Any object with a ``keypoints`` attribute.
        """
        keypoints = None

        if isinstance(face_landmarks, dict):
            keypoints = face_landmarks.get("keypoints")
        elif face_landmarks is not None and hasattr(face_landmarks, "keypoints"):
            keypoints = face_landmarks.keypoints

        if keypoints is None:
            return -1.0

        return self._estimate_ear_from_yolo_keypoints(keypoints)

    # ------------------------------------------------------------------
    # Private helpers — blink tracking
    # ------------------------------------------------------------------

    def _update_blink_tracking(self, ear_value: float) -> None:
        """Record a single-frame EAR and detect blink transitions."""
        # Maintain bounded history
        self._ear_history.append(ear_value)
        if len(self._ear_history) > self._ear_history_max:
            self._ear_history = self._ear_history[-self._ear_history_max :]

        # Detect blink: closed -> open transition
        is_closed = ear_value < self.ear_threshold
        if self._eyes_were_closed and not is_closed:
            self._blink_times.append(time.time())
        self._eyes_were_closed = is_closed

    def _compute_blink_rate(self) -> float:
        """Estimate blinks per minute from recent blink timestamps."""
        now = time.time()
        window = 60.0  # 1-minute sliding window
        self._blink_times = [t for t in self._blink_times if now - t < window]
        return float(len(self._blink_times))

    # ------------------------------------------------------------------
    # Private helpers — alert classification
    # ------------------------------------------------------------------

    def _classify_alert_level(
        self, ear_value: float, consecutive_drowsy: int
    ) -> str:
        """Map EAR value and consecutive-drowsy count to an alert level.

        Returns one of ``"normal"``, ``"drowsy"``, or ``"critical"``.
        """
        if consecutive_drowsy >= self.consecutive_frames * 2:
            return "critical"
        if consecutive_drowsy >= self.consecutive_frames:
            return "drowsy"
        if consecutive_drowsy >= max(1, self.consecutive_frames // 2):
            return "drowsy"
        return "normal"
