"""Cross-validation comparing MEMORA simulator against PostgreSQL buffer metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from memora.metrics.collector import SimulationMetrics
from memora.postgres.collector import PostgresBufferCollector, PostgresBufferStats

__all__ = ["ValidationReport", "PostgresValidator"]


@dataclass(frozen=True)
class ValidationReport:
    """Report comparing simulated performance against PostgreSQL ground truth."""
    simulated_hit_ratio: float
    postgres_hit_ratio: Optional[float]
    relative_error: Optional[float]
    is_postgres_available: bool
    status: str
    details: str


class PostgresValidator:
    """Validates simulation accuracy against PostgreSQL observations."""

    def __init__(self, collector: Optional[PostgresBufferCollector] = None) -> None:
        self._collector = collector or PostgresBufferCollector()

    def validate(
        self,
        sim_metrics: SimulationMetrics,
        pg_stats: Optional[PostgresBufferStats] = None,
    ) -> ValidationReport:
        """Compare simulated metrics against real PostgreSQL statistics.

        Args:
            sim_metrics: Simulation snapshot.
            pg_stats: Optional pre-collected PostgresBufferStats. If None, queries collector.

        Returns:
            ValidationReport detailing comparison.
        """
        if pg_stats is None:
            pg_stats = self._collector.get_database_buffer_stats()

        if pg_stats is None or not pg_stats.is_live:
            return ValidationReport(
                simulated_hit_ratio=sim_metrics.hit_ratio,
                postgres_hit_ratio=None,
                relative_error=None,
                is_postgres_available=False,
                status="BLOCKED",
                details=(
                    "PostgreSQL validation could not complete because the PostgreSQL "
                    "database was unreachable or authentication failed. The simulator "
                    "remains fully functional."
                ),
            )

        sim_hr = sim_metrics.hit_ratio
        pg_hr = pg_stats.hit_ratio
        diff = abs(sim_hr - pg_hr)
        rel_err = diff / max(pg_hr, 1e-4)

        status = "PASSED" if rel_err <= 0.25 else "WARNING"
        details = (
            f"Simulated hit ratio: {sim_hr:.4f}, PostgreSQL hit ratio: {pg_hr:.4f}. "
            f"Absolute delta: {diff:.4f}, Relative error: {rel_err * 100:.1f}%."
        )

        return ValidationReport(
            simulated_hit_ratio=round(sim_hr, 4),
            postgres_hit_ratio=round(pg_hr, 4),
            relative_error=round(rel_err, 4),
            is_postgres_available=True,
            status=status,
            details=details,
        )
