"""Buffer frame abstraction for MEMORA.

A BufferFrame represents one slot in the buffer pool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = ["BufferFrame"]


@dataclass
class BufferFrame:
    """A single buffer frame in the buffer pool.

    Attributes:
        frame_id: Unique identifier of this physical frame (0-indexed).
        page_id: Logical page currently occupying this frame. None = empty.
        dirty_bit: True if the page has been modified and not yet flushed to disk.
        pin_count: Number of active users holding this frame (pinned frames cannot be evicted).
        last_access: Logical timestamp of the most recent access.
        frequency: Number of times this page has been accessed since load.
        load_time: Logical timestamp when this page was loaded into this frame.
        access_count_on_load: Total-access counter value at load time.
    """

    frame_id: int
    page_id: Optional[int] = None
    dirty_bit: bool = False
    pin_count: int = 0
    last_access: int = 0
    frequency: int = 0
    load_time: int = 0
    access_count_on_load: int = 0

    @property
    def is_empty(self) -> bool:
        """True if no page is loaded in this frame."""
        return self.page_id is None

    @property
    def is_pinned(self) -> bool:
        """True if this frame is pinned and cannot be evicted."""
        return self.pin_count > 0

    def pin(self) -> None:
        """Increment the pin count."""
        self.pin_count += 1

    def unpin(self) -> None:
        """Decrement the pin count. Raises RuntimeError if already 0."""
        if self.pin_count <= 0:
            raise RuntimeError(
                f"Frame {self.frame_id}: attempted to unpin an already-unpinned frame"
            )
        self.pin_count -= 1

    def mark_dirty(self) -> None:
        """Mark the frame as containing unwritten modifications."""
        self.dirty_bit = True

    def clear(self) -> None:
        """Reset the frame to empty state after eviction."""
        self.page_id = None
        self.dirty_bit = False
        self.pin_count = 0
        self.last_access = 0
        self.frequency = 0
        self.load_time = 0
        self.access_count_on_load = 0

    def load(
        self,
        page_id: int,
        timestamp: int,
        access_counter: int = 0,
        is_write: bool = False,
    ) -> None:
        """Load a new page into this frame.

        Args:
            page_id: Page identifier to load.
            timestamp: Access timestamp.
            access_counter: Overall access counter value.
            is_write: Whether this initial access is a write operation.
        """
        self.page_id = page_id
        self.dirty_bit = is_write
        self.pin_count = 0
        self.last_access = timestamp
        self.frequency = 1
        self.load_time = timestamp
        self.access_count_on_load = access_counter

    def touch(self, timestamp: int, is_write: bool = False) -> None:
        """Update frame statistics upon a buffer hit.

        Args:
            timestamp: Logical access timestamp.
            is_write: Whether this access is a write operation.
        """
        self.last_access = timestamp
        self.frequency += 1
        if is_write:
            self.dirty_bit = True
