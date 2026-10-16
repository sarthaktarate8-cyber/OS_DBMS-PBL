"""Run experimental matrix and ablation benchmarks for MEMORA.

Usage:
    python scripts/run_experiments.py [--config configs/experiments.yaml] [--length 10000]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from memora.detector.profile import compute_profile
from memora.experiments.config import load_experiment_config
from memora.experiments.runner import ExperimentRunner, build_workload_trace
from memora.experiments.store import ResultStore
from memora.visualization.plots import (
    plot_ablation_study,
    plot_disk_io_comparison,
    plot_hit_ratio_vs_buffer_size,
    plot_latency_comparison,
    plot_performance_heatmap,
    plot_sensitivity_analysis,
    plot_switch_cost_curves,
    plot_workload_characteristics,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MEMORA-Experiments")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MEMORA Experimental Evaluation")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/experiments.yaml",
        help="Path to YAML experiment configuration file",
    )
    parser.add_argument(
        "--length",
        type=int,
        default=10000,
        help="Access trace length per workload",
    )
    parser.add_argument(
        "--skip-ablations",
        action="store_true",
        help="Skip ablation evaluations",
    )
    parser.add_argument(
        "--skip-sensitivity",
        action="store_true",
        help="Skip sensitivity evaluations",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logger.info("Loading experiment config from: %s", args.config)
    cfg = load_experiment_config(args.config)
    store = ResultStore(output_dir=cfg.output_dir)
    runner = ExperimentRunner(config=cfg, store=store)

    figures_dir = Path(cfg.figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)

    # 1. Profile all workloads
    logger.info("Generating and profiling all synthetic workloads...")
    profiles = {}
    for w_spec in cfg.workloads:
        w_name = w_spec["name"]
        trace = build_workload_trace(w_spec, length=args.length, seed=cfg.seed)
        prof = compute_profile(trace, window_index=1)
        profiles[w_name] = {
            "entropy": prof.entropy,
            "sequentiality": prof.sequentiality,
            "mean_reuse_distance": prof.mean_reuse_distance,
            "distinct_pages": prof.distinct_pages,
        }
    store.save_json(profiles, "workload_profiles.json")
    plot_workload_characteristics(profiles, figures_dir=figures_dir)
    logger.info("Workload profile plot generated.")

    # 2. Run Full Experiment Matrix
    logger.info("Executing experiment matrix...")
    matrix_results = runner.run_matrix(trace_length=args.length)
    logger.info("Matrix execution complete: %d trials.", len(matrix_results))

    # 3. Generate Hit Ratio, Latency, Disk I/O, Heatmap & Cost Model Plots
    logger.info("Generating performance figures...")
    hr_plots = plot_hit_ratio_vs_buffer_size(matrix_results, figures_dir=figures_dir)
    logger.info("Generated %d hit ratio curves.", len(hr_plots))

    lat_plot = plot_latency_comparison(matrix_results, figures_dir=figures_dir, buffer_size=256)
    logger.info("Generated latency comparison: %s", lat_plot)

    io_plot = plot_disk_io_comparison(matrix_results, figures_dir=figures_dir, buffer_size=256)
    logger.info("Generated disk I/O comparison: %s", io_plot)

    cost_plot = plot_switch_cost_curves(figures_dir=figures_dir)
    logger.info("Generated switching cost curve: %s", cost_plot)

    hmap_plot = plot_performance_heatmap(matrix_results, figures_dir=figures_dir, buffer_size=256)
    logger.info("Generated performance heatmap: %s", hmap_plot)

    # 4. Run Ablation Studies
    if not args.skip_ablations:
        logger.info("Executing ablation studies...")
        ablation_results = runner.run_ablations(trace_length=args.length, buffer_size=256)
        abl_plot = plot_ablation_study(ablation_results, figures_dir=figures_dir)
        logger.info("Ablation study figure generated: %s", abl_plot)

    # 5. Run Sensitivity Analysis
    if not args.skip_sensitivity:
        logger.info("Executing sensitivity analysis sweeps...")
        sens_results = runner.run_sensitivity(trace_length=args.length, buffer_size=256)
        sens_plots = plot_sensitivity_analysis(sens_results, figures_dir=figures_dir)
        logger.info("Generated %d sensitivity plots.", len(sens_plots))

    logger.info("=" * 60)
    logger.info("All experimental benchmarks finished successfully!")
    logger.info("Results saved to: %s", cfg.output_dir)
    logger.info("Figures saved to: %s", cfg.figures_dir)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
