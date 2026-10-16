"""Least Frequently Used (LFU) buffer replacement policy with LRU tie-breaking.

Evicts the page with the lowest access frequency.
When multiple pages share the lowest frequency, evicts the least-recently
used page among them (Assumption A1).

Implemented in O(1) time per operation using frequency buckets of OrderedDicts.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from memora.policies.base import ReplacementPolicy

__all__ = ["LFUPolicy"]


class LFUPolicy(ReplacementPolicy):
    """O(1) LFU replacement policy with deterministic LRU tie-breaking.

    Structure:
        _page_freq: dict[page_id -> frequency]
        _freq_buckets: dict[freq -> OrderedDict[page_id, None]]
        _min_freq: int tracking the lowest frequency with at least one page
    """

    def __init__(self) -> None:
        """Initialize an empty LFU policy tracker."""
        self._page_freq: dict[int, int] = {}
        self._freq_buckets: dict[int, OrderedDict[int, None]] = {}
        self._min_freq: int = 0

    def access(self, page_id: int, timestamp: int) -> None:
        """Increment access frequency and update recency within the new frequency bucket."""
        if page_id not in self._page_freq:
            self.insert(page_id, timestamp)
            return

        freq = self._page_freq[page_id]
        # Remove from current bucket
        del self._freq_buckets[freq][page_id]
        if not self._freq_buckets[freq]:
            del self._freq_buckets[freq]
            if self._min_freq == freq:
                self._min_freq = freq + 1

        new_freq = freq + 1
        self._page_freq[page_id] = new_freq
        if new_freq not in self._freq_buckets:
            self._freq_buckets[new_freq] = OrderedDict()
        self._freq_buckets[new_freq][page_id] = None

    def insert(self, page_id: int, timestamp: int) -> None:
        """Insert a newly loaded page with frequency 1."""
        if page_id in self._page_freq:
            self.access(page_id, timestamp)
            return

        self._page_freq[page_id] = 1
        if 1 not in self._freq_buckets:
            self._freq_buckets[1] = OrderedDict()
        self._freq_buckets[1][page_id] = None
        self._min_freq = 1

    def evict(self) -> Optional[int]:
        """Evict the page with minimum frequency, breaking ties with LRU.

        Returns:
            The evicted page_id, or None if empty.
        """
        if not self._page_freq:
            return None

        bucket = self._freq_buckets.get(self._min_freq)
        if not bucket:
           
            self._min_freq = min(self._freq_buckets.keys())
            bucket = self._freq_buckets[self._min_freq]

        victim_id, _ = bucket.popitem(last=False)
        if not bucket:
            del self._freq_buckets[self._min_freq]
            if self._freq_buckets:
                self._min_freq = min(self._freq_buckets.keys())
            else:
                self._min_freq = 0

        del self._page_freq[victim_id]
        return victim_id

    def remove(self, page_id: int) -> None:
        """Remove a page from LFU tracking."""
        if page_id not in self._page_freq:
            return

        freq = self._page_freq.pop(page_id)
        bucket = self._freq_buckets.get(freq)
        if bucket and page_id in bucket:
            del bucket[page_id]
            if not bucket:
                del self._freq_buckets[freq]
                if self._min_freq == freq:
                    if self._freq_buckets:
                        self._min_freq = min(self._freq_buckets.keys())
                    else:
                        self._min_freq = 0

    def get_frequency(self, page_id: int) -> int:
        """Return the current frequency of a page, or 0 if not tracked."""
        return self._page_freq.get(page_id, 0)

    def contains(self, page_id: int) -> bool:
        """Return True if page is currently tracked."""
        return page_id in self._page_freq

    def size(self) -> int:
        """Return number of tracked pages."""
        return len(self._page_freq)

    def reset(self) -> None:
        """Reset internal state."""
        self._page_freq.clear()
        self._freq_buckets.clear()
        self._min_freq = 0

    @property
    def name(self) -> str:
        """Canonical policy name."""
        return "lfu"
