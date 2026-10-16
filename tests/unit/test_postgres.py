"""Unit tests for PostgreSQL validation and collector modules."""

from memora.metrics.collector import SimulationMetrics
from memora.postgres.collector import PostgresBufferCollector, PostgresBufferStats, PostgresConfig
from memora.postgres.validator import PostgresValidator, ValidationReport


def test_postgres_config_from_env(monkeypatch):
    monkeypatch.setenv("PGDATABASE", "testdb")
    monkeypatch.setenv("PGUSER", "testuser")
    monkeypatch.setenv("PGPORT", "5433")

    cfg = PostgresConfig.from_env()
    assert cfg.dbname == "testdb"
    assert cfg.user == "testuser"
    assert cfg.port == 5433


def test_postgres_validator_graceful_fallback_when_unreachable():
    # Collector with invalid credentials will fail connection gracefully
    cfg = PostgresConfig(host="127.0.0.1", port=9999, connect_timeout=1)
    collector = PostgresBufferCollector(config=cfg)
    validator = PostgresValidator(collector=collector)

    sim = SimulationMetrics(total_accesses=1000, hits=750, misses=250, policy_name="memora")
    report = validator.validate(sim)

    assert not report.is_postgres_available
    assert report.status == "BLOCKED"
    assert "PostgreSQL database was unreachable" in report.details
    assert report.simulated_hit_ratio == 0.75
    assert report.postgres_hit_ratio is None


def test_postgres_validator_comparison_with_stats():
    validator = PostgresValidator()
    sim = SimulationMetrics(total_accesses=10000, hits=8200, misses=1800, policy_name="memora")
    pg_stats = PostgresBufferStats(blks_read=1900, blks_hit=8100, hit_ratio=0.81, is_live=True)

    report = validator.validate(sim, pg_stats=pg_stats)

    assert report.is_postgres_available
    assert report.status == "PASSED"
    assert report.simulated_hit_ratio == 0.82
    assert report.postgres_hit_ratio == 0.81
    assert report.relative_error is not None
    assert report.relative_error < 0.05
