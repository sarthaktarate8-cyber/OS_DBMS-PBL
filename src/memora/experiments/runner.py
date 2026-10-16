"""Execution runner for experimental evaluation benchmarks."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Optional, Sequence

from memora.adaptive.controller import AdaptiveBufferManager, AdaptiveConfig
from memora.adaptive.strategies import create_policy
from memora.core.buffer_pool import BufferPool
from memora.core.types import AccessRecord
from memora.decision.cost_model import SwitchCostModel
from memora.decision.engine import CostBenefitEngine, EngineConfig
from memora.detector.phase_detector import PhaseDetector
from memora.experiments.config import ExperimentConfig
from memora.experiments.store import ResultStore
from memora.metrics.collector import MetricsCollector, SimulationMetrics
from memora.simulator.replay_engine import TraceReplayEngine
from memora.simulator.trace_loader import TraceLoader
from memora.workloads.generators import (
    generate_frequency_heavy,
    generate_mixed,
    generate_phase_transition,
    generate_random_uniform,
    generate_recency_heavy,
    generate_sequential,
)

__all__ = ["ExperimentRunner", "build_workload_trace"]

logger = logging.getLogger(__name__)


def build_workload_trace(
    workload_spec: dict[str, Any],
    length: int = 10000,
    seed: int = 42,
) -> list[AccessRecord]:
    """Generate access records from a workload specification dict."""
    generator = workload_spec.get("generator", "random_uniform")
    params = dict(workload_spec.get("params", {}))
    params["seed"] = seed

    if generator == "recency_heavy":
        params["length"] = length
        return generate_recency_heavy(**params)
    elif generator == "frequency_heavy":
        params["length"] = length
        return generate_frequency_heavy(**params)
    elif generator == "sequential":
        params["length"] = length
        return generate_sequential(**params)
    elif generator == "random_uniform":
        params["length"] = length
        return generate_random_uniform(**params)
    elif generator == "mixed":
        params["length"] = length
        return generate_mixed(**params)
    elif generator == "phase_transition":
        phases = params.get("phases", [])
        return generate_phase_transition(phases=phases, total_length=length, seed=seed)
    else:
        return generate_random_uniform(length=length, seed=seed)


class ExperimentRunner:
    """Orchestrates running baseline and MEMORA benchmarks."""

    def __init__(
        self,
        config: ExperimentConfig,
        store: Optional[ResultStore] = None,
    ) -> None:
        self._cfg = config
        self._store = store or ResultStore(output_dir=config.output_dir)

    def run_single(
        self,
        trace: Sequence[AccessRecord],
        policy_name: str,
        buffer_size: int,
        detector_kwargs: Optional[dict[str, Any]] = None,
        decision_kwargs: Optional[dict[str, Any]] = None,
        adaptive_kwargs: Optional[dict[str, Any]] = None,
    ) -> SimulationMetrics:
        """Run a single experiment trial with specified policy and buffer size."""
        clean_policy = policy_name.lower().strip()
        metrics = MetricsCollector(policy_name=clean_policy)

        if clean_policy in ("lru", "lfu", "fifo"):
            policy = create_policy(clean_policy)
            pool = BufferPool(size=buffer_size, policy=policy, metrics=metrics)
            loader = TraceLoader(trace)
            engine = TraceReplayEngine(pool, loader, metrics)
            return engine.run()

        elif clean_policy == "memora":
            # MEMORA adaptive setup
            initial_policy = create_policy("lru")
            pool = BufferPool(size=buffer_size, policy=initial_policy, metrics=metrics)

            default_d_kw = {
                "window_size": 500,
                "step_size": 250,
                "phase_threshold": 0.40,
                "confidence_threshold": 0.40,
            }
            if detector_kwargs:
                default_d_kw.update(detector_kwargs)
            d_kw = default_d_kw
            detector = PhaseDetector(**d_kw)

            default_dec_kw = {"minimum_net_benefit": 0.015}
            if decision_kwargs:
                default_dec_kw.update(decision_kwargs)
            dec_kw = default_dec_kw
            decision_engine = CostBenefitEngine(config=EngineConfig(**dec_kw))

            default_a_kw = {
                "cooldown_accesses": 800,
                "min_residence_accesses": 400,
                "hysteresis_factor": 0.05,
            }
            if adaptive_kwargs:
                default_a_kw.update(adaptive_kwargs)
            a_kw = default_a_kw
            manager = AdaptiveBufferManager(
                buffer_pool=pool,
                detector=detector,
                decision_engine=decision_engine,
                metrics=metrics,
                config=AdaptiveConfig(**a_kw),
            )

            metrics.start()
            for r in trace:
                manager.access(r)
            metrics.stop()
            return metrics.snapshot()

        else:
            raise ValueError(f"Unsupported policy: '{policy_name}'")

    def run_matrix(
        self,
        trace_length: int = 10000,
        buffer_sizes: Optional[Sequence[int]] = None,
        policies: Optional[Sequence[str]] = None,
    ) -> list[dict[str, Any]]:
        """Run the full experiment matrix across all workloads, buffer sizes, and policies."""
        b_sizes = buffer_sizes or self._cfg.buffer_sizes
        p_names = policies or self._cfg.policies
        workloads = self._cfg.workloads

        results: list[dict[str, Any]] = []
        total_runs = len(workloads) * len(b_sizes) * len(p_names)
        current_run = 0

        logger.info(
            "Starting matrix benchmark: %d workloads x %d sizes x %d policies = %d runs",
            len(workloads),
            len(b_sizes),
            len(p_names),
            total_runs,
        )

        for w_spec in workloads:
            w_name = w_spec.get("name", "unknown")
            trace = build_workload_trace(w_spec, length=trace_length, seed=self._cfg.seed)

            for b_size in b_sizes:
                for p_name in p_names:
                    current_run += 1
                    logger.info(
                        "[%d/%d] Running workload=%s buffer_size=%d policy=%s",
                        current_run,
                        total_runs,
                        w_name,
                        b_size,
                        p_name,
                    )
                    metrics = self.run_single(
                        trace=trace,
                        policy_name=p_name,
                        buffer_size=b_size,
                    )
                    res_dict = metrics.to_dict()
                    res_dict["workload"] = w_name
                    res_dict["buffer_size"] = b_size
                    res_dict["seed"] = self._cfg.seed
                    results.append(res_dict)

        self._store.save_json(results, "matrix_results.json")
        self._store.save_csv(results, "matrix_results.csv")
        return results

    def run_ablations(
        self,
        trace_length: int = 10000,
        buffer_size: int = 256,
    ) -> list[dict[str, Any]]:
        """Run ablation studies on phase-changing workload."""
        phase_w = next(
            (w for w in self._cfg.workloads if w.get("name") == "phase_changing"),
            {
                "name": "phase_changing",
                "generator": "phase_transition",
                "params": {
                    "phases": [
                        {"type": "recency_heavy", "length": 0.5, "num_pages": 500},
                        {"type": "frequency_heavy", "length": 0.5, "num_pages": 500, "zipf_alpha": 1.5},
                    ]
                },
            },
        )
        trace = build_workload_trace(phase_w, length=trace_length, seed=self._cfg.seed)

        base_d_kw = {"window_size": 500, "step_size": 250, "phase_threshold": 0.35, "confidence_threshold": 0.35}
        base_dec_kw = {"minimum_net_benefit": 0.015}
        base_a_kw = {"cooldown_accesses": 500, "min_residence_accesses": 200, "hysteresis_factor": 0.05}

        ablation_specs = [
            ("full_memora", base_d_kw, base_dec_kw, base_a_kw),
            ("no_cooldown", base_d_kw, base_dec_kw, {**base_a_kw, "cooldown_accesses": 0}),
            ("no_cost_gating", base_d_kw, {"minimum_net_benefit": 0.0}, base_a_kw),
            ("no_hysteresis", base_d_kw, base_dec_kw, {**base_a_kw, "hysteresis_factor": 0.0}),
            ("no_phase_detection", {**base_d_kw, "phase_threshold": 999.0}, base_dec_kw, base_a_kw),
        ]

        results = []
        for name, d_kw, dec_kw, a_kw in ablation_specs:
            logger.info("Running ablation: %s", name)
            m = self.run_single(
                trace=trace,
                policy_name="memora",
                buffer_size=buffer_size,
                detector_kwargs=d_kw,
                decision_kwargs=dec_kw,
                adaptive_kwargs=a_kw,
            )
            d = m.to_dict()
            d["ablation"] = name
            d["buffer_size"] = buffer_size
            results.append(d)

        self._store.save_json(results, "ablation_results.json")
        self._store.save_csv(results, "ablation_results.csv")
        return results

    def run_sensitivity(
        self,
        trace_length: int = 10000,
        buffer_size: int = 256,
    ) -> list[dict[str, Any]]:
        """Run sensitivity sweeps over window sizes, phase thresholds, and cooldowns."""
        phase_w = next(
            (w for w in self._cfg.workloads if w.get("name") == "phase_changing"),
            {
                "name": "phase_changing",
                "generator": "phase_transition",
                "params": {
                    "phases": [
                        {"type": "recency_heavy", "length": 0.5, "num_pages": 500},
                        {"type": "frequency_heavy", "length": 0.5, "num_pages": 500, "zipf_alpha": 1.5},
                    ]
                },
            },
        )
        trace = build_workload_trace(phase_w, length=trace_length, seed=self._cfg.seed)

        sens_cfg = self._cfg.sensitivity
        window_sizes = sens_cfg.get("window_sizes", [250, 500, 1000, 2000])
        phase_thresholds = sens_cfg.get("phase_thresholds", [0.30, 0.50, 0.70, 0.90])
        cooldown_values = sens_cfg.get("cooldown_values", [0, 1000, 5000])

        results = []
        for w_sz in window_sizes:
            m = self.run_single(
                trace=trace,
                policy_name="memora",
                buffer_size=buffer_size,
                detector_kwargs={"window_size": w_sz, "step_size": max(1, w_sz // 4)},
            )
            d = m.to_dict()
            d["sweep_type"] = "window_size"
            d["sweep_param"] = w_sz
            d["buffer_size"] = buffer_size
            results.append(d)

        for th in phase_thresholds:
            m = self.run_single(
                trace=trace,
                policy_name="memora",
                buffer_size=buffer_size,
                detector_kwargs={"phase_threshold": th, "confidence_threshold": max(0.2, th - 0.1)},
            )
            d = m.to_dict()
            d["sweep_type"] = "phase_threshold"
            d["sweep_param"] = th
            d["buffer_size"] = buffer_size
            results.append(d)

        for cd in cooldown_values:
            m = self.run_single(
                trace=trace,
                policy_name="memora",
                buffer_size=buffer_size,
                adaptive_kwargs={"cooldown_accesses": cd},
            )
            d = m.to_dict()
            d["sweep_type"] = "cooldown"
            d["sweep_param"] = cd
            d["buffer_size"] = buffer_size
            results.append(d)

        self._store.save_json(results, "sensitivity_results.json")
        self._store.save_csv(results, "sensitivity_results.csv")
        return results

