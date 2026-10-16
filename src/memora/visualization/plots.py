"""Visualization module for MEMORA benchmark evaluation.

Generates academic-quality figures in PNG format:
- Hit ratio vs buffer size across workloads
- Simulated I/O latency comparison
- Ablation study bar charts
- Phase transition timeline
- Workload statistical characteristics
- Disk I/O comparison
- Analytical switching cost curves
- Performance heatmap
- Parameter sensitivity plots
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Sequence

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np

from memora.decision.cost_model import SwitchCostModel

__all__ = [
    "plot_hit_ratio_vs_buffer_size",
    "plot_latency_comparison",
    "plot_ablation_study",
    "plot_workload_characteristics",
    "plot_phase_transitions",
    "plot_disk_io_comparison",
    "plot_switch_cost_curves",
    "plot_performance_heatmap",
    "plot_sensitivity_analysis",
]

logger = logging.getLogger(__name__)

# Academic visual styling
plt.rcParams.update({
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.titlesize": 14,
    "grid.alpha": 0.4,
    "grid.linestyle": "--",
})


def plot_hit_ratio_vs_buffer_size(
    matrix_results: Sequence[dict[str, Any]],
    figures_dir: str | Path = "figures",
) -> list[Path]:
    """Plot Hit Ratio vs Buffer Size curves for each workload."""
    fig_path = Path(figures_dir)
    fig_path.mkdir(parents=True, exist_ok=True)

    # Group by workload
    workloads: dict[str, dict[str, list[tuple[int, float]]]] = {}
    for row in matrix_results:
        w = row["workload"]
        p = row["policy_name"]
        b = row["buffer_size"]
        hr = row["hit_ratio"]

        workloads.setdefault(w, {}).setdefault(p, []).append((b, hr))

    color_map = {
        "lru": "#1f77b4",
        "lfu": "#2ca02c",
        "fifo": "#d62728",
        "memora": "#9467bd",
    }
    marker_map = {"lru": "o", "lfu": "s", "fifo": "^", "memora": "D"}

    saved_files: list[Path] = []

    for w_name, pol_data in workloads.items():
        fig, ax = plt.subplots(figsize=(7, 4.5), dpi=150)

        for p_name, pts in pol_data.items():
            pts_sorted = sorted(pts, key=lambda x: x[0])
            xs = [x[0] for x in pts_sorted]
            ys = [x[1] for x in pts_sorted]
            ax.plot(
                xs,
                ys,
                label=p_name.upper(),
                color=color_map.get(p_name.lower(), "#333333"),
                marker=marker_map.get(p_name.lower(), "o"),
                linewidth=2.0 if p_name.lower() == "memora" else 1.5,
                markersize=6,
            )

        ax.set_title(f"Hit Ratio vs Buffer Pool Size ({w_name.replace('_', ' ').title()})")
        ax.set_xlabel("Buffer Pool Size (Frames)")
        ax.set_ylabel("Hit Ratio")
        ax.set_ylim(-0.02, 1.02)
        ax.grid(True)
        ax.legend(loc="lower right", framealpha=0.9)

        out_file = fig_path / f"hit_ratio_{w_name}.png"
        fig.tight_layout()
        fig.savefig(out_file)
        plt.close(fig)
        saved_files.append(out_file)

    return saved_files


def plot_latency_comparison(
    matrix_results: Sequence[dict[str, Any]],
    figures_dir: str | Path = "figures",
    buffer_size: int = 256,
) -> Path:
    """Plot total simulated I/O latency comparison across policies."""
    fig_path = Path(figures_dir)
    fig_path.mkdir(parents=True, exist_ok=True)

    filtered = [r for r in matrix_results if r.get("buffer_size") == buffer_size]
    if not filtered:
        filtered = list(matrix_results)

    workloads = sorted(list({r["workload"] for r in filtered}))
    policies = sorted(list({r["policy_name"] for r in filtered}))

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    x = np.arange(len(workloads))
    bar_width = 0.8 / len(policies)

    color_map = {
        "lru": "#1f77b4",
        "lfu": "#2ca02c",
        "fifo": "#d62728",
        "memora": "#9467bd",
    }

    for idx, p in enumerate(policies):
        latencies = []
        for w in workloads:
            match = next(
                (r for r in filtered if r["workload"] == w and r["policy_name"] == p),
                None,
            )
            lat = match["total_simulated_latency_ms"] if match else 0.0
            latencies.append(lat)

        offset = (idx - (len(policies) - 1) / 2) * bar_width
        ax.bar(
            x + offset,
            latencies,
            bar_width,
            label=p.upper(),
            color=color_map.get(p.lower(), "#555555"),
            alpha=0.9,
        )

    ax.set_title(f"Modeled Disk I/O Latency across Workloads (Buffer Size = {buffer_size})")
    ax.set_xlabel("Workload")
    ax.set_ylabel("Total Simulated Latency (ms)")
    ax.set_xticks(x)
    ax.set_xticklabels([w.replace("_", "\n") for w in workloads])
    ax.grid(True, axis="y")
    ax.legend(framealpha=0.9)

    out_file = fig_path / "latency_comparison.png"
    fig.tight_layout()
    fig.savefig(out_file)
    plt.close(fig)
    return out_file


def plot_disk_io_comparison(
    matrix_results: Sequence[dict[str, Any]],
    figures_dir: str | Path = "figures",
    buffer_size: int = 256,
) -> Path:
    """Plot total disk I/O operations (reads + writes) across policies."""
    fig_path = Path(figures_dir)
    fig_path.mkdir(parents=True, exist_ok=True)

    filtered = [r for r in matrix_results if r.get("buffer_size") == buffer_size]
    if not filtered:
        filtered = list(matrix_results)

    workloads = sorted(list({r["workload"] for r in filtered}))
    policies = sorted(list({r["policy_name"] for r in filtered}))

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    x = np.arange(len(workloads))
    bar_width = 0.8 / len(policies)

    color_map = {
        "lru": "#1f77b4",
        "lfu": "#2ca02c",
        "fifo": "#d62728",
        "memora": "#9467bd",
    }

    for idx, p in enumerate(policies):
        ios = []
        for w in workloads:
            match = next(
                (r for r in filtered if r["workload"] == w and r["policy_name"] == p),
                None,
            )
            val = match["total_disk_io"] if match else 0
            ios.append(val)

        offset = (idx - (len(policies) - 1) / 2) * bar_width
        ax.bar(
            x + offset,
            ios,
            bar_width,
            label=p.upper(),
            color=color_map.get(p.lower(), "#555555"),
            alpha=0.9,
        )

    ax.set_title(f"Total Disk I/O Operations across Workloads (Buffer Size = {buffer_size})")
    ax.set_xlabel("Workload")
    ax.set_ylabel("Total Disk I/O (Reads + Writes)")
    ax.set_xticks(x)
    ax.set_xticklabels([w.replace("_", "\n") for w in workloads])
    ax.grid(True, axis="y")
    ax.legend(framealpha=0.9)

    out_file = fig_path / "disk_io_comparison.png"
    fig.tight_layout()
    fig.savefig(out_file)
    plt.close(fig)
    return out_file


def plot_ablation_study(
    ablation_results: Sequence[dict[str, Any]],
    figures_dir: str | Path = "figures",
) -> Path:
    """Plot hit ratio and switch count for ablation configurations."""
    fig_path = Path(figures_dir)
    fig_path.mkdir(parents=True, exist_ok=True)

    names = [r["ablation"].replace("_", "\n") for r in ablation_results]
    hit_ratios = [r["hit_ratio"] for r in ablation_results]
    switches = [r["switches"] for r in ablation_results]

    x = np.arange(len(names))
    fig, ax1 = plt.subplots(figsize=(8, 4.5), dpi=150)

    color1 = "#9467bd"
    ax1.bar(x - 0.15, hit_ratios, 0.3, label="Hit Ratio", color=color1, alpha=0.85)
    ax1.set_ylabel("Hit Ratio", color=color1)
    ax1.set_ylim(0, 1.0)
    ax1.tick_params(axis="y", labelcolor=color1)

    ax2 = ax1.twinx()
    color2 = "#d62728"
    ax2.bar(x + 0.15, switches, 0.3, label="Policy Switches", color=color2, alpha=0.85)
    ax2.set_ylabel("Number of Switches", color=color2)
    ax2.tick_params(axis="y", labelcolor=color2)

    ax1.set_xticks(x)
    ax1.set_xticklabels(names)
    ax1.set_title("MEMORA Component Ablation Study (Phase-Changing Workload)")
    ax1.grid(True, axis="y")

    out_file = fig_path / "ablation_study.png"
    fig.tight_layout()
    fig.savefig(out_file)
    plt.close(fig)
    return out_file


def plot_workload_characteristics(
    profiles: dict[str, dict[str, float]],
    figures_dir: str | Path = "figures",
) -> Path:
    """Plot statistical characteristics across workloads."""
    fig_path = Path(figures_dir)
    fig_path.mkdir(parents=True, exist_ok=True)

    w_names = list(profiles.keys())
    entropy = [profiles[w].get("entropy", 0.0) for w in w_names]
    seq = [profiles[w].get("sequentiality", 0.0) for w in w_names]
    reuse = [profiles[w].get("mean_reuse_distance", 0.0) for w in w_names]

    x = np.arange(len(w_names))
    width = 0.25

    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=150)
    ax.bar(x - width, entropy, width, label="Entropy (bits)", color="#1f77b4")
    ax.bar(x, seq, width, label="Sequentiality Ratio", color="#2ca02c")
    max_r = max(reuse) if max(reuse) > 0 else 1.0
    norm_reuse = [r / max_r for r in reuse]
    ax.bar(x + width, norm_reuse, width, label=f"Reuse Dist (norm, max={max_r:.0f})", color="#ff7f0e")

    ax.set_title("Workload Statistical Profiles")
    ax.set_xticks(x)
    ax.set_xticklabels([w.replace("_", "\n") for w in workloads_names(w_names)])
    ax.grid(True, axis="y")
    ax.legend(framealpha=0.9)

    out_file = fig_path / "workload_profiles.png"
    fig.tight_layout()
    fig.savefig(out_file)
    plt.close(fig)
    return out_file


def workloads_names(names: list[str]) -> list[str]:
    return [n.replace("_", "\n") for n in names]


def plot_phase_transitions(
    trace_records: Sequence[Any],
    phase_history: Sequence[Any],
    switch_history: Sequence[Any],
    figures_dir: str | Path = "figures",
) -> Path:
    """Plot timeline of page accesses, detected phase shifts, and switches."""
    fig_path = Path(figures_dir)
    fig_path.mkdir(parents=True, exist_ok=True)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, dpi=150)

    ts = [getattr(r, "timestamp", i) for i, r in enumerate(trace_records)]
    pids = [getattr(r, "page_id", 0) for r in trace_records]
    ax1.scatter(ts, pids, s=1, color="#333333", alpha=0.3, label="Accesses")
    ax1.set_ylabel("Page ID")
    ax1.set_title("Streaming Accesses & Detected Phase Shifts")
    ax1.grid(True)

    for p in phase_history:
        ax1.axvline(
            p.timestamp,
            color="#d62728",
            linestyle="--",
            alpha=0.8,
            linewidth=1.5,
        )
        ax1.text(
            p.timestamp,
            max(pids) * 0.9 if pids else 100,
            f" {p.detected_phase}",
            color="#d62728",
            rotation=90,
            fontsize=8,
        )

    switch_ts = [s.timestamp for s in switch_history if s.accepted]
    switch_labels = [f"{s.previous_policy}->{s.new_policy}" for s in switch_history if s.accepted]
    if switch_ts:
        ax2.scatter(switch_ts, [1] * len(switch_ts), color="#9467bd", marker="D", s=80, label="Policy Switch")
        for st, lbl in zip(switch_ts, switch_labels):
            ax2.annotate(lbl, (st, 1.05), fontsize=8, ha="center")
    ax2.set_yticks([])
    ax2.set_ylim(0.5, 1.5)
    ax2.set_xlabel("Access Logical Timestamp")
    ax2.set_ylabel("Events")
    ax2.grid(True)
    ax2.legend(loc="upper right")

    out_file = fig_path / "phase_timeline.png"
    fig.tight_layout()
    fig.savefig(out_file)
    plt.close(fig)
    return out_file


def plot_switch_cost_curves(
    figures_dir: str | Path = "figures",
) -> Path:
    """Plot analytical switching cost components as a function of buffer pool size."""
    fig_path = Path(figures_dir)
    fig_path.mkdir(parents=True, exist_ok=True)

    cost_model = SwitchCostModel()
    buffer_sizes = np.linspace(16, 1024, 100)
    window_size = 1000

    cold_penalties = []
    init_penalties = []
    total_costs = []

    for b in buffer_sizes:
        ratio = min(1.0, float(b) / window_size)
        c_cold = cost_model.config.cold_miss_fraction * ratio * 0.1
        c_init = cost_model.config.init_overhead_fraction * ratio
        c_fixed = cost_model.config.switch_overhead_fixed
        cold_penalties.append(c_cold)
        init_penalties.append(c_init)
        total_costs.append(c_cold + c_init + c_fixed)

    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=150)
    ax.plot(buffer_sizes, total_costs, label="Total Switching Cost (κ)", color="#d62728", linewidth=2.0)
    ax.plot(buffer_sizes, cold_penalties, label="Cold Miss Penalty", color="#ff7f0e", linestyle="--")
    ax.plot(buffer_sizes, init_penalties, label="State Init Penalty", color="#1f77b4", linestyle=":")
    ax.axhline(cost_model.config.switch_overhead_fixed, label="Fixed Overhead", color="#7f7f7f", linestyle="-.")

    ax.set_title("Analytical Switching Cost vs Buffer Pool Size (W=1000)")
    ax.set_xlabel("Buffer Pool Size (Frames)")
    ax.set_ylabel("Hit-Ratio Deduction Penalty")
    ax.grid(True)
    ax.legend(loc="upper left")

    out_file = fig_path / "switching_cost_model.png"
    fig.tight_layout()
    fig.savefig(out_file)
    plt.close(fig)
    return out_file


def plot_performance_heatmap(
    matrix_results: Sequence[dict[str, Any]],
    figures_dir: str | Path = "figures",
    buffer_size: int = 256,
) -> Path:
    """Plot 2D heatmap of policy hit ratios across workloads."""
    fig_path = Path(figures_dir)
    fig_path.mkdir(parents=True, exist_ok=True)

    filtered = [r for r in matrix_results if r.get("buffer_size") == buffer_size]
    if not filtered:
        filtered = list(matrix_results)

    workloads = sorted(list({r["workload"] for r in filtered}))
    policies = ["lru", "lfu", "fifo", "memora"]

    grid = np.zeros((len(workloads), len(policies)))
    for i, w in enumerate(workloads):
        for j, p in enumerate(policies):
            match = next((r for r in filtered if r["workload"] == w and r["policy_name"] == p), None)
            grid[i, j] = match["hit_ratio"] if match else 0.0

    fig, ax = plt.subplots(figsize=(7, 5), dpi=150)
    im = ax.imshow(grid, cmap="YlGnBu", aspect="auto", vmin=0.0, vmax=1.0)

    ax.set_xticks(np.arange(len(policies)))
    ax.set_yticks(np.arange(len(workloads)))
    ax.set_xticklabels([p.upper() for p in policies])
    ax.set_yticklabels([w.replace("_", " ").title() for w in workloads])

    # Annotate cell values
    for i in range(len(workloads)):
        for j in range(len(policies)):
            val = grid[i, j]
            color = "white" if val > 0.6 else "black"
            ax.text(j, i, f"{val:.3f}", ha="center", va="center", color=color, fontweight="bold")

    ax.set_title(f"Policy Hit Ratio Heatmap (Buffer Size = {buffer_size})")
    fig.colorbar(im, ax=ax, label="Hit Ratio")

    out_file = fig_path / "performance_heatmap.png"
    fig.tight_layout()
    fig.savefig(out_file)
    plt.close(fig)
    return out_file


def plot_sensitivity_analysis(
    sensitivity_results: Sequence[dict[str, Any]],
    figures_dir: str | Path = "figures",
) -> list[Path]:
    """Plot sensitivity sweeps for window size, phase threshold, and cooldown."""
    fig_path = Path(figures_dir)
    fig_path.mkdir(parents=True, exist_ok=True)

    by_sweep: dict[str, list[dict[str, Any]]] = {}
    for r in sensitivity_results:
        st = r.get("sweep_type", "unknown")
        by_sweep.setdefault(st, []).append(r)

    saved = []
    for sweep_type, rows in by_sweep.items():
        rows_sorted = sorted(rows, key=lambda x: x["sweep_param"])
        params = [r["sweep_param"] for r in rows_sorted]
        hrs = [r["hit_ratio"] for r in rows_sorted]
        sws = [r["switches"] for r in rows_sorted]

        fig, ax1 = plt.subplots(figsize=(7, 4), dpi=150)
        color1 = "#1f77b4"
        ax1.plot(params, hrs, marker="o", color=color1, linewidth=2.0, label="Hit Ratio")
        ax1.set_xlabel(sweep_type.replace("_", " ").title())
        ax1.set_ylabel("Hit Ratio", color=color1)
        ax1.tick_params(axis="y", labelcolor=color1)
        ax1.grid(True)

        ax2 = ax1.twinx()
        color2 = "#d62728"
        ax2.bar(params, sws, width=(max(params) - min(params) + 1) * 0.05 if max(params) > min(params) else 1,
                color=color2, alpha=0.35, label="Switches")
        ax2.set_ylabel("Policy Switches", color=color2)
        ax2.tick_params(axis="y", labelcolor=color2)

        ax1.set_title(f"Sensitivity Analysis: {sweep_type.replace('_', ' ').title()}")
        out_file = fig_path / f"sensitivity_{sweep_type}.png"
        fig.tight_layout()
        fig.savefig(out_file)
        plt.close(fig)
        saved.append(out_file)

    return saved
