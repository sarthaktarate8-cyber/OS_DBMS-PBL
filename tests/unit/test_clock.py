"""Unit tests for ClockPolicy (PostgreSQL Generalized Clock Sweep)."""

import pytest
from memora.policies.clock import ClockPolicy


def test_clock_empty():
    policy = ClockPolicy()
    assert policy.size() == 0
    assert policy.evict() is None
    assert not policy.contains(1)
    assert policy.get_usage_count(1) is None


def test_clock_insert_and_usage_count():
    policy = ClockPolicy(max_usage_count=5)
    policy.insert(1, timestamp=1)
    policy.insert(2, timestamp=2)

    assert policy.size() == 2
    assert policy.contains(1)
    assert policy.contains(2)
    assert policy.get_usage_count(1) == 1
    assert policy.get_usage_count(2) == 1


def test_clock_access_increments_up_to_max():
    policy = ClockPolicy(max_usage_count=3)
    policy.insert(10, timestamp=1)
    assert policy.get_usage_count(10) == 1

    policy.access(10, timestamp=2)
    assert policy.get_usage_count(10) == 2

    policy.access(10, timestamp=3)
    assert policy.get_usage_count(10) == 3

    # Capped at max_usage_count
    policy.access(10, timestamp=4)
    assert policy.get_usage_count(10) == 3


def test_clock_evict_decrements_and_evicts():
    policy = ClockPolicy(max_usage_count=5)
    # Insert 1, 2, 3 (each has usage_count=1)
    policy.insert(1, timestamp=1)
    policy.insert(2, timestamp=2)
    policy.insert(3, timestamp=3)

    # Hand starts at 1.
    # In first evict():
    # 1 has usage 1 -> decremented to 0
    # 2 has usage 1 -> decremented to 0
    # 3 has usage 1 -> decremented to 0
    # Sweeps back to 1: 1 now has usage 0 -> 1 is evicted!
    # Hand moves to 2.
    assert policy.evict() == 1
    assert policy.size() == 2
    assert not policy.contains(1)

    # Next evict: Hand at 2. 2 already has usage 0 -> 2 is evicted!
    assert policy.evict() == 2
    assert policy.size() == 1

    # Next evict: Hand at 3. 3 already has usage 0 -> 3 is evicted!
    assert policy.evict() == 3
    assert policy.size() == 0
    assert policy.evict() is None


def test_clock_hot_page_retention():
    """Verify that a page with higher usage count survives longer than cold pages."""
    policy = ClockPolicy(max_usage_count=5)
    policy.insert(1, timestamp=1)
    policy.insert(2, timestamp=2)

    # Boost page 2 to usage_count=3
    policy.access(2, timestamp=3)
    policy.access(2, timestamp=4)
    assert policy.get_usage_count(2) == 3

    # On first eviction:
    # 1: 1 -> 0
    # 2: 3 -> 2
    # 1: 0 -> evicted!
    assert policy.evict() == 1
    assert policy.contains(2)
    assert policy.size() == 1
    # Page 2 remains in cache
    assert policy.get_usage_count(2) == 2

    # Evicting again will eventually drain page 2's usage count and evict it
    assert policy.evict() == 2
    assert policy.size() == 0


def test_clock_remove_and_reset():
    policy = ClockPolicy()
    policy.insert(1, timestamp=1)
    policy.insert(2, timestamp=2)
    policy.insert(3, timestamp=3)

    policy.remove(2)
    assert not policy.contains(2)
    assert policy.size() == 2

    # Hand was at 1. Evicting should sweep 1, 3
    victim = policy.evict()
    assert victim in (1, 3)

    policy.reset()
    assert policy.size() == 0
    assert policy.evict() is None


def test_clock_invalid_max_usage():
    with pytest.raises(ValueError):
        ClockPolicy(max_usage_count=0)
