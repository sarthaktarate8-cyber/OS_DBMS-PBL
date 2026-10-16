"""Configuration management for MEMORA experimental benchmarks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

import yaml

__all__ = ["ExperimentConfig", "load_experiment_config"]


@dataclass
class ExperimentConfig:
    """Master configuration for running benchmarks."""
    seed: int = 42
    output_dir: str = "results"
    figures_dir: str = "figures"
    trace_sizes: dict[str, int] = field(
        default_factory=lambda: {"small": 10000, "medium": 100000, "large": 1000000}
    )
    buffer_sizes: Sequence[int] = (64, 128, 256, 512, 1024)
    policies: Sequence[str] = ("lru", "lfu", "fifo", "memora")
    workloads: list[dict[str, Any]] = field(default_factory=list)
    ablations: list[dict[str, Any]] = field(default_factory=list)
    sensitivity: dict[str, Any] = field(default_factory=dict)


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    """Load ExperimentConfig from a YAML file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Configuration file not found: {p}")

    with open(p, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    global_cfg = raw.get("global", {})

    return ExperimentConfig(
        seed=global_cfg.get("seed", 42),
        output_dir=global_cfg.get("output_dir", "results"),
        figures_dir=global_cfg.get("figures_dir", "figures"),
        trace_sizes=global_cfg.get(
            "trace_sizes", {"small": 10000, "medium": 100000, "large": 1000000}
        ),
        buffer_sizes=raw.get("buffer_sizes", [64, 128, 256, 512, 1024]),
        policies=raw.get("policies", ["lru", "lfu", "fifo", "memora"]),
        workloads=raw.get("workloads", []),
        ablations=raw.get("ablations", []),
        sensitivity=raw.get("sensitivity", {}),
    )
