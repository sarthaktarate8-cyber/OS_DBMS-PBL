"""Unit tests for FIFOPolicy."""

import pytest
from memora.policies.fifo import FIFOPolicy


def test_fifo_empty():
    policy = FIFOPolicy()
    assert policy.size() == 0
    assert policy.evict() is None
    assert policy.peek_fifo() is None


def test_fifo_insertion_order():
    policy = FIFOPolicy()
    policy.insert(1, timestamp=1)
    policy.insert(2, timestamp=2)
    policy.insert(3, timestamp=3)

    assert policy.size() == 3
    assert policy.peek_fifo() == 1
    assert policy.evict() == 1
    assert policy.evict() == 2
    assert policy.evict() == 3
    assert policy.evict() is None


def test_fifo_access_does_not_reorder():
    """In FIFO, subsequent hits must NOT move items to the back."""
    policy = FIFOPolicy()
    policy.insert(1, timestamp=1)
    policy.insert(2, timestamp=2)
    policy.insert(3, timestamp=3)

    # Re-access page 1 multiple times
    policy.access(1, timestamp=4)
    policy.access(1, timestamp=5)

    # Page 1 was still inserted earliest, so it must be evicted first
    assert policy.evict() == 1
    assert policy.evict() == 2
    assert policy.evict() == 3


def test_fifo_remove_and_reset():
    policy = FIFOPolicy()
    policy.insert(10, timestamp=1)
    policy.insert(20, timestamp=2)

    policy.remove(10)
    assert not policy.contains(10)
    assert policy.evict() == 20

    policy.insert(30, timestamp=3)
    policy.reset()
    assert policy.size() == 0
    assert policy.evict() is None
