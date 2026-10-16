"""Integration tests for Phase 1 simulation pipeline."""

import pytest
from memora.core.buffer_pool import BufferPool
from memora.metrics.collector import MetricsCollector
from memora.policies.fifo import FIFOPolicy
from memora.policies.lfu import LFUPolicy
from memora.policies.lru import LRUPolicy
from memora.simulator.replay_engine import TraceReplayEngine
from memora.simulator.trace_loader import TraceLoader
from memora.workloads.generators import (
    generate_frequency_heavy,
    generate_mixed,
    generate_phase_transition,
    generate_random_uniform,
    generate_recency_heavy,
    generate_sequential,
)


def test_recency_workload_lru_beats_fifo():
    """Verify LRU outperforms FIFO on recency-heavy workloads."""
    records = generate_recency_heavy(
        num_pages=200, length=2000, hot_fraction=0.1, hot_weight=0.9, seed=123
    )

    # LRU
    p_lru = LRUPolicy()
    m_lru = MetricsCollector(policy_name="lru")
    b_lru = BufferPool(size=30, policy=p_lru, metrics=m_lru)
    e_lru = TraceReplayEngine(b_lru, TraceLoader(records), m_lru)
    r_lru = e_lru.run()

    # FIFO
    p_fifo = FIFOPolicy()
    m_fifo = MetricsCollector(policy_name="fifo")
    b_fifo = BufferPool(size=30, policy=p_fifo, metrics=m_fifo)
    e_fifo = TraceReplayEngine(b_fifo, TraceLoader(records), m_fifo)
    r_fifo = e_fifo.run()

    assert r_lru.total_accesses == 2000
    assert r_fifo.total_accesses == 2000
    assert r_lru.hit_ratio > r_fifo.hit_ratio


def test_frequency_workload_lfu_beats_fifo():
    """Verify LFU performs strongly on skewed Zipfian workloads."""
    records = generate_frequency_heavy(
        num_pages=200, length=2000, zipf_alpha=1.5, seed=123
    )

    # LFU
    p_lfu = LFUPolicy()
    m_lfu = MetricsCollector(policy_name="lfu")
    b_lfu = BufferPool(size=30, policy=p_lfu, metrics=m_lfu)
    e_lfu = TraceReplayEngine(b_lfu, TraceLoader(records), m_lfu)
    r_lfu = e_lfu.run()

    # FIFO
    p_fifo = FIFOPolicy()
    m_fifo = MetricsCollector(policy_name="fifo")
    b_fifo = BufferPool(size=30, policy=p_fifo, metrics=m_fifo)
    e_fifo = TraceReplayEngine(b_fifo, TraceLoader(records), m_fifo)
    r_fifo = e_fifo.run()

    assert r_lfu.total_accesses == 2000
    assert r_fifo.total_accesses == 2000
    assert r_lfu.hit_ratio >= r_fifo.hit_ratio


def test_all_workload_generators_execute_cleanly():
    """Verify each generator runs and replays without errors."""
    generators = [
        generate_recency_heavy(num_pages=50, length=200, seed=42),
        generate_frequency_heavy(num_pages=50, length=200, seed=42),
        generate_sequential(num_pages=50, length=200, seed=42),
        generate_random_uniform(num_pages=50, length=200, seed=42),
        generate_mixed(num_pages=50, length=200, seed=42),
        generate_phase_transition(
            phases=[
                {"type": "recency_heavy", "length": 0.5, "num_pages": 50},
                {"type": "sequential", "length": 0.5, "num_pages": 50},
            ],
            total_length=200,
            seed=42,
        ),
    ]

    for trace in generators:
        assert len(trace) == 200
        pool = BufferPool(size=10, policy=LRUPolicy())
        engine = TraceReplayEngine(pool, TraceLoader(trace))
        metrics = engine.run()
        assert metrics.total_accesses == 200
        assert metrics.hits + metrics.misses == 200
