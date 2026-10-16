"""Buffer pool implementation for MEMORA.

The BufferPool manages a fixed collection of BufferFrame slots, tracks page
presence via a page table, coordinates with a ReplacementPolicy for evictions,
and emits events to a MetricsCollector.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from memora.core.frame import BufferFrame
from memora.core.types import AccessRecord, EvictionRecord, Operation
from memora.policies.base import ReplacementPolicy

if TYPE_CHECKING:
    from memora.metrics.collector import MetricsCollector

__all__ = ["BufferPool"]

logger = logging.getLogger(__name__)


class BufferPool:
    """Fixed-size database buffer pool with pluggable replacement policy.

    Attributes:
        size: Total number of frames in the buffer pool.
        policy: Current active ReplacementPolicy.
        metrics: MetricsCollector instance recording hits, misses, evictions.
    """

    def __init__(
        self,
        size: int,
        policy: ReplacementPolicy,
        metrics: Optional[MetricsCollector] = None,
    ) -> None:
        """Initialize the buffer pool.

        Args:
            size: Number of frames (must be positive).
            policy: Replacement policy to manage evictions.
            metrics: Optional metrics collector.
        """
        if size <= 0:
            raise ValueError(f"Buffer pool size must be positive, got {size}")

        self._size = size
        self._policy = policy
        self._metrics = metrics

        self._frames: list[BufferFrame] = [
            BufferFrame(frame_id=i) for i in range(size)
        ]
        self._page_table: dict[int, int] = {}  # page_id -> frame_id
        self._free_frames: list[int] = list(reversed(range(size)))  # frame IDs free
        self._access_counter: int = 0
        self._eviction_history: list[EvictionRecord] = []

    @property
    def size(self) -> int:
        """Total capacity of the buffer pool."""
        return self._size

    @property
    def policy(self) -> ReplacementPolicy:
        """Currently active replacement policy."""
        return self._policy

    @property
    def metrics(self) -> Optional[MetricsCollector]:
        """MetricsCollector attached to this buffer pool."""
        return self._metrics

    @property
    def access_counter(self) -> int:
        """Number of accesses processed so far."""
        return self._access_counter

    @property
    def occupancy(self) -> int:
        """Number of currently occupied frames."""
        return len(self._page_table)

    @property
    def free_count(self) -> int:
        """Number of unallocated frames."""
        return len(self._free_frames)

    @property
    def is_full(self) -> bool:
        """True if all frames are occupied."""
        return len(self._page_table) >= self._size

    def contains(self, page_id: int) -> bool:
        """Return True if page is resident in the buffer pool."""
        return page_id in self._page_table

    def get_frame(self, page_id: int) -> Optional[BufferFrame]:
        """Return the BufferFrame holding page_id, or None if not resident."""
        frame_id = self._page_table.get(page_id)
        if frame_id is not None:
            return self._frames[frame_id]
        return None

    def get_frame_by_id(self, frame_id: int) -> BufferFrame:
        """Return frame by physical frame index."""
        return self._frames[frame_id]

    def resident_pages(self) -> list[int]:
        """Return list of all resident page IDs."""
        return list(self._page_table.keys())

    def access(self, record: AccessRecord) -> bool:
        """Process a page access request.

        Args:
            record: The AccessRecord detailing page_id, operation, etc.

        Returns:
            True if access was a HIT, False if a MISS.
        """
        self._access_counter += 1
        page_id = record.page_id
        is_write = record.operation == Operation.WRITE

        if self._metrics is not None:
            self._metrics.record_access()

        # Check for HIT
        if page_id in self._page_table:
            frame_id = self._page_table[page_id]
            frame = self._frames[frame_id]
            frame.touch(record.timestamp, is_write=is_write)
            self._policy.access(page_id, self._access_counter)

            if self._metrics is not None:
                self._metrics.record_hit()
            return True

        # Handle MISS
        if self._metrics is not None:
            self._metrics.record_miss()

        frame_id = self._allocate_frame(new_page_id=page_id)
        frame = self._frames[frame_id]
        frame.load(
            page_id=page_id,
            timestamp=record.timestamp,
            access_counter=self._access_counter,
            is_write=is_write,
        )
        self._page_table[page_id] = frame_id
        self._policy.insert(page_id, self._access_counter)
        return False

    def _allocate_frame(self, new_page_id: int) -> int:
        """Find an empty frame or evict a victim to make room.

        Returns:
            Physical frame ID ready for loading.
        """
        # Case 1: Free frame available
        if self._free_frames:
            return self._free_frames.pop()

        # Case 2: Must evict a page
        skipped_pinned: list[int] = []
        victim_page_id = self._policy.evict()
        while (
            victim_page_id is not None
            and victim_page_id in self._page_table
            and self._frames[self._page_table[victim_page_id]].is_pinned
        ):
            skipped_pinned.append(victim_page_id)
            victim_page_id = self._policy.evict()

        # Re-insert skipped pinned pages into policy tracking so they aren't lost
        for p in skipped_pinned:
            frame_p = self._frames[self._page_table[p]]
            self._policy.insert(p, frame_p.last_access)
            if hasattr(self._policy, "_page_freq") and frame_p.frequency > 1:
                for _ in range(frame_p.frequency - 1):
                    self._policy.access(p, frame_p.last_access)

        if victim_page_id is None or victim_page_id not in self._page_table:
            # Fallback: evict first unpinned frame
            unpinned = [p for p, fid in self._page_table.items() if not self._frames[fid].is_pinned]
            if not unpinned:
                raise RuntimeError("Buffer pool full: all resident pages are pinned")
            victim_page_id = unpinned[0]
            self._policy.remove(victim_page_id)

        victim_frame_id = self._page_table.pop(victim_page_id)
        victim_frame = self._frames[victim_frame_id]
        was_dirty = victim_frame.dirty_bit

        eviction_record = EvictionRecord(
            evicted_page_id=victim_page_id,
            new_page_id=new_page_id,
            was_dirty=was_dirty,
            policy=self._policy.name,
            timestamp=self._access_counter,
        )
        self._eviction_history.append(eviction_record)

        if self._metrics is not None:
            self._metrics.record_eviction(was_dirty=was_dirty)

        victim_frame.clear()
        return victim_frame_id

    def set_policy(self, new_policy: ReplacementPolicy, strategy: str = "hard") -> None:
        """Switch the active replacement policy.

        Args:
            new_policy: The replacement policy to transition to.
            strategy: 'hard' (immediate state transfer) or 'warm' / 'soft'.
        """
        if new_policy.name == self._policy.name:
            return

        logger.info(
            "Switching policy from %s to %s (strategy=%s)",
            self._policy.name,
            new_policy.name,
            strategy,
        )

        new_policy.reset()
        # Transfer resident pages into the new policy metadata
        if strategy in ("hard", "soft"):
            # Insert resident pages ordered by load time or last access
            sorted_pages = sorted(
                self._page_table.keys(),
                key=lambda p: self._frames[self._page_table[p]].last_access,
            )
            for p in sorted_pages:
                frame = self._frames[self._page_table[p]]
                new_policy.insert(p, frame.load_time)
                # If target is LFU, simulate recorded frequency
                if hasattr(new_policy, "_page_freq") and frame.frequency > 1:
                    for _ in range(frame.frequency - 1):
                        new_policy.access(p, frame.last_access)
                elif hasattr(new_policy, "_max_usage_count") and frame.frequency > 1:
                    extra = min(frame.frequency - 1, getattr(new_policy, "_max_usage_count") - 1)
                    for _ in range(extra):
                        new_policy.access(p, frame.last_access)

        self._policy = new_policy
        if self._metrics is not None:
            self._metrics.set_policy_name(new_policy.name)

    def flush(self) -> int:
        """Flush all dirty pages, returning number of flushed pages."""
        flushed = 0
        for frame in self._frames:
            if not frame.is_empty and frame.dirty_bit:
                frame.dirty_bit = False
                flushed += 1
                if self._metrics is not None:
                    self._metrics.record_eviction(was_dirty=True)
        return flushed

    def clear(self) -> None:
        """Reset the buffer pool to empty."""
        for frame in self._frames:
            frame.clear()
        self._page_table.clear()
        self._free_frames = list(reversed(range(self._size)))
        self._policy.reset()
        self._access_counter = 0
        self._eviction_history.clear()
