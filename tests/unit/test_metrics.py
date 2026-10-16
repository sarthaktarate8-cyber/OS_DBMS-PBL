"""Unit tests for MetricsCollector and SimulationMetrics."""

import pytest
from memora.metrics.collector import MetricsCollector


def test_metrics_collector_empty():
    collector = MetricsCollector(policy_name="lru")
    snapshot = collector.snapshot()
    assert snapshot.total_accesses == 0
    assert snapshot.hit_ratio == 0.0
    assert snapshot.miss_ratio == 0.0
    assert snapshot.total_disk_io == 0


def test_metrics_collector_record_events():
    collector = MetricsCollector(
        policy_name="lru",
        disk_read_latency_ms=10.0,
        disk_write_latency_ms=15.0,
    )
    collector.start()

    # 3 accesses: 2 hits, 1 miss
    collector.record_access()
    collector.record_hit()

    collector.record_access()
    collector.record_hit()

    collector.record_access()
    collector.record_miss()

    # 1 dirty eviction
    collector.record_eviction(was_dirty=True)

    collector.stop()
    s = collector.snapshot()

    assert s.total_accesses == 3
    assert s.hits == 2
    assert s.misses == 1
    assert round(s.hit_ratio, 4) == round(2 / 3, 4)
    assert round(s.miss_ratio, 4) == round(1 / 3, 4)
    assert s.disk_reads == 1
    assert s.disk_writes == 1
    assert s.total_disk_io == 2
    assert s.simulated_read_latency_ms == 10.0
    assert s.simulated_write_latency_ms == 15.0
    assert s.total_simulated_latency_ms == 25.0

    d = s.to_dict()
    assert d["policy_name"] == "lru"
    assert d["total_disk_io"] == 2


def test_metrics_collector_reset():
    collector = MetricsCollector(policy_name="fifo")
    collector.record_access()
    collector.record_hit()
    collector.reset()

    s = collector.snapshot()
    assert s.total_accesses == 0
    assert s.hits == 0
