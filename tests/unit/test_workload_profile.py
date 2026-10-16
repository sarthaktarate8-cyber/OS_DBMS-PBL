"""Unit tests for WorkloadProfile and statistical computation."""

import math
import pytest
from memora.core.types import AccessRecord, Operation
from memora.detector.profile import compute_jsd, compute_profile


def test_jsd_identical_distributions():
    dist = {1: 10, 2: 20, 3: 30}
    assert compute_jsd(dist, dist) == pytest.approx(0.0, abs=1e-6)


def test_jsd_disjoint_distributions():
    p = {1: 10, 2: 10}
    q = {3: 10, 4: 10}
    # Completely disjoint support has maximal JSD = 1.0
    assert compute_jsd(p, q) == pytest.approx(1.0, abs=1e-4)


def test_jsd_symmetry():
    p = {1: 50, 2: 30, 3: 20}
    q = {1: 10, 2: 70, 4: 20}
    assert compute_jsd(p, q) == pytest.approx(compute_jsd(q, p), abs=1e-6)


def test_profile_sequential_stream():
    records = [
        AccessRecord(page_id=i, timestamp=i, operation=Operation.READ)
        for i in range(1, 101)
    ]
    prof = compute_profile(records, window_index=1)
    assert prof.sample_size == 100
    assert prof.distinct_pages == 100
    assert prof.sequentiality == pytest.approx(1.0, abs=1e-3)
    assert prof.read_fraction == 1.0


def test_profile_single_page_entropy():
    records = [
        AccessRecord(page_id=42, timestamp=i, operation=Operation.READ)
        for i in range(1, 51)
    ]
    prof = compute_profile(records, window_index=1)
    assert prof.distinct_pages == 1
    assert prof.entropy == pytest.approx(0.0, abs=1e-6)


def test_profile_uniform_entropy():
    # 8 pages equally accessed 10 times each -> entropy should be log2(8) = 3.0 bits
    records = []
    t = 1
    for p in range(8):
        for _ in range(10):
            records.append(AccessRecord(page_id=p, timestamp=t))
            t += 1
    prof = compute_profile(records, window_index=1)
    assert prof.distinct_pages == 8
    assert prof.entropy == pytest.approx(3.0, abs=1e-2)
