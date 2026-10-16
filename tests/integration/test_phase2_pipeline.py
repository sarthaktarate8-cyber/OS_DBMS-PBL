"""Integration tests for Phase 2 workload intelligence pipeline.

Verifies the four critical test cases:
1. Stable workload (expected: no phase change)
2. Abrupt change (expected: phase change flagged)
3. Small noise (expected: no unnecessary phase change)
4. Repeated oscillation (bounded detection without unbounded false alarms)
"""

import pytest
from memora.core.types import AccessRecord
from memora.detector.phase_detector import PhaseDetector
from memora.workloads.generators import (
    generate_frequency_heavy,
    generate_phase_transition,
    generate_random_uniform,
    generate_recency_heavy,
    generate_sequential,
)


def test_phase2_stable_workload_no_false_alarm():
    """Case A: Stable workload should NOT trigger phase change."""
    # A single continuous recency-heavy workload with identical parameters
    trace = generate_recency_heavy(num_pages=500, length=3000, seed=42)

    detector = PhaseDetector(
        window_size=500,
        step_size=250,
        overlap=True,
        phase_threshold=0.60,
        confidence_threshold=0.50,
        min_windows_before_detect=2,
    )

    detections = []
    for r in trace:
        res = detector.feed_record(r)
        if res is not None and res.is_phase_change:
            detections.append(res)

    # In a stationary workload, no window should exceed 0.60 phase threshold
    assert len(detections) == 0, f"Expected 0 detections in stable workload, got {len(detections)}"


def test_phase2_abrupt_change_detected():
    """Case B: Abrupt shift from sequential scan to heavy Zipfian frequency."""
    seq_trace = generate_sequential(num_pages=500, length=1500, scan_length=50, seed=10)
    # Abrupt transition to highly skewed Zipfian
    freq_trace = generate_frequency_heavy(num_pages=100, length=1500, zipf_alpha=2.0, seed=20)

    combined = seq_trace + freq_trace

    detector = PhaseDetector(
        window_size=500,
        step_size=250,
        overlap=True,
        phase_threshold=0.40,
        confidence_threshold=0.40,
        min_windows_before_detect=2,
    )

    detections = []
    for r in combined:
        res = detector.feed_record(r)
        if res is not None and res.is_phase_change:
            detections.append(res)

    assert len(detections) >= 1, "Abrupt transition must trigger at least one phase change detection"
    # Transition should flag frequency or sequential
    phases = [d.detected_phase for d in detections]
    assert any(p in ("frequency", "sequential") for p in phases)


def test_phase2_small_noise_suppression():
    """Case C: Small noise injected into a dominant workload must not trigger phase changes."""
    # Base recency workload with 5% random noise
    base = generate_recency_heavy(num_pages=500, length=2500, seed=42)
    noise = generate_random_uniform(num_pages=500, length=2500, seed=99)

    # Interleave 95% base, 5% noise
    interleaved = []
    for i in range(2500):
        if i % 20 == 0:
            interleaved.append(AccessRecord(page_id=noise[i].page_id, timestamp=i + 1))
        else:
            interleaved.append(AccessRecord(page_id=base[i].page_id, timestamp=i + 1))

    detector = PhaseDetector(
        window_size=500,
        step_size=250,
        overlap=True,
        phase_threshold=0.60,
        confidence_threshold=0.50,
        min_windows_before_detect=2,
    )

    detections = [res for r in interleaved if (res := detector.feed_record(r)) and res.is_phase_change]
    assert len(detections) == 0, f"Expected 0 detections under small 5% noise, got {len(detections)}"


def test_phase2_repeated_oscillation_bounded():
    """Case D: Repeated oscillation between patterns is tracked stably."""
    phases = [
        {"type": "sequential", "length": 500, "num_pages": 300, "scan_length": 30},
        {"type": "frequency_heavy", "length": 500, "num_pages": 100, "zipf_alpha": 1.8},
        {"type": "sequential", "length": 500, "num_pages": 300, "scan_length": 30},
        {"type": "frequency_heavy", "length": 500, "num_pages": 100, "zipf_alpha": 1.8},
    ]
    trace = generate_phase_transition(phases=phases, total_length=2000, seed=123)

    detector = PhaseDetector(
        window_size=250,
        step_size=125,
        overlap=True,
        phase_threshold=0.35,
        confidence_threshold=0.35,
        min_windows_before_detect=2,
    )

    detections = [res for r in trace if (res := detector.feed_record(r)) and res.is_phase_change]
    # Detections should match the number of phase shifts (approx 2 to 4), not run away uncontrollably
    assert 1 <= len(detections) <= 8, f"Oscillation produced unexpected detection count: {len(detections)}"
