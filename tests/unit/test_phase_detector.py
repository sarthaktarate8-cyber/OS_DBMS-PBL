"""Unit tests for PhaseDetector."""

import pytest
from memora.core.types import AccessRecord
from memora.detector.phase_detector import PhaseDetector
from memora.workloads.generators import (
    generate_frequency_heavy,
    generate_recency_heavy,
    generate_sequential,
)


def test_phase_detector_windowing():
    detector = PhaseDetector(window_size=100, step_size=50, min_windows_before_detect=1)

    results = []
    for i in range(99):
        res = detector.feed_record(AccessRecord(page_id=i % 10, timestamp=i))
        assert res is None

    # 100th record completes first window
    res100 = detector.feed_record(AccessRecord(page_id=99 % 10, timestamp=100))
    assert res100 is not None
    assert not res100.is_phase_change  # Baseline window

    # Next 49 records return None
    for i in range(101, 150):
        res = detector.feed_record(AccessRecord(page_id=i % 10, timestamp=i))
        assert res is None

    # 150th record completes second window (step=50)
    res150 = detector.feed_record(AccessRecord(page_id=150 % 10, timestamp=150))
    assert res150 is not None


def test_phase_detector_flags_transition():
    detector = PhaseDetector(
        window_size=200,
        step_size=200,
        overlap=False,
        phase_threshold=0.40,
        confidence_threshold=0.40,
        min_windows_before_detect=2,
    )

    # Window 1: Sequential pages 0..199
    seq_records = generate_sequential(num_pages=200, length=200, scan_length=50, seed=1)
    for r in seq_records:
        detector.feed_record(r)

    # Window 2: Completely different disjoint Zipf distribution on pages 5000..5500
    zipf_records = generate_frequency_heavy(num_pages=100, length=200, zipf_alpha=2.0, seed=2)
    # Shift page IDs to 5000+ so support is completely disjoint
    shifted = [
        AccessRecord(page_id=r.page_id + 5000, timestamp=r.timestamp + 200, operation=r.operation)
        for r in zipf_records
    ]

    res2 = None
    for r in shifted:
        out = detector.feed_record(r)
        if out is not None:
            res2 = out

    assert res2 is not None
    assert res2.is_phase_change
    assert res2.composite_score >= 0.40
    assert res2.jsd > 0.80  # Disjoint pages produce high JSD
