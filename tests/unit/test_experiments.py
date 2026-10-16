"""Unit tests for ExperimentConfig, ResultStore, and ExperimentRunner."""

import tempfile
from pathlib import Path

import pytest
from memora.core.types import AccessRecord
from memora.experiments.config import ExperimentConfig, load_experiment_config
from memora.experiments.runner import ExperimentRunner, build_workload_trace
from memora.experiments.store import ResultStore


def test_result_store_save_load_json(tmp_path: Path):
    store = ResultStore(output_dir=tmp_path)
    data = {"metric": 0.95, "policy": "memora"}
    store.save_json(data, "test.json")

    loaded = store.load_json("test.json")
    assert loaded["metric"] == 0.95
    assert loaded["policy"] == "memora"


def test_result_store_save_load_csv(tmp_path: Path):
    store = ResultStore(output_dir=tmp_path)
    rows = [
        {"policy": "lru", "hit_ratio": 0.8},
        {"policy": "fifo", "hit_ratio": 0.75},
    ]
    store.save_csv(rows, "test.csv")

    loaded = store.load_csv("test.csv")
    assert len(loaded) == 2
    assert loaded[0]["policy"] == "lru"


def test_runner_run_single(tmp_path: Path):
    cfg = ExperimentConfig(output_dir=str(tmp_path))
    runner = ExperimentRunner(config=cfg)

    trace = [AccessRecord(page_id=i % 10, timestamp=i) for i in range(100)]
    res = runner.run_single(trace=trace, policy_name="lru", buffer_size=5)

    assert res.total_accesses == 100
    assert res.hits + res.misses == 100
    assert res.policy_name == "lru"


def test_runner_build_workload_trace():
    spec = {
        "name": "seq_test",
        "generator": "sequential",
        "params": {"num_pages": 50, "scan_length": 10},
    }
    trace = build_workload_trace(spec, length=100, seed=42)
    assert len(trace) == 100
