"""Abstract base class for all buffer replacement policies.

All policies follow a uniform interface so that the buffer pool and
adaptive controller can treat them interchangeably.

Design note:
    Policies operate on page IDs only. They do NOT access or modify
    BufferFrame objects directly. Frame management is the buffer pool's
    responsibility. This maintains strict separation of concerns.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

__all__ = ["ReplacementPolicy"]


class ReplacementPolicy(ABC):
    """Abstract interface for buffer replacement policies.

    A policy tracks which pages are in the buffer and decides which
    page to evict when the buffer is full and a new page must be loaded.

    IMPORTANT: Policies track ONLY the metadata needed for their
    replacement decision (e.g., access order for LRU). They do NOT
    duplicate frame data or buffer pool state.
    """

    @abstractmethod
    def access(self, page_id: int, timestamp: int) -> None:
        """Notify the policy that ``page_id`` was accessed.

        Called on both hits and misses (after insertion on a miss).

        Args:
            page_id: The page that was accessed.
            timestamp: The current logical access counter.
        """

    @abstractmethod
    def insert(self, page_id: int, timestamp: int) -> None:
        """Record a new page being loaded into the buffer.

        Called exactly once per page load, before or alongside ``access``.

        Args:
            page_id: The page being inserted.
            timestamp: The current logical access counter.
        """

    @abstractmethod
    def evict(self) -> Optional[int]:
        """Select and remove the victim page according to this policy's rules.

        Returns:
            The page ID of the victim page, or None if the policy tracks no pages.
        """

    @abstractmethod
    def remove(self, page_id: int) -> None:
        """Explicitly remove a page from policy tracking without normal eviction.

        Used when a page is invalidated or moved out of the buffer pool.

        Args:
            page_id: The page to remove.
        """

    @abstractmethod
    def contains(self, page_id: int) -> bool:
        """Return True if ``page_id`` is currently tracked by this policy."""

    @abstractmethod
    def size(self) -> int:
        """Return the number of pages currently tracked by this policy."""

    @abstractmethod
    def reset(self) -> None:
        """Reset all internal state to empty."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return canonical lowercase string name of the policy (e.g. 'lru')."""
