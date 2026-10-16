"""Deterministic synthetic workload generators for MEMORA.

Provides 6 workload patterns:
1. Recency-heavy (favors LRU)
2. Frequency-heavy / Zipfian (favors LFU)
3. Sequential scan (favors FIFO / MRU)
4. Uniform random (stress test / baseline)
5. Mixed workload (blended distribution)
6. Phase transition (dynamic shifts between patterns)

All generators accept an explicit random seed for full experimental reproducibility.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

from memora.core.types import AccessRecord, Operation

__all__ = [
    "generate_recency_heavy",
    "generate_frequency_heavy",
    "generate_sequential",
    "generate_random_uniform",
    "generate_mixed",
    "generate_phase_transition",
    "save_trace_to_file",
]


def generate_recency_heavy(
    num_pages: int = 1000,
    length: int = 10000,
    hot_fraction: float = 0.2,
    hot_weight: float = 0.8,
    write_ratio: float = 0.1,
    seed: int = 42,
) -> list[AccessRecord]:
    """Generate a workload with strong temporal recency locality.

    A hot fraction of pages receives the vast majority of accesses,
    modeled with geometric back-references to recently accessed hot pages.

    Args:
        num_pages: Total universe of pages.
        length: Total number of access events to generate.
        hot_fraction: Fraction of pages designated as hot (0.0 to 1.0).
        hot_weight: Probability of selecting from the hot set.
        write_ratio: Fraction of accesses that are write operations.
        seed: Random seed.

    Returns:
        List of AccessRecord objects.
    """
    rng = np.random.default_rng(seed)
    num_hot = max(1, int(num_pages * hot_fraction))
    hot_pages = np.arange(num_hot)
    cold_pages = np.arange(num_hot, num_pages)

    # Hot stack to simulate recency
    hot_stack = list(hot_pages[: min(len(hot_pages), 50)])

    records: list[AccessRecord] = []
    for t in range(1, length + 1):
        is_write = rng.random() < write_ratio
        op = Operation.WRITE if is_write else Operation.READ

        if rng.random() < hot_weight and len(hot_stack) > 0:
            # Pick recently accessed hot page with geometric decay
            decay_idx = int(rng.geometric(p=0.15)) - 1
            idx = min(decay_idx, len(hot_stack) - 1)
            page_id = hot_stack.pop(idx)
            hot_stack.insert(0, page_id)
        else:
            if len(cold_pages) > 0:
                page_id = int(rng.choice(cold_pages))
            else:
                page_id = int(rng.choice(hot_pages))
            if page_id in hot_stack:
                hot_stack.remove(page_id)
            hot_stack.insert(0, page_id)
            if len(hot_stack) > 100:
                hot_stack.pop()

        records.append(AccessRecord(page_id=int(page_id), timestamp=t, operation=op))

    return records


def generate_frequency_heavy(
    num_pages: int = 1000,
    length: int = 10000,
    zipf_alpha: float = 1.2,
    write_ratio: float = 0.1,
    seed: int = 42,
) -> list[AccessRecord]:
    """Generate a Zipfian / power-law distributed workload.

    A few pages are referenced extremely frequently, perfectly matching LFU.

    Args:
        num_pages: Total universe of pages.
        length: Total number of accesses.
        zipf_alpha: Skew parameter (alpha > 1 gives heavy skew).
        write_ratio: Fraction of write accesses.
        seed: Random seed.

    Returns:
        List of AccessRecord objects.
    """
    rng = np.random.default_rng(seed)
    ranks = np.arange(1, num_pages + 1, dtype=np.float64)
    probs = 1.0 / (ranks ** zipf_alpha)
    probs /= probs.sum()

    pages = rng.choice(num_pages, size=length, p=probs)
    writes = rng.random(length) < write_ratio

    return [
        AccessRecord(
            page_id=int(pages[i]),
            timestamp=i + 1,
            operation=Operation.WRITE if writes[i] else Operation.READ,
        )
        for i in range(length)
    ]


def generate_sequential(
    num_pages: int = 1000,
    length: int = 10000,
    scan_length: int = 100,
    write_ratio: float = 0.05,
    seed: int = 42,
) -> list[AccessRecord]:
    """Generate sequential block scans across pages.

    Scans pages p, p+1, p+2, ... in stride-1 order, wrapping around.

    Args:
        num_pages: Total page pool size.
        length: Total access count.
        scan_length: Number of consecutive pages per scan.
        write_ratio: Fraction of writes.
        seed: Random seed.

    Returns:
        List of AccessRecord objects.
    """
    rng = np.random.default_rng(seed)
    records: list[AccessRecord] = []
    t = 1

    while len(records) < length:
        start_page = int(rng.integers(0, max(1, num_pages - scan_length)))
        cur_scan = min(scan_length, length - len(records))
        for step in range(cur_scan):
            page_id = (start_page + step) % num_pages
            is_write = rng.random() < write_ratio
            records.append(
                AccessRecord(
                    page_id=int(page_id),
                    timestamp=t,
                    operation=Operation.WRITE if is_write else Operation.READ,
                )
            )
            t += 1

    return records


def generate_random_uniform(
    num_pages: int = 1000,
    length: int = 10000,
    write_ratio: float = 0.1,
    seed: int = 42,
) -> list[AccessRecord]:
    """Generate uniform random page accesses without temporal or spatial locality.

    Args:
        num_pages: Universe of pages.
        length: Number of accesses.
        write_ratio: Fraction of writes.
        seed: Random seed.

    Returns:
        List of AccessRecord objects.
    """
    rng = np.random.default_rng(seed)
    pages = rng.integers(0, num_pages, size=length)
    writes = rng.random(length) < write_ratio

    return [
        AccessRecord(
            page_id=int(pages[i]),
            timestamp=i + 1,
            operation=Operation.WRITE if writes[i] else Operation.READ,
        )
        for i in range(length)
    ]


def generate_mixed(
    num_pages: int = 1000,
    length: int = 10000,
    mix_weights: Sequence[float] = (0.4, 0.3, 0.2, 0.1),
    write_ratio: float = 0.1,
    seed: int = 42,
) -> list[AccessRecord]:
    """Generate an interleaved mixture of recency, frequency, sequential, and random accesses.

    Weights correspond to: [recency, frequency, sequential, random].
    """
    rng = np.random.default_rng(seed)
    weights = np.array(mix_weights, dtype=np.float64)
    weights /= weights.sum()

    recency_trace = generate_recency_heavy(
        num_pages=num_pages, length=length, write_ratio=write_ratio, seed=seed + 1
    )
    freq_trace = generate_frequency_heavy(
        num_pages=num_pages, length=length, write_ratio=write_ratio, seed=seed + 2
    )
    seq_trace = generate_sequential(
        num_pages=num_pages, length=length, write_ratio=write_ratio, seed=seed + 3
    )
    rand_trace = generate_random_uniform(
        num_pages=num_pages, length=length, write_ratio=write_ratio, seed=seed + 4
    )

    traces = [recency_trace, freq_trace, seq_trace, rand_trace]
    indices = [0, 0, 0, 0]

    records: list[AccessRecord] = []
    for t in range(1, length + 1):
        chosen = int(rng.choice(4, p=weights))
        rec = traces[chosen][indices[chosen]]
        indices[chosen] = (indices[chosen] + 1) % length
        records.append(
            AccessRecord(
                page_id=rec.page_id,
                timestamp=t,
                operation=rec.operation,
            )
        )

    return records


def generate_phase_transition(
    phases: Sequence[dict[str, Any]],
    total_length: int = 10000,
    seed: int = 42,
) -> list[AccessRecord]:
    """Generate a composite workload exhibiting explicit phase changes.

    Args:
        phases: List of dicts specifying 'type' ('recency_heavy', 'frequency_heavy',
                'sequential', 'random_uniform') and 'length' (fraction or int), plus params.
        total_length: Overall length across all phases.
        seed: Random seed.

    Returns:
        List of AccessRecord objects across all phases.
    """
    records: list[AccessRecord] = []
    t = 1

    generator_map = {
        "recency_heavy": generate_recency_heavy,
        "frequency_heavy": generate_frequency_heavy,
        "sequential": generate_sequential,
        "random_uniform": generate_random_uniform,
    }

    for phase_idx, phase_spec in enumerate(phases):
        ptype = phase_spec.get("type", "random_uniform")
        plen = phase_spec.get("length", 1.0 / len(phases))
        if isinstance(plen, float) and plen <= 1.0:
            actual_len = int(round(plen * total_length))
        else:
            actual_len = int(plen)

        num_pages = phase_spec.get("num_pages", 1000)
        p_seed = seed + phase_idx * 100

        gen_fn = generator_map.get(ptype, generate_random_uniform)
        kwargs: dict[str, Any] = {
            "num_pages": num_pages,
            "length": actual_len,
            "seed": p_seed,
        }
        if "hot_fraction" in phase_spec:
            kwargs["hot_fraction"] = phase_spec["hot_fraction"]
        if "hot_weight" in phase_spec:
            kwargs["hot_weight"] = phase_spec["hot_weight"]
        if "zipf_alpha" in phase_spec:
            kwargs["zipf_alpha"] = phase_spec["zipf_alpha"]
        if "scan_length" in phase_spec:
            kwargs["scan_length"] = phase_spec["scan_length"]

        sub_records = gen_fn(**kwargs)
        for r in sub_records:
            records.append(
                AccessRecord(
                    page_id=r.page_id,
                    timestamp=t,
                    operation=r.operation,
                    query_id=f"phase_{phase_idx}_{ptype}",
                )
            )
            t += 1

    return records


def save_trace_to_file(
    records: Sequence[AccessRecord],
    file_path: Union[str, Path],
    fmt: str = "simple",
) -> Path:
    """Write access records to disk in simple or CSV format."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        if fmt == "structured" or str(path).endswith(".csv"):
            f.write("timestamp,page_id,operation,query_id\n")
            for r in records:
                op_str = "W" if r.operation == Operation.WRITE else "R"
                qid = r.query_id or ""
                f.write(f"{r.timestamp},{r.page_id},{op_str},{qid}\n")
        else:
            for r in records:
                f.write(f"{r.page_id}\n")

    return path
