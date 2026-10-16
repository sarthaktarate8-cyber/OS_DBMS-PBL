"""MEMORA End-to-End Demonstration Script.

Runs a multi-phase dynamic workload against:
- Static LRU
- Static LFU
- Static FIFO
- Adaptive MEMORA

Outputs live transition events, metrics comparison table, and generates timeline plot.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add src to path if executed standalone
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from memora.adaptive.controller import AdaptiveBufferManager, AdaptiveConfig
from memora.adaptive.strategies import create_policy
from memora.core.buffer_pool import BufferPool
from memora.decision.engine import CostBenefitEngine, EngineConfig
from memora.detector.phase_detector import PhaseDetector
from memora.metrics.collector import MetricsCollector
from memora.simulator.replay_engine import TraceReplayEngine
from memora.simulator.trace_loader import TraceLoader
from memora.visualization.plots import plot_phase_transitions
from memora.workloads.generators import generate_phase_transition

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MEMORA-Demo")


def main() -> None:
    print("=" * 70)
    print("      MEMORA — Saviours of Memory: Adaptive DBMS Buffer Pool Demo      ")
    print("=" * 70)
    print()

    buffer_size = 64
    total_length = 6000

    print(f"[*] Generating multi-phase workload (length={total_length} accesses)...")
    print("    Phase 1: Sequential Scan (pages 0-300)")
    print("    Phase 2: Skewed Zipfian Frequency (pages 500-600, alpha=1.8)")
    print("    Phase 3: Recency-heavy Temporal Locality (pages 700-800, hot=90%)")
    print("    Phase 4: Uniform Random (pages 1000-1500)")

    trace = generate_phase_transition(
        phases=[
            {"type": "sequential", "length": 0.25, "num_pages": 300, "scan_length": 50},
            {"type": "frequency_heavy", "length": 0.25, "num_pages": 100, "zipf_alpha": 1.8},
            {"type": "recency_heavy", "length": 0.25, "num_pages": 100, "hot_fraction": 0.1, "hot_weight": 0.9},
            {"type": "random_uniform", "length": 0.25, "num_pages": 500},
        ],
        total_length=total_length,
        seed=42,
    )

    print(f"[*] Trace ready: {len(trace)} access records.")
    print(f"[*] Buffer pool capacity: {buffer_size} frames.")
    print()

    results = {}

    # 1. Run Static Baselines
    for policy_name in ("fifo", "lfu", "lru"):
        print(f"[*] Evaluating baseline policy: {policy_name.upper()}...")
        policy = create_policy(policy_name)
        metrics = MetricsCollector(policy_name=policy_name)
        pool = BufferPool(size=buffer_size, policy=policy, metrics=metrics)
        engine = TraceReplayEngine(pool, TraceLoader(trace), metrics)
        res = engine.run()
        results[policy_name] = res

    # 2. Run Adaptive MEMORA
    print("[*] Evaluating Adaptive MEMORA...")
    m_metrics = MetricsCollector(policy_name="memora")
    m_pool = BufferPool(size=buffer_size, policy=create_policy("fifo"), metrics=m_metrics)
    detector = PhaseDetector(
        window_size=500,
        step_size=250,
        overlap=True,
        phase_threshold=0.35,
        confidence_threshold=0.35,
        min_windows_before_detect=2,
    )
    decision_engine = CostBenefitEngine(config=EngineConfig(minimum_net_benefit=0.015))
    manager = AdaptiveBufferManager(
        buffer_pool=m_pool,
        detector=detector,
        decision_engine=decision_engine,
        metrics=m_metrics,
        config=AdaptiveConfig(cooldown_accesses=400),
    )

    m_metrics.start()
    for r in trace:
        manager.access(r)
    m_metrics.stop()
    results["memora"] = manager.snapshot()

    print()
    print("=" * 70)
    print("                      EXPERIMENTAL BENCHMARK RESULTS                   ")
    print("=" * 70)
    print(f"{'Policy':<10} | {'Hit Ratio':<12} | {'Disk Reads':<12} | {'Disk Writes':<12} | {'Switches':<10}")
    print("-" * 70)
    for p_name, snap in results.items():
        print(
            f"{snap.policy_name.upper():<10} | "
            f"{snap.hit_ratio * 100.0:>8.2f} %   | "
            f"{snap.disk_reads:>10}   | "
            f"{snap.disk_writes:>10}   | "
            f"{snap.switches:>8}"
        )
    print("=" * 70)
    print()

    # Switches breakdown
    switches = manager.switch_history
    accepted = [s for s in switches if s.accepted]
    print(f"[*] MEMORA executed {len(accepted)} dynamic policy switches:")
    for s in accepted:
        print(f"    - Access {s.timestamp:>5}: {s.previous_policy.upper()} -> {s.new_policy.upper()} "
              f"(Phase: {s.triggered_by}, Net Benefit: +{s.net_benefit:.4f})")

    # Generate plot
    figures_dir = Path("figures")
    plot_file = plot_phase_transitions(
        trace_records=trace,
        phase_history=manager.phase_history,
        switch_history=manager.switch_history,
        figures_dir=figures_dir,
    )
    print(f"\n[+] Timeline figure generated: {plot_file}")
    print("\nDemo completed successfully!")


if __name__ == "__main__":
    main()
