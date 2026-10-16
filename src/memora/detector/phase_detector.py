"""Phase change detector using multi-feature statistical divergence.

Detects phase shifts in the access stream by computing:
- Jensen-Shannon Divergence on frequency histograms
- Normalized Entropy Delta
- Sequentiality Delta
- Reuse Distance Delta
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Optional

from memora.core.types import AccessRecord
from memora.detector.profile import WorkloadProfile, compute_jsd, compute_profile
from memora.detector.window import SlidingWindowManager

__all__ = ["PhaseDetector", "PhaseDetectionResult"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PhaseDetectionResult:
    """Result of evaluating a sliding window for phase transitions.

    Attributes:
        is_phase_change: True if composite score exceeds phase_threshold.
        confidence: Confidence score of the detection [0.0, 1.0].
        composite_score: Weighted multi-feature divergence score.
        detected_phase: Classified workload characteristic ('recency', 'frequency', 'sequential', 'random').
        jsd: Frequency histogram divergence [0.0, 1.0].
        entropy_delta: Relative change in access entropy.
        sequentiality_delta: Absolute difference in sequentiality ratio.
        reuse_distance_delta: Relative change in mean reuse distance.
        current_profile: Profile of the current window.
        previous_profile: Profile of the preceding window.
    """

    is_phase_change: bool
    confidence: float
    composite_score: float
    detected_phase: str
    jsd: float
    entropy_delta: float
    sequentiality_delta: float
    reuse_distance_delta: float
    current_profile: Optional[WorkloadProfile] = None
    previous_profile: Optional[WorkloadProfile] = None


class PhaseDetector:
    """Detects phase changes in a streaming workload trace."""

    def __init__(
        self,
        window_size: int = 1000,
        step_size: int = 250,
        overlap: bool = True,
        phase_threshold: float = 0.70,
        confidence_threshold: float = 0.60,
        min_windows_before_detect: int = 2,
        feature_weights: Optional[dict[str, float]] = None,
        max_reuse_distance: int = 10000,
    ) -> None:
        """Initialize PhaseDetector.

        Args:
            window_size: Number of records in sliding observation window.
            step_size: Step stride between evaluations.
            overlap: Whether sliding windows overlap.
            phase_threshold: Composite threshold to flag a phase shift.
            confidence_threshold: Minimum required confidence level.
            min_windows_before_detect: Initial warm-up windows before flags.
            feature_weights: Weights for JSD, entropy, sequentiality, reuse.
            max_reuse_distance: Capping limit for stack distance calculations.
        """
        self._window_mgr = SlidingWindowManager(
            window_size=window_size, step_size=step_size, overlap=overlap
        )
        self._phase_threshold = phase_threshold
        self._confidence_threshold = confidence_threshold
        self._min_windows = min_windows_before_detect
        self._max_reuse_distance = max_reuse_distance

        default_weights = {
            "jsd_frequency": 0.50,
            "entropy_delta": 0.20,
            "sequentiality_delta": 0.15,
            "reuse_distance_delta": 0.15,
        }
        self._weights = feature_weights or default_weights
        # Normalize weights to sum to 1.0
        w_sum = sum(self._weights.values())
        if w_sum > 0:
            self._weights = {k: v / w_sum for k, v in self._weights.items()}

        self._previous_profile: Optional[WorkloadProfile] = None
        self._windows_analyzed = 0
        self._detection_history: list[PhaseDetectionResult] = []

    @property
    def windows_analyzed(self) -> int:
        """Total windows examined."""
        return self._windows_analyzed

    @property
    def history(self) -> list[PhaseDetectionResult]:
        """Chronological list of all detection results."""
        return list(self._detection_history)

    def feed_record(self, record: AccessRecord) -> Optional[PhaseDetectionResult]:
        """Ingest one AccessRecord from the stream and evaluate if at a step boundary.

        Returns:
            PhaseDetectionResult when a window is evaluated, or None.
        """
        window_records = self._window_mgr.add_record(record)
        if window_records is None:
            return None

        self._windows_analyzed += 1
        current_profile = compute_profile(
            window_records,
            window_index=self._windows_analyzed,
            max_reuse_distance=self._max_reuse_distance,
        )

        detected_phase = self._classify_phase(current_profile)

        if self._previous_profile is None:
            # First window: establish baseline
            self._previous_profile = current_profile
            res = PhaseDetectionResult(
                is_phase_change=False,
                confidence=0.0,
                composite_score=0.0,
                detected_phase=detected_phase,
                jsd=0.0,
                entropy_delta=0.0,
                sequentiality_delta=0.0,
                reuse_distance_delta=0.0,
                current_profile=current_profile,
                previous_profile=None,
            )
            self._detection_history.append(res)
            return res

        # Compute multi-feature divergence
        jsd = compute_jsd(
            self._previous_profile.page_frequencies,
            current_profile.page_frequencies,
        )

        # Normalized Entropy Delta
        max_ent = max(self._previous_profile.entropy, current_profile.entropy, 1.0)
        entropy_delta = abs(current_profile.entropy - self._previous_profile.entropy) / max_ent

        # Sequentiality Delta
        seq_delta = abs(current_profile.sequentiality - self._previous_profile.sequentiality)

        # Normalized Reuse Distance Delta
        max_reuse = max(
            self._previous_profile.mean_reuse_distance,
            current_profile.mean_reuse_distance,
            1.0,
        )
        reuse_delta = (
            abs(current_profile.mean_reuse_distance - self._previous_profile.mean_reuse_distance)
            / max_reuse
        )

        composite_score = (
            self._weights.get("jsd_frequency", 0.5) * jsd
            + self._weights.get("entropy_delta", 0.2) * entropy_delta
            + self._weights.get("sequentiality_delta", 0.15) * seq_delta
            + self._weights.get("reuse_distance_delta", 0.15) * reuse_delta
        )

        # Confidence metric
        if composite_score >= self._phase_threshold:
            confidence = min(1.0, 0.5 + 0.5 * (composite_score - self._phase_threshold) / (1.0 - self._phase_threshold + 1e-6))
        else:
            confidence = composite_score / (self._phase_threshold + 1e-6)

        is_change = (
            composite_score >= self._phase_threshold
            and confidence >= self._confidence_threshold
            and self._windows_analyzed >= self._min_windows
        )

        result = PhaseDetectionResult(
            is_phase_change=is_change,
            confidence=round(confidence, 4),
            composite_score=round(composite_score, 4),
            detected_phase=detected_phase,
            jsd=round(jsd, 4),
            entropy_delta=round(entropy_delta, 4),
            sequentiality_delta=round(seq_delta, 4),
            reuse_distance_delta=round(reuse_delta, 4),
            current_profile=current_profile,
            previous_profile=self._previous_profile,
        )

        if is_change:
            logger.info(
                "Phase shift detected at window %d: phase=%s score=%.3f conf=%.3f (JSD=%.3f, seq_delta=%.3f)",
                self._windows_analyzed,
                detected_phase,
                composite_score,
                confidence,
                jsd,
                seq_delta,
            )

        self._previous_profile = current_profile
        self._detection_history.append(result)
        return result

    def _classify_phase(self, profile: WorkloadProfile) -> str:
        """Classify the dominant workload type for a window."""
        if profile.sample_size == 0:
            return "random"

        # 1. Sequential Scan
        if profile.sequentiality >= 0.45:
            return "sequential"

        # 2. Frequency / Skewed Zipfian
        # Measure concentration: share of accesses accounted for by top 20% pages
        if profile.page_frequencies:
            freqs = sorted(profile.page_frequencies.values(), reverse=True)
            top_20_count = max(1, int(len(freqs) * 0.2))
            top_share = sum(freqs[:top_20_count]) / float(profile.sample_size)
            if top_share >= 0.55:
                return "frequency"

        # 3. Recency Heavy (low mean reuse distance relative to distinct pages)
        if profile.distinct_pages > 0 and profile.mean_reuse_distance < 0.35 * profile.distinct_pages:
            return "recency"

        # 4. Uniform Random
        return "random"

    def reset(self) -> None:
        """Reset state."""
        self._window_mgr.reset()
        self._previous_profile = None
        self._windows_analyzed = 0
        self._detection_history.clear()
