"""Least Recently Used (LRU) buffer replacement policy.

Evicts the page that has not been accessed for the longest time.
Implemented in O(1) time per operation using collections.OrderedDict.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from memora.policies.base import ReplacementPolicy

__all__ = ["LRUPolicy"]


class LRUPolicy(ReplacementPolicy):
    """O(1) Least Recently Used buffer replacement policy.

    Maintains access ordering in an OrderedDict where:
    - The head (first item) is the Least Recently Used page.
    - The tail (last item) is the Most Recently Used page.
    """

    def __init__(self) -> None:
        """Initialize an empty LRU policy tracker."""
        self._order: OrderedDict[int, int] = OrderedDict()

    def access(self, page_id: int, timestamp: int) -> None:
        """Move page to the MRU position (tail of OrderedDict).

        If the page is not yet present, it is added.
        """
        self._order[page_id] = timestamp
        self._order.move_to_end(page_id)

    def insert(self, page_id: int, timestamp: int) -> None:
        """Insert a newly loaded page at the MRU position."""
        self._order[page_id] = timestamp
        self._order.move_to_end(page_id)

    def evict(self) -> Optional[int]:
        """Evict the LRU page (head of OrderedDict).

        Returns:
            The victim page_id, or None if the tracker is empty.
        """
        if not self._order:
            return None
        victim_id, _ = self._order.popitem(last=False)
        return victim_id

    def peek_lru(self) -> Optional[int]:
        """Inspect the current LRU candidate without evicting it."""
        if not self._order:
            return None
        return next(iter(self._order))

    def remove(self, page_id: int) -> None:
        """Remove page from LRU tracking."""
        self._order.pop(page_id, None)

    def contains(self, page_id: int) -> bool:
        """Return True if page is currently tracked."""
        return page_id in self._order

    def size(self) -> int:
        """Return number of tracked pages."""
        return len(self._order)

    def reset(self) -> None:
        """Reset internal state."""
        self._order.clear()

    @property
    def name(self) -> str:
        """Canonical policy name."""
        return "lru"
