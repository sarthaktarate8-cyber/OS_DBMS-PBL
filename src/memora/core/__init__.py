"""Core data structures and buffer pool implementation for MEMORA."""

from __future__ import annotations

from memora.core.buffer_pool import BufferPool
from memora.core.frame import BufferFrame
from memora.core.types import (
    AccessRecord,
    EvictionRecord,
    Operation,
    PhaseChangeEvent,
    PolicyName,
    SwitchEvent,
)

__all__ = [
    "BufferPool",
    "BufferFrame",
    "AccessRecord",
    "EvictionRecord",
    "Operation",
    "PolicyName",
    "SwitchEvent",
    "PhaseChangeEvent",
]
