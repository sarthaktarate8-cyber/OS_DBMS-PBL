"""Integration tests for Phase 3 Adaptive MEMORA controller pipeline."""

import pytest
from memora.adaptive.controller import AdaptiveBufferManager, AdaptiveConfig
from memora.core.buffer_pool import BufferPool
from memora.core.types import AccessRecord
from memora.decision.engine import CostBenefitEngine, EngineConfig
from memora.detector.phase_detector import PhaseDetector
from memora.metrics.collector import MetricsCollector
from memora.policies.fifo import FIFOPolicy
from memora.workloads.generators import (
    generate_frequency_heavy,
    generate_phase_transition,
    generate_recency_heavy,
    generate_sequential,
)


def test_adaptive_controller_switches_when_profitable():
    """Verify AdaptiveBufferManager switches from FIFO to LRU on recency workload."""
    pool = BufferPool(size=50, policy=FIFOPolicy())
    detector = PhaseDetector(
        window_size=200,
        step_size=100,
        overlap=True,
        phase_threshold=0.30,
        confidence_threshold=0.30,
        min_windows_before_detect=1,
    )
    engine = CostBenefitEngine(config=EngineConfig(minimum_net_benefit=0.01))
    manager = AdaptiveBufferManager(
        buffer_pool=pool,
        detector=detector,
        decision_engine=engine,
        config=AdaptiveConfig(cooldown_accesses=200),
    )

    # Window 1: Sequential to train baseline
    seq = generate_sequential(num_pages=50, length=200, seed=1)
    for r in seq:
        manager.access(r)

    # Window 2: Heavy recency on disjoint pages
    recency = generate_recency_heavy(num_pages=100, length=400, hot_fraction=0.1, hot_weight=0.95, seed=2)
    shifted_recency = [
        AccessRecord(page_id=r.page_id + 500, timestamp=r.timestamp + 200, operation=r.operation)
        for r in recency
    ]

    for r in shifted_recency:
        manager.access(r)

    # Verify that a switch was executed to LRU
    accepted_switches = [s for s in manager.switch_history if s.accepted]
    assert len(accepted_switches) >= 1
    assert any(s.new_policy == "lru" for s in accepted_switches)
    assert manager.current_policy_name == "lru"


def test_adaptive_controller_cooldown_suppresses_thrashing():
    """Verify that during cooldown, policy switches are rejected."""
    pool = BufferPool(size=30, policy=FIFOPolicy())
    detector = PhaseDetector(
        window_size=100,
        step_size=50,
        overlap=False,
        phase_threshold=0.20,
        confidence_threshold=0.20,
        min_windows_before_detect=1,
    )
    engine = CostBenefitEngine(config=EngineConfig(minimum_net_benefit=0.01))
    # Long cooldown of 5000 accesses
    manager = AdaptiveBufferManager(
        buffer_pool=pool,
        detector=detector,
        decision_engine=engine,
        config=AdaptiveConfig(cooldown_accesses=5000),
    )

    # 1. Baseline
    for r in generate_sequential(num_pages=30, length=100, seed=1):
        manager.access(r)

    # 2. Recency shift triggers initial switch
    for r in generate_recency_heavy(num_pages=30, length=100, seed=2):
        manager.access(AccessRecord(page_id=r.page_id + 100, timestamp=r.timestamp + 100))

    accepted = [s for s in manager.switch_history if s.accepted]
    assert len(accepted) <= 1

    # 3. Another rapid shift within cooldown period
    for r in generate_frequency_heavy(num_pages=30, length=100, zipf_alpha=1.8, seed=3):
        manager.access(AccessRecord(page_id=r.page_id + 200, timestamp=r.timestamp + 200))

    # Second shift must be suppressed because access count is within cooldown (cooldown=5000)
    rejections = [s for s in manager.switch_history if not s.accepted and "Cooldown active" in s.reason]
    assert len(rejections) >= 1
