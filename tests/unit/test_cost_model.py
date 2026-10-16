"""Unit tests for SwitchCostModel and CostBenefitEngine."""

import pytest
from memora.decision.cost_model import CostModelConfig, SwitchCostModel
from memora.decision.engine import CostBenefitEngine, EngineConfig
from memora.detector.profile import WorkloadProfile


def test_cost_model_same_policy_zero():
    model = SwitchCostModel()
    cost = model.compute_cost(current_policy="lru", target_policy="lru", buffer_size=256)
    assert cost == 0.0


def test_cost_model_different_policy_positive():
    model = SwitchCostModel()
    cost = model.compute_cost(current_policy="lru", target_policy="lfu", buffer_size=256)
    assert cost > 0.0
    assert cost < 1.0


def test_cost_model_buffer_scaling():
    model = SwitchCostModel()
    cost_small = model.compute_cost("lru", "lfu", buffer_size=64, window_size=1000)
    cost_large = model.compute_cost("lru", "lfu", buffer_size=512, window_size=1000)
    assert cost_large > cost_small


def test_engine_recommends_switch():
    engine = CostBenefitEngine(config=EngineConfig(minimum_net_benefit=0.02))
    dummy_profile = WorkloadProfile(
        window_index=1,
        sample_size=1000,
        distinct_pages=200,
        entropy=4.5,
        sequentiality=0.05,
        mean_reuse_distance=15.0,
        read_fraction=0.9,
    )

    # Currently FIFO, workload is recency-heavy -> should switch to LRU
    decision = engine.evaluate(
        current_policy="fifo",
        detected_phase="recency",
        profile=dummy_profile,
        buffer_size=256,
        access_counter=1000,
    )

    assert decision.should_switch
    assert decision.recommended_policy == "lru"
    assert decision.net_benefit >= 0.02


def test_engine_retains_when_already_optimal():
    engine = CostBenefitEngine()
    dummy_profile = WorkloadProfile(
        window_index=1,
        sample_size=1000,
        distinct_pages=200,
        entropy=4.5,
        sequentiality=0.05,
        mean_reuse_distance=15.0,
        read_fraction=0.9,
    )

    # Already on LRU during recency phase
    decision = engine.evaluate(
        current_policy="lru",
        detected_phase="recency",
        profile=dummy_profile,
        buffer_size=256,
        access_counter=1000,
    )

    assert not decision.should_switch
    assert decision.recommended_policy == "lru"


def test_engine_gating_rejects_sub_threshold_benefit():
    # Set an impossibly high threshold (0.50)
    engine = CostBenefitEngine(config=EngineConfig(minimum_net_benefit=0.50))
    dummy_profile = WorkloadProfile(
        window_index=1,
        sample_size=1000,
        distinct_pages=200,
        entropy=4.5,
        sequentiality=0.05,
        mean_reuse_distance=15.0,
        read_fraction=0.9,
    )

    decision = engine.evaluate(
        current_policy="fifo",
        detected_phase="recency",
        profile=dummy_profile,
        buffer_size=256,
        access_counter=1000,
    )

    assert not decision.should_switch
    assert "below minimum threshold" in decision.reason
