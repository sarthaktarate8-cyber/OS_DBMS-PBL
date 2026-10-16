"""PostgreSQL-style Generalized Clock-Sweep buffer replacement policy.

Implements the generalized CLOCK replacement algorithm utilized by PostgreSQL's
buffer manager (freelist.c / bufmgr.c).

In PostgreSQL:
- Pages reside in a circular buffer ring.
- Each buffer header maintains a usage counter (usagecount) in [0, BM_MAX_USAGE_COUNT].
- On page hit (access), the usage count is incremented up to a maximum (default 5).
- On initial page load (insert), the usage count is initialized to 1.
- On eviction, a clock hand sweeps across the ring:
  * If usagecount > 0, it is decremented by 1, and the hand advances.
  * If usagecount == 0, the page is selected as the eviction victim.
"""

from __future__ import annotations

import logging
from typing import Optional

from memora.policies.base import ReplacementPolicy

__all__ = ["ClockPolicy"]

logger = logging.getLogger(__name__)


class _ClockNode:
    """Internal node in circular doubly linked clock sweep list."""

    __slots__ = ("page_id", "usage_count", "prev", "next")

    def __init__(self, page_id: int, usage_count: int = 1) -> None:
        self.page_id = page_id
        self.usage_count = usage_count
        self.prev: _ClockNode = self
        self.next: _ClockNode = self


class ClockPolicy(ReplacementPolicy):
    """Generalized Clock-Sweep replacement policy matching PostgreSQL's buffer engine.

    Attributes:
        max_usage_count: Maximum usage counter cap (PostgreSQL default is 5).
    """

    DEFAULT_MAX_USAGE_COUNT = 5

    def __init__(self, max_usage_count: int = DEFAULT_MAX_USAGE_COUNT) -> None:
        """Initialize the Clock replacement policy.

        Args:
            max_usage_count: Maximum usage counter (default 5 for PostgreSQL,
                             1 for standard second-chance FIFO).
        """
        if max_usage_count < 1:
            raise ValueError(f"max_usage_count must be >= 1, got {max_usage_count}")
        self._max_usage_count = max_usage_count
        self._nodes: dict[int, _ClockNode] = {}
        self._hand: Optional[_ClockNode] = None

    @property
    def max_usage_count(self) -> int:
        """Maximum usage count cap."""
        return self._max_usage_count

    @property
    def name(self) -> str:
        """Canonical name."""
        return "clock"

    def access(self, page_id: int, timestamp: int) -> None:
        """Increment page usage counter up to max_usage_count (PostgreSQL hit behavior).

        If page is not yet tracked, it is inserted with usage_count=1.
        """
        node = self._nodes.get(page_id)
        if node is not None:
            if node.usage_count < self._max_usage_count:
                node.usage_count += 1
        else:
            self.insert(page_id, timestamp)

    def insert(self, page_id: int, timestamp: int) -> None:
        """Insert a newly loaded page into the clock ring with usage_count=1."""
        if page_id in self._nodes:
            # Already in ring, simply increment usage count
            node = self._nodes[page_id]
            if node.usage_count < self._max_usage_count:
                node.usage_count += 1
            return

        node = _ClockNode(page_id=page_id, usage_count=1)
        self._nodes[page_id] = node

        if self._hand is None:
            node.next = node
            node.prev = node
            self._hand = node
        else:
            # Insert right before current hand (at tail of ring)
            prev_node = self._hand.prev
            prev_node.next = node
            node.prev = prev_node
            node.next = self._hand
            self._hand.prev = node

    def evict(self) -> Optional[int]:
        """Sweep clock hand to find and evict the next victim with usage_count == 0.

        Decrements usage counters of encountered pages until a victim is located.

        Returns:
            Evicted page ID, or None if buffer is empty.
        """
        if not self._nodes or self._hand is None:
            return None

        # Sweep until a page with usage_count == 0 is encountered
        curr = self._hand
        while True:
            if curr.usage_count > 0:
                curr.usage_count -= 1
                curr = curr.next
            else:
                # Found victim
                victim_id = curr.page_id
                self._advance_and_remove(curr)
                return victim_id

    def _advance_and_remove(self, target: _ClockNode) -> None:
        """Unlink target node and advance clock hand."""
        del self._nodes[target.page_id]

        if not self._nodes:
            self._hand = None
            return

        # Advance hand to target.next
        next_hand = target.next
        target.prev.next = target.next
        target.next.prev = target.prev

        if self._hand is target:
            self._hand = next_hand

    def remove(self, page_id: int) -> None:
        """Remove a specific page from clock sweep tracking."""
        node = self._nodes.get(page_id)
        if node is not None:
            self._advance_and_remove(node)

    def contains(self, page_id: int) -> bool:
        """Check if page is currently tracked."""
        return page_id in self._nodes

    def size(self) -> int:
        """Total pages in clock ring."""
        return len(self._nodes)

    def reset(self) -> None:
        """Clear all tracking state."""
        self._nodes.clear()
        self._hand = None

    def get_usage_count(self, page_id: int) -> Optional[int]:
        """Diagnostic helper to inspect usage counter for a page."""
        node = self._nodes.get(page_id)
        return node.usage_count if node is not None else None
