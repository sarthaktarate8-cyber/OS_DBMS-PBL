"""First-In-First-Out (FIFO) buffer replacement policy.

Evicts the page that was inserted earliest into the buffer pool,
regardless of subsequent accesses.
Implemented in O(1) time using collections.OrderedDict.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from memora.policies.base import ReplacementPolicy

__all__ = ["FIFOPolicy"]


class FIFOPolicy(ReplacementPolicy):
    """First-In-First-Out replacement policy.

    Maintains insertion order. Subsequent accesses do NOT change eviction priority.
    """

    def __init__(self) -> None:
        """Initialize an empty FIFO policy tracker."""
        self._queue: OrderedDict[int, int] = OrderedDict()

    def access(self, page_id: int, timestamp: int) -> None:
        """Record an access.

        In FIFO, accessing an already-buffered page does NOT change its position.
        If the page is not yet in the queue, it is inserted at the tail.
        """
        if page_id not in self._queue:
            self._queue[page_id] = timestamp

    def insert(self, page_id: int, timestamp: int) -> None:
        """Insert a newly loaded page at the tail of the FIFO queue."""
        if page_id not in self._queue:
            self._queue[page_id] = timestamp

    def evict(self) -> Optional[int]:
        """Evict the earliest-inserted page (head of queue).

        Returns:
            The evicted page_id, or None if empty.
        """
        if not self._queue:
            return None
        victim_id, _ = self._queue.popitem(last=False)
        return victim_id

    def peek_fifo(self) -> Optional[int]:
        """Inspect the next FIFO eviction candidate without removing it."""
        if not self._queue:
            return None
        return next(iter(self._queue))

    def remove(self, page_id: int) -> None:
        """Remove a page from FIFO tracking."""
        self._queue.pop(page_id, None)

    def contains(self, page_id: int) -> bool:
        """Return True if page is currently tracked."""
        return page_id in self._queue

    def size(self) -> int:
        """Return number of tracked pages."""
        return len(self._queue)

    def reset(self) -> None:
        """Reset internal state."""
        self._queue.clear()

    @property
    def name(self) -> str:
        """Canonical policy name."""
        return "fifo"
