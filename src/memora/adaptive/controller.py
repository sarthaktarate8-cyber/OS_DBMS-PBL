"""Adaptive Buffer Manager controller for MEMORA.

Coordinates between the buffer pool, workload phase detector, and cost-benefit
engine, enforcing anti-thrashing rules (cooldown, residence periods, hysteresis).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from memora.adaptive.strategies import HardSwitchStrategy, SoftSwitchStrategy, SwitchStrategy
from memora.core.buffer_pool import BufferPool
from memora.core.types import AccessRecord, PhaseChangeEvent, SwitchEvent
from memora.decision.engine import CostBenefitEngine, SwitchDecision
from memora.detector.phase_detector import PhaseDetectionResult, PhaseDetector
from memora.metrics.collector import MetricsCollector, SimulationMetrics

__all__ = ["AdaptiveBufferManager", "AdaptiveConfig"]

logger = logging.getLogger(__name__)


@dataclass
class AdaptiveConfig:
    """Anti-thrashing and adaptation parameters."""
    cooldown_accesses: int = 5000
    min_residence_accesses: int = 2000
    hysteresis_factor: float = 0.05
    switch_strategy: str = "hard"


class AdaptiveBufferManager:
    """Intelligent adaptive buffer pool manager."""

    def __init__(
        self,
        buffer_pool: BufferPool,
        detector: PhaseDetector,
        decision_engine: CostBenefitEngine,
        metrics: Optional[MetricsCollector] = None,
        config: Optional[AdaptiveConfig] = None,
    ) -> None:
        """Initialize the Adaptive Buffer Manager."""
        self._pool = buffer_pool
        self._detector = detector
        self._engine = decision_engine
        self._cfg = config or AdaptiveConfig()

        self._metrics = metrics or buffer_pool._metrics or MetricsCollector(
            policy_name="memora"
        )
        self._pool._metrics = self._metrics
        self._metrics.set_policy_name("memora")

        self._strategy: SwitchStrategy = (
            HardSwitchStrategy()
            if self._cfg.switch_strategy == "hard"
            else SoftSwitchStrategy()
        )

        self._last_switch_access: int = 0
        self._previous_policy_name: str = buffer_pool.policy.name
        self._switch_history: list[SwitchEvent] = []
        self._phase_history: list[PhaseChangeEvent] = []

    @property
    def buffer_pool(self) -> BufferPool:
        """Underlying BufferPool instance."""
        return self._pool

    @property
    def current_policy_name(self) -> str:
        """Name of the currently active replacement policy."""
        return self._pool.policy.name

    @property
    def switch_history(self) -> list[SwitchEvent]:
        """All recorded policy switch decisions."""
        return list(self._switch_history)

    @property
    def phase_history(self) -> list[PhaseChangeEvent]:
        """All detected workload phase changes."""
        return list(self._phase_history)

    def access(self, record: AccessRecord) -> bool:
        """Process one page access, checking phase detection and anti-thrashing gates.

        Args:
            record: Page access event.

        Returns:
            True on buffer hit, False on miss.
        """
        # 1. Feed into phase detector
        detection: Optional[PhaseDetectionResult] = self._detector.feed_record(record)

        if detection is not None and detection.is_phase_change:
            phase_evt = PhaseChangeEvent(
                timestamp=self._pool.access_counter,
                detected_phase=detection.detected_phase,
                confidence=detection.confidence,
                jsd_frequency=detection.jsd,
                entropy_delta=detection.entropy_delta,
                sequentiality_delta=detection.sequentiality_delta,
                window_index=self._detector.windows_analyzed,
            )
            self._phase_history.append(phase_evt)

            # 2. Check Anti-Thrashing Guardrails
            accesses_since_last_switch = self._pool.access_counter - self._last_switch_access
            if accesses_since_last_switch < self._cfg.cooldown_accesses:
                logger.debug(
                    "Switch suppressed: in cooldown (%d / %d accesses since last switch)",
                    accesses_since_last_switch,
                    self._cfg.cooldown_accesses,
                )
                self._record_rejection(
                    decision=None,
                    phase=detection.detected_phase,
                    reason=f"Cooldown active ({accesses_since_last_switch}/{self._cfg.cooldown_accesses} accesses)",
                )
            else:
                # 3. Evaluate Cost-Benefit
                decision: SwitchDecision = self._engine.evaluate(
                    current_policy=self._pool.policy.name,
                    detected_phase=detection.detected_phase,
                    profile=detection.current_profile or self._detector._previous_profile,  # type: ignore
                    buffer_size=self._pool.size,
                    access_counter=self._pool.access_counter,
                    window_size=self._detector._window_mgr.window_size,
                )

                if decision.should_switch:
                    self._execute_switch(decision)
                else:
                    self._record_rejection(
                        decision=decision,
                        phase=detection.detected_phase,
                        reason=decision.reason,
                    )

        # 4. Delegate access to buffer pool
        return self._pool.access(record)

    def _execute_switch(self, decision: SwitchDecision) -> None:
        """Perform policy transition and record events."""
        old_policy = self._pool.policy.name
        target_policy = decision.recommended_policy

        self._strategy.execute(self._pool, target_policy)
        self._last_switch_access = self._pool.access_counter
        self._previous_policy_name = old_policy

        evt = SwitchEvent(
            timestamp=self._pool.access_counter,
            previous_policy=old_policy,
            new_policy=target_policy,
            estimated_benefit=decision.estimated_benefit,
            estimated_cost=decision.estimated_cost,
            net_benefit=decision.net_benefit,
            triggered_by=decision.detected_phase,
            accepted=True,
            reason=decision.reason,
        )
        self._switch_history.append(evt)
        self._metrics.record_switch(evt)

        logger.info(
            "Adaptive switch executed: %s -> %s at access %d (net benefit=%.4f)",
            old_policy,
            target_policy,
            self._pool.access_counter,
            decision.net_benefit,
        )

    def _record_rejection(
        self,
        decision: Optional[SwitchDecision],
        phase: str,
        reason: str,
    ) -> None:
        """Record an evaluated but rejected switch event."""
        evt = SwitchEvent(
            timestamp=self._pool.access_counter,
            previous_policy=self._pool.policy.name,
            new_policy=decision.recommended_policy if decision else self._pool.policy.name,
            estimated_benefit=decision.estimated_benefit if decision else 0.0,
            estimated_cost=decision.estimated_cost if decision else 0.0,
            net_benefit=decision.net_benefit if decision else 0.0,
            triggered_by=phase,
            accepted=False,
            reason=reason,
        )
        self._switch_history.append(evt)

    def snapshot(self) -> SimulationMetrics:
        """Retrieve metrics snapshot with policy_name set to memora."""
        s = self._metrics.snapshot()
        s.policy_name = "memora"
        return s
