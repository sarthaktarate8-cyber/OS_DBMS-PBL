"""Policy creation factory and state migration strategies for MEMORA."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from memora.core.buffer_pool import BufferPool
from memora.policies.base import ReplacementPolicy
from memora.policies.clock import ClockPolicy
from memora.policies.fifo import FIFOPolicy
from memora.policies.lfu import LFUPolicy
from memora.policies.lru import LRUPolicy

__all__ = [
    "create_policy",
    "SwitchStrategy",
    "HardSwitchStrategy",
    "SoftSwitchStrategy",
]

logger = logging.getLogger(__name__)


def create_policy(name: str) -> ReplacementPolicy:
    """Instantiate a clean replacement policy by canonical name."""
    clean_name = name.strip().lower()
    if clean_name == "lru":
        return LRUPolicy()
    elif clean_name == "lfu":
        return LFUPolicy()
    elif clean_name == "fifo":
        return FIFOPolicy()
    elif clean_name == "clock":
        return ClockPolicy()
    else:
        raise ValueError(f"Unknown replacement policy name: '{name}'")


class SwitchStrategy(ABC):
    """Abstract strategy for migrating buffer pool state to a new replacement policy."""

    @abstractmethod
    def execute(
        self,
        pool: BufferPool,
        target_policy_name: str,
    ) -> ReplacementPolicy:
        """Perform policy transition and return the active policy instance."""


class HardSwitchStrategy(SwitchStrategy):
    """Immediate policy replacement with deterministic metadata migration.

    Transfers all currently resident pages into the new policy metadata structures,
    ordered by their existing recency and frequencies.
    """

    def execute(
        self,
        pool: BufferPool,
        target_policy_name: str,
    ) -> ReplacementPolicy:
        new_policy = create_policy(target_policy_name)
        pool.set_policy(new_policy, strategy="hard")
        return new_policy


class SoftSwitchStrategy(SwitchStrategy):
    """Warm policy transition preserving frame metadata."""

    def execute(
        self,
        pool: BufferPool,
        target_policy_name: str,
    ) -> ReplacementPolicy:
        new_policy = create_policy(target_policy_name)
        pool.set_policy(new_policy, strategy="soft")
        return new_policy
