"""Run a single baseline policy (LRU, LFU, or FIFO) on a specified workload trace."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from memora.adaptive.strategies import create_policy
from memora.core.buffer_pool import BufferPool
from memora.metrics.collector import MetricsCollector
from memora.simulator.replay_engine import TraceReplayEngine
from memora.simulator.trace_loader import TraceLoader
from memora.workloads.generators import generate_recency_heavy

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run baseline policy")
    parser.add_argument("--policy", type=str, default="lru", choices=["lru", "lfu", "fifo"])
    parser.add_argument("--buffer-size", type=int, default=256)
    parser.add_argument("--trace", type=str, default=None, help="Trace file path (optional)")
    parser.add_argument("--length", type=int, default=5000)
    args = parser.parse_args()

    if args.trace:
        loader = TraceLoader(args.trace)
    else:
        records = generate_recency_heavy(length=args.length, seed=42)
        loader = TraceLoader(records)

    policy = create_policy(args.policy)
    metrics = MetricsCollector(policy_name=args.policy)
    pool = BufferPool(size=args.buffer_size, policy=policy, metrics=metrics)
    engine = TraceReplayEngine(pool, loader, metrics)

    res = engine.run()
    print(f"\n--- Baseline Execution Result ({args.policy.upper()}) ---")
    print(f"Total Accesses: {res.total_accesses}")
    print(f"Hit Ratio:      {res.hit_ratio * 100:.2f} %")
    print(f"Disk Reads:     {res.disk_reads}")
    print(f"Disk Writes:    {res.disk_writes}")
    print(f"Total Disk I/O: {res.total_disk_io}")
    print(f"Runtime:        {res.runtime_seconds:.4f} s\n")


if __name__ == "__main__":
    main()
