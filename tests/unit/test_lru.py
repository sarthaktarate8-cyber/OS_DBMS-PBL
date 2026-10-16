"""Unit tests for LRUPolicy."""

import pytest
from memora.policies.lru import LRUPolicy


def test_lru_empty():
    policy = LRUPolicy()
    assert policy.size() == 0
    assert policy.evict() is None
    assert policy.peek_lru() is None
    assert not policy.contains(1)


def test_lru_insert_and_evict_order():
    policy = LRUPolicy()
    policy.insert(1, timestamp=1)
    policy.insert(2, timestamp=2)
    policy.insert(3, timestamp=3)

    assert policy.size() == 3
    assert policy.peek_lru() == 1

    # Evict should return least recently accessed (1, then 2, then 3)
    assert policy.evict() == 1
    assert policy.size() == 2
    assert policy.evict() == 2
    assert policy.evict() == 3
    assert policy.evict() is None


def test_lru_access_promotes_to_mru():
    policy = LRUPolicy()
    policy.insert(1, timestamp=1)
    policy.insert(2, timestamp=2)
    policy.insert(3, timestamp=3)

    # Access page 1 -> moves 1 to MRU, so LRU is now 2
    policy.access(1, timestamp=4)
    assert policy.peek_lru() == 2

    assert policy.evict() == 2
    assert policy.evict() == 3
    assert policy.evict() == 1


def test_lru_remove_and_reset():
    policy = LRUPolicy()
    policy.insert(10, timestamp=1)
    policy.insert(20, timestamp=2)
    assert policy.contains(10)

    policy.remove(10)
    assert not policy.contains(10)
    assert policy.size() == 1
    assert policy.evict() == 20

    policy.insert(30, timestamp=3)
    policy.reset()
    assert policy.size() == 0
    assert policy.evict() is None
