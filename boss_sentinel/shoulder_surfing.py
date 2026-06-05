"""Shoulder surfing detection for Boss Sentinel.

Analyzes recognized faces in a frame to determine whether the screen
content is vulnerable to unauthorized onlookers (shoulder surfers).
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ShoulderSurfResult:
    """Result of a shoulder-surfing vulnerability check.

    Attributes:
        is_vulnerable: ``True`` when at least one unauthorized face is
            detected alongside the screen user.
        total_faces: Total number of faces found in the frame.
        authorized_count: Number of faces belonging to authorized
            individuals.
        unauthorized_count: Number of faces that are either unknown or
            belong to explicitly unauthorized persons.
        privacy_level: A float between 0.0 (all faces authorized — safe)
            and 1.0 (all faces unauthorized — maximum danger).
    """

    is_vulnerable: bool
    total_faces: int
    authorized_count: int
    unauthorized_count: int
    privacy_level: float = field(default=0.0)


class ShoulderSurfingDetector:
    """Detect shoulder-surfing situations by comparing recognized faces
    against a set of authorized person names.

    The detector receives a list of face identities (as returned by the
    face-recognition pipeline) for each processed frame and classifies
    every face as *authorized* or *unauthorized*.  An unrecognised face
    (``None`` or an empty string) is always treated as unauthorized.

    Example::

        detector = ShoulderSurfingDetector(authorized_names=["alice", "bob"])
        result = detector.check_frame(["alice", None])
        # result.is_vulnerable == True  (unknown face present)
    """

    def __init__(self, authorized_names: Optional[List[str]] = None) -> None:
        """Initialise the detector.

        Args:
            authorized_names: A list of names that are considered
                authorized.  Name comparison is case-insensitive.
                Defaults to an empty list (everyone is unauthorized).
        """
        names = authorized_names or []
        self._authorized: Set[str] = {n.lower() for n in names if n}
        logger.info(
            "ShoulderSurfingDetector initialised with %d authorized name(s)",
            len(self._authorized),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_frame(self, face_names: List[Optional[str]]) -> ShoulderSurfResult:
        """Evaluate a single frame for shoulder-surfing risk.

        Args:
            face_names: A list where each element is either the
                recognised person's name or ``None`` / empty string for
                an unrecognised face.

        Returns:
            A :class:`ShoulderSurfResult` describing the vulnerability
            state.
        """
        total_faces = len(face_names)
        authorized_count = 0
        unauthorized_count = 0

        for name in face_names:
            if name and name.lower() in self._authorized:
                authorized_count += 1
            else:
                unauthorized_count += 1

        # privacy_level: 0.0 when all authorized, 1.0 when all unauthorized
        if total_faces == 0:
            privacy_level = 0.0
        else:
            privacy_level = unauthorized_count / total_faces

        is_vulnerable = unauthorized_count > 0

        result = ShoulderSurfResult(
            is_vulnerable=is_vulnerable,
            total_faces=total_faces,
            authorized_count=authorized_count,
            unauthorized_count=unauthorized_count,
            privacy_level=round(privacy_level, 4),
        )

        if is_vulnerable:
            logger.warning(
                "Shoulder surfing detected: %d unauthorized / %d total "
                "(privacy_level=%.2f)",
                unauthorized_count,
                total_faces,
                privacy_level,
            )

        return result

    def update_authorized(self, names: List[str]) -> None:
        """Replace the current set of authorized names.

        Args:
            names: New list of authorized person names.  Comparison is
                case-insensitive.
        """
        self._authorized = {n.lower() for n in names if n}
        logger.info(
            "Authorized names updated: %d name(s) — %s",
            len(self._authorized),
            ", ".join(sorted(self._authorized)) if self._authorized else "(none)",
        )
