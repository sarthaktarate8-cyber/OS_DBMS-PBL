"""Unit tests for LFUPolicy."""

import pytest
from memora.policies.lfu import LFUPolicy


def test_lfu_empty():
    policy = LFUPolicy()
    assert policy.size() == 0
    assert policy.evict() is None
    assert not policy.contains(1)


def test_lfu_frequency_tracking():
    policy = LFUPolicy()
    policy.insert(1, timestamp=1)
    assert policy.get_frequency(1) == 1

    policy.access(1, timestamp=2)
    assert policy.get_frequency(1) == 2

    policy.access(1, timestamp=3)
    assert policy.get_frequency(1) == 3


def test_lfu_evicts_lowest_frequency():
    policy = LFUPolicy()
    policy.insert(1, timestamp=1)
    policy.insert(2, timestamp=2)
    policy.insert(3, timestamp=3)

    # 1 accessed 3 times, 2 accessed 2 times, 3 accessed 1 time
    policy.access(1, timestamp=4)
    policy.access(1, timestamp=5)
    policy.access(2, timestamp=6)

    assert policy.get_frequency(1) == 3
    assert policy.get_frequency(2) == 2
    assert policy.get_frequency(3) == 1

    # Victim must be 3 (freq=1)
    assert policy.evict() == 3
    # Next victim must be 2 (freq=2)
    assert policy.evict() == 2
    # Next victim must be 1 (freq=3)
    assert policy.evict() == 1
    assert policy.evict() is None


def test_lfu_tie_breaking_lru():
    """Verify Assumption A1: equal frequency breaks ties using LRU."""
    policy = LFUPolicy()
    policy.insert(10, timestamp=1)
    policy.insert(20, timestamp=2)
    policy.insert(30, timestamp=3)

    # All three have frequency 1.
    # Recency order (oldest to newest): 10, 20, 30
    assert policy.evict() == 10
    assert policy.evict() == 20
    assert policy.evict() == 30


def test_lfu_tie_breaking_with_accesses():
    policy = LFUPolicy()
    policy.insert(10, timestamp=1)
    policy.insert(20, timestamp=2)

    # Both incremented to freq 2
    policy.access(10, timestamp=3)
    policy.access(20, timestamp=4)

    # Both have freq 2. 10 was accessed earlier than 20.
    # Therefore 10 is the LRU within frequency bucket 2.
    assert policy.evict() == 10
    assert policy.evict() == 20


def test_lfu_remove_and_reset():
    policy = LFUPolicy()
    policy.insert(1, timestamp=1)
    policy.insert(2, timestamp=2)
    policy.remove(1)

    assert not policy.contains(1)
    assert policy.size() == 1
    assert policy.evict() == 2

    policy.insert(3, timestamp=3)
    policy.reset()
    assert policy.size() == 0
    assert policy.evict() is None
