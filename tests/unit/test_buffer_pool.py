"""Unit tests for BufferPool."""

import pytest
from memora.core.buffer_pool import BufferPool
from memora.core.types import AccessRecord, Operation
from memora.metrics.collector import MetricsCollector
from memora.policies.fifo import FIFOPolicy
from memora.policies.lru import LRUPolicy


def test_buffer_pool_init():
    pool = BufferPool(size=4, policy=LRUPolicy())
    assert pool.size == 4
    assert pool.occupancy == 0
    assert pool.free_count == 4
    assert not pool.is_full


def test_buffer_pool_hit_and_miss():
    metrics = MetricsCollector(policy_name="lru")
    pool = BufferPool(size=3, policy=LRUPolicy(), metrics=metrics)

    # Access 1 -> Miss
    hit = pool.access(AccessRecord(page_id=1, timestamp=1))
    assert not hit
    assert pool.occupancy == 1
    assert pool.contains(1)

    # Access 1 -> Hit
    hit = pool.access(AccessRecord(page_id=1, timestamp=2))
    assert hit

    snapshot = metrics.snapshot()
    assert snapshot.hits == 1
    assert snapshot.misses == 1
    assert snapshot.total_accesses == 2


def test_buffer_pool_dirty_writes_and_flush():
    metrics = MetricsCollector(policy_name="lru")
    pool = BufferPool(size=2, policy=LRUPolicy(), metrics=metrics)

    # Write to page 10
    pool.access(AccessRecord(page_id=10, timestamp=1, operation=Operation.WRITE))
    frame = pool.get_frame(10)
    assert frame is not None
    assert frame.dirty_bit

    # Evict page 10 by loading pages 20 and 30
    pool.access(AccessRecord(page_id=20, timestamp=2, operation=Operation.READ))
    pool.access(AccessRecord(page_id=30, timestamp=3, operation=Operation.READ))

    # Page 10 should have been evicted and counted as dirty eviction
    snapshot = metrics.snapshot()
    assert snapshot.dirty_evictions == 1
    assert snapshot.disk_writes == 1


def test_buffer_pool_policy_switch():
    pool = BufferPool(size=3, policy=LRUPolicy())
    pool.access(AccessRecord(page_id=1, timestamp=1))
    pool.access(AccessRecord(page_id=2, timestamp=2))

    new_policy = FIFOPolicy()
    pool.set_policy(new_policy, strategy="hard")

    assert pool.policy.name == "fifo"
    assert new_policy.contains(1)
    assert new_policy.contains(2)


def test_buffer_pool_pinning():
    pool = BufferPool(size=2, policy=LRUPolicy())
    pool.access(AccessRecord(page_id=1, timestamp=1))
    pool.access(AccessRecord(page_id=2, timestamp=2))

    # Pin frame 1
    frame1 = pool.get_frame(1)
    assert frame1 is not None
    frame1.pin()

    # Access page 3 -> LRU would want to evict 1, but 1 is pinned! Frame 2 should be evicted
    pool.access(AccessRecord(page_id=3, timestamp=3))
    assert pool.contains(1)
    assert pool.contains(3)
    assert not pool.contains(2)

    frame1.unpin()
    assert not frame1.is_pinned
