"""Run MEMORA adaptive buffer manager on a specified workload trace."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from memora.adaptive.controller import AdaptiveBufferManager, AdaptiveConfig
from memora.adaptive.strategies import create_policy
from memora.core.buffer_pool import BufferPool
from memora.decision.engine import CostBenefitEngine, EngineConfig
from memora.detector.phase_detector import PhaseDetector
from memora.metrics.collector import MetricsCollector
from memora.simulator.trace_loader import TraceLoader
from memora.workloads.generators import generate_phase_transition

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MEMORA Adaptive Buffer Manager")
    parser.add_argument("--buffer-size", type=int, default=256)
    parser.add_argument("--trace", type=str, default=None, help="Trace file path (optional)")
    parser.add_argument("--length", type=int, default=5000)
    args = parser.parse_args()

    if args.trace:
        loader = TraceLoader(args.trace)
        records = loader.load()
    else:
        records = generate_phase_transition(
            phases=[
                {"type": "recency_heavy", "length": 0.5, "num_pages": 500},
                {"type": "frequency_heavy", "length": 0.5, "num_pages": 500, "zipf_alpha": 1.5},
            ],
            total_length=args.length,
            seed=42,
        )

    metrics = MetricsCollector(policy_name="memora")
    pool = BufferPool(size=args.buffer_size, policy=create_policy("lru"), metrics=metrics)
    detector = PhaseDetector(window_size=500, step_size=250)
    engine = CostBenefitEngine(config=EngineConfig(minimum_net_benefit=0.02))
    manager = AdaptiveBufferManager(
        buffer_pool=pool,
        detector=detector,
        decision_engine=engine,
        metrics=metrics,
    )

    metrics.start()
    for r in records:
        manager.access(r)
    metrics.stop()

    res = manager.snapshot()
    print("\n--- MEMORA Execution Result ---")
    print(f"Total Accesses: {res.total_accesses}")
    print(f"Hit Ratio:      {res.hit_ratio * 100:.2f} %")
    print(f"Disk Reads:     {res.disk_reads}")
    print(f"Disk Writes:    {res.disk_writes}")
    print(f"Total Disk I/O: {res.total_disk_io}")
    print(f"Switches:       {res.switches}")
    print(f"Runtime:        {res.runtime_seconds:.4f} s\n")


if __name__ == "__main__":
    main()
