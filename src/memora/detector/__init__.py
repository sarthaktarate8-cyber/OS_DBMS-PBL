"""Workload detection and phase change intelligence for MEMORA."""

from __future__ import annotations

from memora.detector.phase_detector import PhaseDetectionResult, PhaseDetector
from memora.detector.profile import WorkloadProfile, compute_jsd, compute_profile
from memora.detector.window import SlidingWindowManager

__all__ = [
    "WorkloadProfile",
    "compute_jsd",
    "compute_profile",
    "SlidingWindowManager",
    "PhaseDetector",
    "PhaseDetectionResult",
]
