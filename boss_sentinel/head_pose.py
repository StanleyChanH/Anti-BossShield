"""Head Pose Estimation for Boss Sentinel.

Uses OpenCV solvePnP with YOLOv8 5 facial keypoints to estimate head
orientation (yaw, pitch, roll).  Works reliably with just 5 keypoints
because the spatial relationships between eyes, nose, and mouth corners
constrain the head orientation in 3D space.

Applications:
    - Owner attention tracking (focus score, distraction alerts)
    - Boss approach detection (head-on orientation + proximity)
    - Shoulder surfing confirmation (stranger looking at screen)

Keypoint order from YOLOv8-face:
    0: left_eye
    1: right_eye
    2: nose_tip
    3: left_mouth_corner
    4: right_mouth_corner
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Standard 3D face model (approximate metric positions in mm)
# ---------------------------------------------------------------------------
# Coordinate system: X=right, Y=down, Z=forward (OpenCV convention)
_FACE_MODEL_3D = np.array([
    [-30.0, -30.0,  0.0],   # 0: left eye
    [ 30.0, -30.0,  0.0],   # 1: right eye
    [  0.0,   0.0, 30.0],   # 2: nose tip (forward)
    [-25.0,  40.0,  0.0],   # 3: left mouth corner
    [ 25.0,  40.0,  0.0],   # 4: right mouth corner
], dtype=np.float64)


@dataclass
class HeadPoseResult:
    """Result of head pose estimation for one face.

    Attributes:
        yaw:   Left-right head rotation in degrees. Positive = turning right.
        pitch: Up-down head tilt in degrees. Positive = tilting down.
        roll:  Side tilt in degrees. Positive = tilting right.
        looking_at_screen: True when head is roughly facing the camera.
        attention_status: One of "focused", "distracted", "away".
        confidence: Estimation quality (0.0-1.0). Lower when keypoints
            are noisy or partially occluded.
    """

    yaw: float
    pitch: float
    roll: float
    looking_at_screen: bool
    attention_status: str
    confidence: float


class HeadPoseEstimator:
    """Estimate head pose from YOLOv8 5-keypoint detections.

    Uses cv2.solvePnP to compute the rotation vector from a standard
    3D face model and the detected 2D keypoints, then converts to
    Euler angles (yaw, pitch, roll).

    Args:
        yaw_threshold: Degrees of yaw beyond which the person is
            considered not looking at the screen. Default 30.
        pitch_threshold: Same for pitch. Default 25.
        focus_window_seconds: How many seconds of history to consider
            for focus/attention scoring. Default 60.
    """

    def __init__(
        self,
        yaw_threshold: float = 30.0,
        pitch_threshold: float = 25.0,
        focus_window_seconds: float = 60.0,
    ) -> None:
        self.yaw_threshold = yaw_threshold
        self.pitch_threshold = pitch_threshold
        self.focus_window_seconds = focus_window_seconds

        # Per-face attention history: face_index -> deque of (timestamp, looking_at_screen)
        self._attention_history: dict = {}

        # Cache camera matrix (will be set on first call based on frame size)
        self._camera_matrix: Optional[np.ndarray] = None
        self._dist_coeffs = np.zeros((4, 1), dtype=np.float64)

    def estimate(
        self,
        keypoints: list,
        frame_shape: Tuple[int, int, int],
        face_index: int = 0,
    ) -> Optional[HeadPoseResult]:
        """Estimate head pose from 5 facial keypoints.

        Args:
            keypoints: List of 5 (x, y) or (x, y, confidence) keypoints
                from YOLOv8-face detection.
            frame_shape: (height, width, channels) of the frame.
            face_index: Index to track attention history per face.

        Returns:
            A HeadPoseResult, or None if estimation fails.
        """
        if keypoints is None or len(keypoints) < 5:
            return None

        try:
            # Extract 2D image points
            image_points = np.array([
                [float(keypoints[i][0]), float(keypoints[i][1])]
                for i in range(5)
            ], dtype=np.float64)

            # Check for invalid points (all zeros or NaN)
            if np.any(np.isnan(image_points)) or np.all(image_points == 0):
                return None

            # Build camera matrix from frame dimensions
            h, w = frame_shape[:2]
            if self._camera_matrix is None or self._camera_matrix[0, 2] != w / 2:
                self._camera_matrix = np.array([
                    [w,   0, w / 2],
                    [0,   h, h / 2],
                    [0,   0,   1  ],
                ], dtype=np.float64)

            # Solve for pose
            success, rvec, tvec = cv2.solvePnP(
                _FACE_MODEL_3D,
                image_points,
                self._camera_matrix,
                self._dist_coeffs,
                flags=cv2.SOLVEPNP_EPNP,
            )

            if not success:
                return None

            # Convert rotation vector to Euler angles
            yaw, pitch, roll = self._rotation_to_euler(rvec)

            # Determine if looking at screen
            looking = (abs(yaw) < self.yaw_threshold and
                       abs(pitch) < self.pitch_threshold)

            # Update attention history
            now = time.time()
            if face_index not in self._attention_history:
                self._attention_history[face_index] = deque(maxlen=1800)
            history = self._attention_history[face_index]
            history.append((now, looking))

            # Compute attention status from recent history
            attention_status = self._compute_attention(history, now)

            # Confidence based on reprojection quality (simplified)
            confidence = self._estimate_confidence(rvec, tvec, image_points)

            return HeadPoseResult(
                yaw=round(yaw, 1),
                pitch=round(pitch, 1),
                roll=round(roll, 1),
                looking_at_screen=looking,
                attention_status=attention_status,
                confidence=round(confidence, 3),
            )

        except (cv2.error, IndexError, TypeError, ValueError) as exc:
            logger.debug("Head pose estimation failed: %s", exc)
            return None

    def get_focus_score(self, face_index: int = 0) -> float:
        """Compute a focus score (0.0 - 1.0) for a tracked face.

        The score is the fraction of recent frames where the person
        was looking at the screen.

        Returns:
            Focus score between 0.0 (never looking) and 1.0 (always looking).
        """
        history = self._attention_history.get(face_index)
        if not history:
            return 0.0

        now = time.time()
        cutoff = now - self.focus_window_seconds
        recent = [(t, looking) for t, looking in history if t >= cutoff]

        if not recent:
            return 0.0

        return sum(1 for _, looking in recent if looking) / len(recent)

    def reset(self) -> None:
        """Clear all attention history."""
        self._attention_history.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rotation_to_euler(rvec: np.ndarray) -> Tuple[float, float, float]:
        """Convert a rotation vector to Euler angles (yaw, pitch, roll) in degrees.

        Uses the ZYX convention consistent with head pose literature.
        """
        R, _ = cv2.Rodrigues(rvec)

        # Yaw (Y-axis rotation)
        yaw = np.degrees(np.arctan2(R[1, 0], R[0, 0]))

        # Pitch (X-axis rotation)
        sy = -R[2, 0]
        sy = np.clip(sy, -1.0, 1.0)
        pitch = np.degrees(np.arcsin(sy))

        # Roll (Z-axis rotation)
        roll = np.degrees(np.arctan2(R[2, 1], R[2, 2]))

        return float(yaw), float(pitch), float(roll)

    @staticmethod
    def _estimate_confidence(
        rvec: np.ndarray,
        tvec: np.ndarray,
        image_points: np.ndarray,
    ) -> float:
        """Estimate pose quality from translation vector magnitude.

        Returns a value between 0.0 and 1.0.  Extremely large or small
        translations suggest poor estimation.
        """
        tz = abs(tvec[2, 0])
        # Reasonable range: 100mm to 2000mm from camera
        if tz < 50:
            return 0.3
        if tz > 3000:
            return 0.3
        # Peak confidence around 300-800mm
        if 200 < tz < 1000:
            return 0.9
        return 0.6

    def _compute_attention(
        self,
        history: deque,
        now: float,
    ) -> str:
        """Classify attention status from recent looking-at-screen history.

        Returns one of:
            - "focused": Mostly looking at screen
            - "distracted": Looking away frequently
            - "away": Consistently not looking at screen
        """
        cutoff = now - self.focus_window_seconds
        recent = [(t, looking) for t, looking in history if t >= cutoff]

        if len(recent) < 5:
            return "focused"  # Not enough data, assume present

        look_ratio = sum(1 for _, looking in recent if looking) / len(recent)

        if look_ratio >= 0.7:
            return "focused"
        elif look_ratio >= 0.3:
            return "distracted"
        else:
            return "away"
