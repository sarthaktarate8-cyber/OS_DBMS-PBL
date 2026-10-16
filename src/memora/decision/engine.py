"""Cost-Benefit Decision Engine for MEMORA.

Evaluates whether transitioning to a different replacement policy will yield
a net performance benefit over the current policy, taking into account
the cold-miss switching penalties and minimum net-benefit gates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from memora.decision.cost_model import SwitchCostModel
from memora.detector.profile import WorkloadProfile

__all__ = ["CostBenefitEngine", "SwitchDecision", "EngineConfig"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SwitchDecision:
    """Outcome of a cost-benefit policy transition evaluation.

    Attributes:
        timestamp: Logical access timestamp at decision time.
        current_policy: Currently running policy.
        recommended_policy: Best candidate policy.
        should_switch: True if recommended != current AND net_benefit >= minimum_net_benefit.
        estimated_benefit: Projected hit-ratio increase.
        estimated_cost: Projected switching penalty.
        net_benefit: (benefit_weight * benefit) - (cost_weight * cost).
        detected_phase: Phase label triggering the evaluation.
        reason: Human-readable justification.
    """

    timestamp: int
    current_policy: str
    recommended_policy: str
    should_switch: bool
    estimated_benefit: float
    estimated_cost: float
    net_benefit: float
    detected_phase: str
    reason: str


@dataclass
class EngineConfig:
    """Parameters controlling the decision engine."""
    minimum_net_benefit: float = 0.020
    benefit_weight: float = 1.0
    cost_weight: float = 1.0
    candidate_policies: Sequence[str] = ("lru", "lfu", "fifo")
    heuristic_benefits: Optional[dict[str, float]] = None


class CostBenefitEngine:
    """Evaluates candidate replacement policies and gates transitions."""

    def __init__(
        self,
        cost_model: Optional[SwitchCostModel] = None,
        config: Optional[EngineConfig] = None,
    ) -> None:
        """Initialize the decision engine.

        Args:
            cost_model: SwitchCostModel instance.
            config: EngineConfig options.
        """
        self._cost_model = cost_model or SwitchCostModel()
        self._cfg = config or EngineConfig()

        default_heuristics = {
            "recency_to_lru": 0.05,
            "recency_to_lfu": -0.03,
            "recency_to_fifo": -0.08,
            "frequency_to_lfu": 0.06,
            "frequency_to_lru": -0.01,
            "frequency_to_fifo": -0.05,
            "sequential_to_fifo": 0.04,
            "sequential_to_lru": -0.02,
            "sequential_to_lfu": -0.04,
            "random_to_lru": 0.00,
            "random_to_lfu": -0.01,
            "random_to_fifo": -0.02,
        }
        self._heuristics = self._cfg.heuristic_benefits or default_heuristics

    def estimate_benefit(self, phase: str, candidate_policy: str) -> float:
        """Estimate the hit-ratio gain of using candidate_policy for phase."""
        key = f"{phase.lower()}_to_{candidate_policy.lower()}"
        return self._heuristics.get(key, 0.0)

    def evaluate(
        self,
        current_policy: str,
        detected_phase: str,
        profile: WorkloadProfile,
        buffer_size: int,
        access_counter: int,
        window_size: int = 1000,
    ) -> SwitchDecision:
        """Evaluate candidate replacement policies and decide whether to switch.

        Args:
            current_policy: Name of the currently active policy.
            detected_phase: Classified phase name.
            profile: Profile of the recent workload window.
            buffer_size: Size of the buffer pool in frames.
            access_counter: Current total access counter.
            window_size: Window length.

        Returns:
            SwitchDecision specifying recommended policy, net benefit, and decision.
        """
        curr = current_policy.lower()
        candidates = list(self._cfg.candidate_policies)

        # Baseline: staying with current policy has cost 0 and benefit relative to itself 0
        best_policy = curr
        best_benefit = 0.0
        best_cost = 0.0
        best_net = 0.0

        current_phase_affinity = self.estimate_benefit(detected_phase, curr)

        for candidate in candidates:
            cand = candidate.lower()
            if cand == curr:
                continue

            # Projected benefit relative to current policy's affinity
            cand_affinity = self.estimate_benefit(detected_phase, cand)
            benefit = max(0.0, cand_affinity - current_phase_affinity)

            cost = self._cost_model.compute_cost(
                current_policy=curr,
                target_policy=cand,
                buffer_size=buffer_size,
                window_size=window_size,
            )

            net = (self._cfg.benefit_weight * benefit) - (self._cfg.cost_weight * cost)

            if net > best_net:
                best_net = net
                best_policy = cand
                best_benefit = benefit
                best_cost = cost

        should_switch = (
            best_policy != curr
            and best_net >= self._cfg.minimum_net_benefit
        )

        if should_switch:
            reason = (
                f"Switch accepted: {curr} -> {best_policy} for {detected_phase} phase. "
                f"Net benefit {best_net:.4f} >= threshold {self._cfg.minimum_net_benefit:.4f} "
                f"(benefit={best_benefit:.4f}, cost={best_cost:.4f})"
            )
            logger.info(reason)
        elif best_policy != curr:
            reason = (
                f"Switch rejected: {curr} -> {best_policy} net benefit {best_net:.4f} "
                f"below minimum threshold {self._cfg.minimum_net_benefit:.4f}"
            )
            logger.debug(reason)
        else:
            reason = f"Retained {curr}: current policy already optimal for {detected_phase} phase"
            logger.debug(reason)

        return SwitchDecision(
            timestamp=access_counter,
            current_policy=curr,
            recommended_policy=best_policy if should_switch else curr,
            should_switch=should_switch,
            estimated_benefit=round(best_benefit, 4),
            estimated_cost=round(best_cost, 4),
            net_benefit=round(best_net, 4),
            detected_phase=detected_phase,
            reason=reason,
        )
