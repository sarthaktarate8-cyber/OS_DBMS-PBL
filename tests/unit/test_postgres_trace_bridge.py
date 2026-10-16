"""Unit tests for PostgreSQL trace generator, log parser, and policy comparator."""

import pytest
from memora.core.types import Operation
from memora.postgres.trace_bridge import (
    PgBenchTraceConfig,
    PostgresBenchTraceGenerator,
    PostgresComparator,
    PostgresLogTraceParser,
)


def test_pgbench_trace_generator_structure():
    cfg = PgBenchTraceConfig(
        num_transactions=100,
        scale_factor=5,
        include_analytical_scans=False,
        seed=123,
    )
    gen = PostgresBenchTraceGenerator(cfg)
    records = gen.generate()

    # Each transaction generates 7 records (2 account, 2 teller, 2 branch, 1 history)
    assert len(records) == 700
    assert all(r.page_id > 0 for r in records)
    assert any(r.operation == Operation.WRITE for r in records)
    assert any(r.operation == Operation.READ for r in records)


def test_pgbench_trace_with_olap_scans():
    cfg = PgBenchTraceConfig(
        num_transactions=200,
        scale_factor=2,
        include_analytical_scans=True,
        analytical_scan_interval=50,
        scan_length_pages=20,
        seed=42,
    )
    gen = PostgresBenchTraceGenerator(cfg)
    records = gen.generate()

    # 4 analytical scans of 20 pages = 80 extra records
    # 200 * 7 = 1400 transaction records
    assert len(records) == 1400 + 80
    olap_records = [r for r in records if "OLAP_SCAN" in (r.query_id or "")]
    assert len(olap_records) == 80


def test_postgres_log_trace_parser():
    parser = PostgresLogTraceParser()
    queries = [
        "SELECT * FROM pgbench_accounts WHERE aid = 100;",
        "UPDATE pgbench_tellers SET tbalance = 50 WHERE tid = 2;",
        "SELECT count(*) FROM users WHERE status = 'active';",
    ]
    records = parser.parse_query_sequence(queries)
    assert len(records) == 3
    assert records[0].operation == Operation.READ
    assert records[1].operation == Operation.WRITE
    assert records[2].operation == Operation.READ


def test_postgres_comparator_runs_all_policies():
    cfg = PgBenchTraceConfig(
        num_transactions=150,
        scale_factor=2,
        include_analytical_scans=True,
        analytical_scan_interval=50,
        scan_length_pages=15,
        seed=42,
    )
    records = PostgresBenchTraceGenerator(cfg).generate()

    results = PostgresComparator.run_comparison(records, buffer_size=64)

    assert "postgres_clock" in results
    assert "lru" in results
    assert "lfu" in results
    assert "fifo" in results
    assert "memora" in results

    clock_res = results["postgres_clock"]
    assert clock_res.total_accesses == len(records)
    assert 0.0 <= clock_res.hit_ratio <= 1.0
    assert clock_res.hits + clock_res.misses == len(records)

    memora_res = results["memora"]
    assert memora_res.total_accesses == len(records)
    assert 0.0 <= memora_res.hit_ratio <= 1.0
