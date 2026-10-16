"""Shared data types for MEMORA.

All types are immutable dataclasses or enums. No business logic lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

__all__ = [
    "Operation",
    "PolicyName",
    "AccessRecord",
    "EvictionRecord",
    "SwitchEvent",
    "PhaseChangeEvent",
]


class Operation(Enum):
    """Type of a page access."""
    READ = auto()
    WRITE = auto()

    def __str__(self) -> str:
        return self.name


class PolicyName(Enum):
    """Canonical names for replacement policies."""
    LRU = "lru"
    LFU = "lfu"
    FIFO = "fifo"
    MEMORA = "memora"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class AccessRecord:
    """A single page access event.

    Attributes:
        page_id: Logical page identifier (non-negative integer).
        timestamp: Logical or wall-clock timestamp.
        operation: READ or WRITE.
        query_id: Optional identifier of the originating query.
    """
    page_id: int
    timestamp: int = 0
    operation: Operation = Operation.READ
    query_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.page_id < 0:
            raise ValueError(f"page_id must be non-negative, got {self.page_id}")


@dataclass(frozen=True)
class EvictionRecord:
    """Records a single frame eviction event.

    Attributes:
        evicted_page_id: Page that was evicted.
        new_page_id: Page that was loaded in its place.
        was_dirty: Whether the evicted page had to be written to disk.
        policy: Policy that made the eviction decision.
        timestamp: Access count at eviction time.
    """
    evicted_page_id: int
    new_page_id: int
    was_dirty: bool
    policy: str
    timestamp: int


@dataclass(frozen=True)
class SwitchEvent:
    """Records an adaptive policy switch decision (switch OR retain)."""
    timestamp: int
    previous_policy: str
    new_policy: str
    estimated_benefit: float
    estimated_cost: float
    net_benefit: float
    triggered_by: str
    accepted: bool
    reason: str = ""


@dataclass(frozen=True)
class PhaseChangeEvent:
    """Records a detected phase transition in the workload stream."""
    timestamp: int
    detected_phase: str
    confidence: float
    jsd_frequency: float
    entropy_delta: float
    sequentiality_delta: float
    window_index: int = 0
