"""Sliding window manager for streaming workload analysis."""

from __future__ import annotations

from collections import deque
from typing import Optional

from memora.core.types import AccessRecord

__all__ = ["SlidingWindowManager"]


class SlidingWindowManager:
    """Maintains a rolling window of recent AccessRecord events.

    Args:
        window_size: Number of records in each observation window.
        step_size: Number of accesses between consecutive window evaluations.
        overlap: If True, windows advance by step_size (< window_size).
                 If False, step_size is set equal to window_size (disjoint).
    """

    def __init__(
        self,
        window_size: int = 1000,
        step_size: int = 250,
        overlap: bool = True,
    ) -> None:
        if window_size <= 0:
            raise ValueError(f"window_size must be positive, got {window_size}")
        if step_size <= 0:
            raise ValueError(f"step_size must be positive, got {step_size}")

        self._window_size = window_size
        self._step_size = step_size if overlap else window_size
        self._overlap = overlap

        self._buffer: deque[AccessRecord] = deque(maxlen=window_size)
        self._total_added = 0
        self._windows_emitted = 0

    @property
    def window_size(self) -> int:
        """Configured size of the observation window."""
        return self._window_size

    @property
    def step_size(self) -> int:
        """Step stride between evaluations."""
        return self._step_size

    @property
    def total_records(self) -> int:
        """Total records ingested since last reset."""
        return self._total_added

    @property
    def windows_emitted(self) -> int:
        """Total full windows yielded so far."""
        return self._windows_emitted

    def add_record(self, record: AccessRecord) -> Optional[list[AccessRecord]]:
        """Ingest one AccessRecord.

        Returns:
            A snapshot list of ``window_size`` records if a step boundary
            was reached, or None otherwise.
        """
        self._buffer.append(record)
        self._total_added += 1

        if len(self._buffer) == self._window_size:
            # Check if this addition aligns with step_size
            offset = self._total_added - self._window_size
            if offset % self._step_size == 0:
                self._windows_emitted += 1
                return list(self._buffer)

        return None

    def reset(self) -> None:
        """Reset internal buffer and counters."""
        self._buffer.clear()
        self._total_added = 0
        self._windows_emitted = 0
