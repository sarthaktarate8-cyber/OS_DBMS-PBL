"""Analytical Cost Model for policy switching in MEMORA.

Models the transient performance penalties of transitioning between buffer
replacement policies:
1. Cold-miss penalty from uncalibrated policy metadata
2. State transfer / initialization overhead
3. Fixed dispatch & synchronization overhead

All parameters represent explicitly documented model assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = ["SwitchCostModel", "CostModelConfig"]


@dataclass
class CostModelConfig:
    """Configuration parameters for the switching cost model."""
    cold_miss_fraction: float = 0.30
    init_overhead_fraction: float = 0.02
    switch_overhead_fixed: float = 0.005


class SwitchCostModel:
    """Computes expected transition cost for switching replacement policies."""

    def __init__(self, config: Optional[CostModelConfig] = None) -> None:
        """Initialize the cost model."""
        self._cfg = config or CostModelConfig()

    @property
    def config(self) -> CostModelConfig:
        """Active configuration."""
        return self._cfg

    def compute_cost(
        self,
        current_policy: str,
        target_policy: str,
        buffer_size: int,
        window_size: int = 1000,
    ) -> float:
        """Compute estimated switching penalty as a hit-ratio deduction.

        Args:
            current_policy: Currently active policy name (e.g., 'lru').
            target_policy: Candidate policy name (e.g., 'lfu').
            buffer_size: Total buffer pool size in frames.
            window_size: Number of accesses in the decision window.

        Returns:
            Normalized cost value in [0.0, 1.0], representing anticipated
            transient hit-ratio drop over the subsequent window.
        """
        if current_policy.lower() == target_policy.lower():
            return 0.0

        # Effective ratio of buffer size to observation window
        buffer_ratio = min(1.0, float(buffer_size) / max(1, window_size))

        # 1. Cold-miss penalty from imperfect metadata calibration
        cold_penalty = self._cfg.cold_miss_fraction * buffer_ratio * 0.1

        # 2. Re-initialization & state rebuild overhead
        init_penalty = self._cfg.init_overhead_fraction * buffer_ratio

        # 3. Fixed overhead (dispatch, locking, hook invocation)
        fixed_penalty = self._cfg.switch_overhead_fixed

        total_cost = cold_penalty + init_penalty + fixed_penalty
        return round(float(total_cost), 6)
