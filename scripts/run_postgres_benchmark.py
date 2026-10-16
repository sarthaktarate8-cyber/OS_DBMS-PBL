"""PostgreSQL Workload Benchmark: Native Clock Sweep vs MEMORA vs Baselines.

Generates realistic TPC-B transactional and analytical (HTAP) access traces,
evaluates buffer caching performance across multiple buffer pool sizes,
and outputs a comparative performance matrix.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Add project src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from memora.postgres.trace_bridge import (
    PgBenchTraceConfig,
    PostgresBenchTraceGenerator,
    PostgresComparator,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("pg_benchmark")


def main() -> None:
    print("=" * 78)
    print("MEMORA vs PostgreSQL Native Clock-Sweep & Baselines Benchmark")
    print("=" * 78)

    # 1. Generate TPC-B + Analytical Scans Workload (HTAP)
    cfg = PgBenchTraceConfig(
        num_transactions=3000,
        scale_factor=10,
        zipf_alpha=1.2,
        include_analytical_scans=True,
        analytical_scan_interval=300,
        scan_length_pages=80,
        seed=42,
    )
    generator = PostgresBenchTraceGenerator(cfg)
    trace = generator.generate()

    workload_path = Path("workloads/pgbench_tpbc_htap.csv")
    workload_path.parent.mkdir(parents=True, exist_ok=True)
    with open(workload_path, "w", encoding="utf-8") as f:
        f.write("timestamp,page_id,operation,query_id\n")
        for r in trace:
            op_char = "W" if r.operation.name == "WRITE" else "R"
            f.write(f"{r.timestamp},{r.page_id},{op_char},{r.query_id or ''}\n")
    print(f"Generated and saved workload trace ({len(trace)} accesses) to {workload_path}")

    buffer_sizes = [64, 128, 256, 512]
    all_results = {}

    print("\nEvaluating across buffer pool capacities:")
    for b_size in buffer_sizes:
        print(f"\n--- Buffer Pool Capacity: {b_size} frames ---")
        res = PostgresComparator.run_comparison(trace, buffer_size=b_size)
        all_results[f"B_{b_size}"] = {k: v.__dict__ for k, v in res.items()}

        print(f"{'Policy':<18} | {'Hit Ratio':<10} | {'Disk Reads':<12} | {'Disk Writes':<12} | {'Total Disk I/O':<14} | {'Switches':<8}")
        print("-" * 84)
        for policy_name in ["postgres_clock", "lru", "lfu", "fifo", "memora"]:
            r = res[policy_name]
            print(
                f"{r.policy_name:<18} | {r.hit_ratio:<10.4f} | {r.disk_reads:<12d} | "
                f"{r.disk_writes:<12d} | {r.total_disk_io:<14d} | {r.switches:<8d}"
            )

    # Save benchmark results
    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    results_file = results_dir / "postgres_clock_benchmark.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nBenchmark completed successfully. Full results saved to {results_file}")


if __name__ == "__main__":
    main()
