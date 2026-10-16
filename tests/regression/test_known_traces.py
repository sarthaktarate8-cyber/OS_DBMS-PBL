"""Regression tests using mathematically hand-calculated traces to verify exact simulator behavior."""

import pytest
from memora.core.buffer_pool import BufferPool
from memora.metrics.collector import MetricsCollector
from memora.policies.fifo import FIFOPolicy
from memora.policies.lfu import LFUPolicy
from memora.policies.lru import LRUPolicy
from memora.simulator.replay_engine import TraceReplayEngine
from memora.simulator.trace_loader import TraceLoader


def test_hand_calculated_trace_lru():
    """Trace: [1, 2, 3, 1, 4, 1, 2, 5], buffer size 3.

    Step-by-step ground truth for LRU:
    1: miss -> [1]
    2: miss -> [1, 2]
    3: miss -> [1, 2, 3]
    1: HIT  -> recency [2, 3, 1]
    4: miss -> evict 2 -> [3, 1, 4]
    1: HIT  -> recency [3, 4, 1]
    2: miss -> evict 3 -> [4, 1, 2]
    5: miss -> evict 4 -> [1, 2, 5]

    Expected: hits=2, misses=6, total=8, hit_ratio=0.25
    """
    trace = [1, 2, 3, 1, 4, 1, 2, 5]
    policy = LRUPolicy()
    metrics = MetricsCollector(policy_name="lru")
    pool = BufferPool(size=3, policy=policy, metrics=metrics)
    loader = TraceLoader(trace)
    engine = TraceReplayEngine(pool, loader, metrics)

    result = engine.run()
    assert result.total_accesses == 8
    assert result.hits == 2
    assert result.misses == 6
    assert result.hit_ratio == 0.25
    assert pool.resident_pages() == [1, 2, 5] or set(pool.resident_pages()) == {1, 2, 5}


def test_hand_calculated_trace_fifo():
    """Trace: [1, 2, 3, 1, 4, 1, 2, 5], buffer size 3.

    Step-by-step ground truth for FIFO:
    1: miss -> queue: [1]
    2: miss -> queue: [1, 2]
    3: miss -> queue: [1, 2, 3]
    1: HIT  -> queue: [1, 2, 3] (unchanged!)
    4: miss -> evict 1 -> queue: [2, 3, 4]
    1: miss -> evict 2 -> queue: [3, 4, 1]
    2: miss -> evict 3 -> queue: [4, 1, 2]
    5: miss -> evict 4 -> queue: [1, 2, 5]

    Expected: hits=1, misses=7, total=8, hit_ratio=0.125
    """
    trace = [1, 2, 3, 1, 4, 1, 2, 5]
    policy = FIFOPolicy()
    metrics = MetricsCollector(policy_name="fifo")
    pool = BufferPool(size=3, policy=policy, metrics=metrics)
    loader = TraceLoader(trace)
    engine = TraceReplayEngine(pool, loader, metrics)

    result = engine.run()
    assert result.total_accesses == 8
    assert result.hits == 1
    assert result.misses == 7
    assert result.hit_ratio == 0.125
    assert set(pool.resident_pages()) == {1, 2, 5}


def test_hand_calculated_trace_lfu():
    """Trace: [1, 2, 3, 1, 4, 1, 2, 5], buffer size 3.

    Step-by-step ground truth for LFU:
    1: miss -> freq: {1:1}
    2: miss -> freq: {1:1, 2:1}
    3: miss -> freq: {1:1, 2:1, 3:1}
    1: HIT  -> freq: {1:2, 2:1, 3:1}
    4: miss -> evict 2 (tie-break LRU between 2,3) -> freq: {1:2, 3:1, 4:1}
    1: HIT  -> freq: {1:3, 3:1, 4:1}
    2: miss -> evict 3 (tie-break LRU between 3,4) -> freq: {1:3, 4:1, 2:1}
    5: miss -> evict 4 (tie-break LRU between 4,2) -> freq: {1:3, 2:1, 5:1}

    Expected: hits=2, misses=6, total=8, hit_ratio=0.25
    """
    trace = [1, 2, 3, 1, 4, 1, 2, 5]
    policy = LFUPolicy()
    metrics = MetricsCollector(policy_name="lfu")
    pool = BufferPool(size=3, policy=policy, metrics=metrics)
    loader = TraceLoader(trace)
    engine = TraceReplayEngine(pool, loader, metrics)

    result = engine.run()
    assert result.total_accesses == 8
    assert result.hits == 2
    assert result.misses == 6
    assert result.hit_ratio == 0.25
    assert set(pool.resident_pages()) == {1, 2, 5}
