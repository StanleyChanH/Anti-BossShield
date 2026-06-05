"""Pomodoro Timer with presence detection for Boss Sentinel.

Tracks focus sessions, breaks, and daily productivity statistics.
Automatically pauses when the user is absent and resumes on return.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PomodoroState(Enum):
    """Possible states of the Pomodoro timer."""

    IDLE = "idle"
    FOCUS = "focus"
    SHORT_BREAK = "short_break"
    LONG_BREAK = "long_break"


@dataclass
class PomodoroStatus:
    """Snapshot of the current Pomodoro timer state.

    Attributes:
        state: Current timer state.
        elapsed_seconds: Seconds elapsed in the current phase.
        remaining_seconds: Seconds remaining in the current phase.
        completed_pomodoros: Number of focus sessions completed today.
        focus_ratio: Fraction of the day's tracked time spent in focus.
    """

    state: PomodoroState
    elapsed_seconds: float
    remaining_seconds: float
    completed_pomodoros: int
    focus_ratio: float


class PomodoroTimer:
    """Pomodoro timer that responds to user presence.

    The timer starts or resumes a focus session when the user is detected
    as present, and pauses when the user is absent.  Daily statistics are
    persisted to disk so they survive application restarts.

    Args:
        focus_minutes: Length of a focus session in minutes.
        break_minutes: Length of a short break in minutes.
        long_break_minutes: Length of a long break in minutes.
        target_pomodoros: Number of focus sessions before a long break.
    """

    _DATA_DIR = Path.home() / ".boss_sentinel_pomodoro"

    def __init__(
        self,
        focus_minutes: int = 25,
        break_minutes: int = 5,
        long_break_minutes: int = 15,
        target_pomodoros: int = 8,
    ) -> None:
        self.focus_minutes = focus_minutes
        self.break_minutes = break_minutes
        self.long_break_minutes = long_break_minutes
        self.target_pomodoros = target_pomodoros

        # Runtime state
        self._state: PomodoroState = PomodoroState.IDLE
        self._phase_start: Optional[datetime] = None
        self._accumulated_seconds: float = 0.0
        self._is_paused: bool = False
        self._pause_start: Optional[datetime] = None
        self._total_pause_seconds: float = 0.0

        # Daily accumulators (loaded from / saved to disk)
        self._completed_pomodoros: int = 0
        self._total_focus_seconds: float = 0.0
        self._total_break_seconds: float = 0.0
        self._data_date: Optional[date] = None

        self._load_daily_data()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_user_present(self) -> None:
        """Start or resume the focus timer when the user is present.

        * If the timer is **IDLE**, a new focus session begins.
        * If the timer is **paused** (user was absent), the session resumes.
        * If the timer is already running, this is a no-op.
        """
        if self._state == PomodoroState.IDLE:
            self._start_phase(PomodoroState.FOCUS)
            logger.info("Pomodoro: focus session started (%d min)", self.focus_minutes)
            return

        if self._is_paused:
            self._resume()
            logger.info("Pomodoro: timer resumed in state %s", self._state.value)

    def on_user_absent(self) -> None:
        """Pause the timer when the user is absent.

        Pausing records how much time was already spent in the current
        phase so it can be restored on resume.
        """
        if self._state == PomodoroState.IDLE or self._is_paused:
            return

        self._pause()
        logger.info("Pomodoro: timer paused in state %s", self._state.value)

    def get_status(self) -> PomodoroStatus:
        """Return a snapshot of the current timer state.

        Returns:
            A :class:`PomodoroStatus` dataclass.
        """
        if self._state == PomodoroState.IDLE:
            return PomodoroStatus(
                state=PomodoroState.IDLE,
                elapsed_seconds=0.0,
                remaining_seconds=0.0,
                completed_pomodoros=self._completed_pomodoros,
                focus_ratio=self._compute_focus_ratio(),
            )

        elapsed = self._elapsed_seconds()
        duration = self._current_phase_duration()
        remaining = max(0.0, duration - elapsed)

        return PomodoroStatus(
            state=self._state,
            elapsed_seconds=elapsed,
            remaining_seconds=remaining,
            completed_pomodoros=self._completed_pomodoros,
            focus_ratio=self._compute_focus_ratio(),
        )

    def get_daily_report(self) -> Dict[str, Any]:
        """Return a summary of today's Pomodoro activity.

        Returns:
            A dictionary with keys ``total_focus_time``,
            ``total_break_time``, ``pomodoros_completed``, and
            ``focus_ratio``.
        """
        return {
            "total_focus_time": str(timedelta(seconds=int(self._total_focus_seconds))),
            "total_break_time": str(timedelta(seconds=int(self._total_break_seconds))),
            "pomodoros_completed": self._completed_pomodoros,
            "focus_ratio": round(self._compute_focus_ratio(), 4),
            "date": str(self._data_date or date.today()),
        }

    def reset(self) -> None:
        """Reset the timer to IDLE without affecting daily statistics."""
        self._state = PomodoroState.IDLE
        self._phase_start = None
        self._accumulated_seconds = 0.0
        self._is_paused = False
        self._pause_start = None
        self._total_pause_seconds = 0.0
        logger.info("Pomodoro: timer reset to IDLE")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _start_phase(self, state: PomodoroState) -> None:
        """Begin a new timer phase."""
        self._state = state
        self._phase_start = datetime.now()
        self._accumulated_seconds = 0.0
        self._is_paused = False
        self._pause_start = None
        self._total_pause_seconds = 0.0

    def _pause(self) -> None:
        """Pause the current phase, saving elapsed progress."""
        if self._phase_start is None:
            return
        self._accumulated_seconds = self._elapsed_seconds()
        self._is_paused = True
        self._pause_start = datetime.now()

    def _resume(self) -> None:
        """Resume a paused phase."""
        if not self._is_paused or self._pause_start is None:
            return
        # Account for the time spent paused
        pause_duration = (datetime.now() - self._pause_start).total_seconds()
        self._total_pause_seconds += pause_duration
        self._is_paused = False
        self._pause_start = None
        # Reset phase_start so elapsed is computed from "now" with accumulated offset
        self._phase_start = datetime.now()

    def _elapsed_seconds(self) -> float:
        """Compute total elapsed seconds in the current phase."""
        if self._phase_start is None:
            return self._accumulated_seconds

        if self._is_paused:
            return self._accumulated_seconds

        live_elapsed = (datetime.now() - self._phase_start).total_seconds()
        return self._accumulated_seconds + live_elapsed

    def _current_phase_duration(self) -> float:
        """Return the total duration (in seconds) of the current phase."""
        if self._state == PomodoroState.FOCUS:
            return self.focus_minutes * 60.0
        elif self._state == PomodoroState.SHORT_BREAK:
            return self.break_minutes * 60.0
        elif self._state == PomodoroState.LONG_BREAK:
            return self.long_break_minutes * 60.0
        return 0.0

    def _compute_focus_ratio(self) -> float:
        """Compute the ratio of focus time to total tracked time."""
        total = self._total_focus_seconds + self._total_break_seconds
        if total == 0:
            return 0.0
        return self._total_focus_seconds / total

    def _check_phase_completion(self) -> None:
        """Transition to the next phase if the current one is complete."""
        if self._state == PomodoroState.IDLE:
            return

        elapsed = self._elapsed_seconds()
        duration = self._current_phase_duration()

        if elapsed < duration:
            return

        # Record time spent in the completed phase
        phase_seconds = duration
        if self._state == PomodoroState.FOCUS:
            self._total_focus_seconds += phase_seconds
            self._completed_pomodoros += 1
            logger.info(
                "Pomodoro: focus session #%d completed",
                self._completed_pomodoros,
            )
            # Decide break type
            if self._completed_pomodoros % self.target_pomodoros == 0:
                self._start_phase(PomodoroState.LONG_BREAK)
                logger.info("Pomodoro: long break started (%d min)", self.long_break_minutes)
            else:
                self._start_phase(PomodoroState.SHORT_BREAK)
                logger.info("Pomodoro: short break started (%d min)", self.break_minutes)
        else:
            self._total_break_seconds += phase_seconds
            self._start_phase(PomodoroState.FOCUS)
            logger.info("Pomodoro: focus session started (%d min)", self.focus_minutes)

        self._save_daily_data()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _data_file_path(self) -> Path:
        """Return the path to today's data file."""
        today_str = date.today().isoformat()
        return self._DATA_DIR / f"pomodoro_{today_str}.json"

    def _save_daily_data(self) -> None:
        """Persist today's statistics to a JSON file."""
        try:
            self._DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "date": date.today().isoformat(),
                "completed_pomodoros": self._completed_pomodoros,
                "total_focus_seconds": self._total_focus_seconds,
                "total_break_seconds": self._total_break_seconds,
            }
            path = self._data_file_path()
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
            logger.debug("Pomodoro: daily data saved to %s", path)
        except Exception as exc:
            logger.error("Pomodoro: failed to save daily data: %s", exc)

    def _load_daily_data(self) -> None:
        """Load today's statistics from disk.

        If no data file exists for today (or the file is corrupt),
        counters start from zero.
        """
        today = date.today()
        path = self._data_file_path()

        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
                self._data_date = date.fromisoformat(payload["date"])
                self._completed_pomodoros = int(payload.get("completed_pomodoros", 0))
                self._total_focus_seconds = float(payload.get("total_focus_seconds", 0.0))
                self._total_break_seconds = float(payload.get("total_break_seconds", 0.0))
                logger.info(
                    "Pomodoro: loaded daily data for %s (%d pomodoros)",
                    self._data_date,
                    self._completed_pomodoros,
                )
                return
            except Exception as exc:
                logger.warning("Pomodoro: failed to load daily data: %s", exc)

        # Fresh start
        self._data_date = today
        self._completed_pomodoros = 0
        self._total_focus_seconds = 0.0
        self._total_break_seconds = 0.0
