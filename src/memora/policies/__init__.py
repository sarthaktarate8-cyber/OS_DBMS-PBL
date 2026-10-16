"""Buffer replacement policy implementations for MEMORA."""

from __future__ import annotations

from memora.policies.base import ReplacementPolicy
from memora.policies.clock import ClockPolicy
from memora.policies.fifo import FIFOPolicy
from memora.policies.lfu import LFUPolicy
from memora.policies.lru import LRUPolicy

__all__ = [
    "ReplacementPolicy",
    "LRUPolicy",
    "LFUPolicy",
    "FIFOPolicy",
    "ClockPolicy",
]
