"""Workload profiling and statistical feature extraction for MEMORA.

Computes quantifiable characterizations of page access windows:
- Frequency distribution & Shannon entropy
- Sequential access ratio (stride +1)
- Temporal reuse distance (stack distance)
- Jensen-Shannon Divergence (JSD) between successive windows
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from memora.core.types import AccessRecord, Operation

__all__ = ["WorkloadProfile", "compute_jsd", "compute_profile"]


@dataclass(frozen=True)
class WorkloadProfile:
    """Quantitative statistical profile of a workload window.

    Attributes:
        window_index: Sequential index of this observation window.
        sample_size: Number of access events analyzed in this window.
        distinct_pages: Number of unique pages referenced.
        entropy: Shannon entropy in bits (log2 base).
        sequentiality: Fraction of consecutive accesses with stride +1 [0.0, 1.0].
        mean_reuse_distance: Average LRU stack distance between re-accesses.
        read_fraction: Fraction of accesses that are read operations [0.0, 1.0].
        page_frequencies: Mapping of page_id to access count in this window.
    """

    window_index: int
    sample_size: int
    distinct_pages: int
    entropy: float
    sequentiality: float
    mean_reuse_distance: float
    read_fraction: float
    page_frequencies: dict[int, int] = field(default_factory=dict, repr=False)

    @property
    def write_fraction(self) -> float:
        """Fraction of accesses that are write operations."""
        return 1.0 - self.read_fraction


def compute_jsd(p_freq: dict[int, int], q_freq: dict[int, int]) -> float:
    """Compute Jensen-Shannon Divergence between two frequency distributions.

    JSD is symmetric, bounded in [0.0, 1.0] when using log2, and numerically stable.

    Args:
        p_freq: Frequency counts for distribution P.
        q_freq: Frequency counts for distribution Q.

    Returns:
        JSD value between 0.0 (identical) and 1.0 (disjoint).
    """
    if not p_freq or not q_freq:
        return 1.0

    total_p = sum(p_freq.values())
    total_q = sum(q_freq.values())
    if total_p == 0 or total_q == 0:
        return 1.0

    all_keys = set(p_freq.keys()) | set(q_freq.keys())

    # Normalized probability vectors
    p = np.array([p_freq.get(k, 0) / total_p for k in all_keys], dtype=np.float64)
    q = np.array([q_freq.get(k, 0) / total_q for k in all_keys], dtype=np.float64)

    m = 0.5 * (p + q)

    # Compute KL(p || m) and KL(q || m) using log2
    def kl_divergence(a: np.ndarray, b: np.ndarray) -> float:
        mask = a > 0
        return float(np.sum(a[mask] * np.log2(a[mask] / b[mask])))

    kl_pm = kl_divergence(p, m)
    kl_qm = kl_divergence(q, m)
    jsd = 0.5 * (kl_pm + kl_qm)

    return float(np.clip(jsd, 0.0, 1.0))


def compute_profile(
    records: Sequence[AccessRecord],
    window_index: int = 0,
    max_reuse_distance: int = 10000,
) -> WorkloadProfile:
    """Analyze a sequence of AccessRecord objects and build a WorkloadProfile.

    Args:
        records: Access records in the window.
        window_index: Integer index of this window.
        max_reuse_distance: Cap for reuse distance computation.

    Returns:
        WorkloadProfile containing extracted statistical features.
    """
    sample_size = len(records)
    if sample_size == 0:
        return WorkloadProfile(
            window_index=window_index,
            sample_size=0,
            distinct_pages=0,
            entropy=0.0,
            sequentiality=0.0,
            mean_reuse_distance=0.0,
            read_fraction=1.0,
            page_frequencies={},
        )

    # 1. Frequency and Entropy
    counts = Counter(r.page_id for r in records)
    distinct_pages = len(counts)
    total_count = float(sample_size)

    entropy = 0.0
    for count in counts.values():
        p = count / total_count
        if p > 0:
            entropy -= p * math.log2(p)

    # 2. Sequentiality (stride +1)
    sequential_steps = 0
    for i in range(sample_size - 1):
        if records[i + 1].page_id == records[i].page_id + 1:
            sequential_steps += 1
    sequentiality = sequential_steps / float(sample_size - 1) if sample_size > 1 else 0.0

    # 3. Mean Reuse Distance (LRU Stack Distance)
    # Track the order of recent unique pages
    last_seen: dict[int, int] = {}
    reuse_distances: list[int] = []

    for idx, r in enumerate(records):
        pid = r.page_id
        if pid in last_seen:
            # Count distinct pages accessed between last_seen[pid] and idx
            prev_idx = last_seen[pid]
            sub_window = records[prev_idx + 1 : idx]
            distinct_intervening = len({x.page_id for x in sub_window})
            reuse_distances.append(min(distinct_intervening, max_reuse_distance))
        last_seen[pid] = idx

    mean_reuse = float(np.mean(reuse_distances)) if reuse_distances else float(distinct_pages)

    # 4. Read / Write fraction
    reads = sum(1 for r in records if r.operation == Operation.READ)
    read_fraction = reads / total_count

    return WorkloadProfile(
        window_index=window_index,
        sample_size=sample_size,
        distinct_pages=distinct_pages,
        entropy=round(entropy, 4),
        sequentiality=round(sequentiality, 4),
        mean_reuse_distance=round(mean_reuse, 2),
        read_fraction=round(read_fraction, 4),
        page_frequencies=dict(counts),
    )
