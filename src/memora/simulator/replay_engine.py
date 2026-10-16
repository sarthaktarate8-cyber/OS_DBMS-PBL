"""Trace Replay Engine for MEMORA.

Feeds access records from a TraceLoader into a BufferPool, invokes hooks
(e.g., adaptive controller, phase detector), and aggregates simulation metrics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from memora.core.buffer_pool import BufferPool
from memora.core.types import AccessRecord
from memora.metrics.collector import MetricsCollector, SimulationMetrics
from memora.simulator.trace_loader import TraceLoader

__all__ = ["TraceReplayEngine", "ReplayConfig"]

logger = logging.getLogger(__name__)

AccessHook = Callable[[int, AccessRecord, bool, BufferPool], None]


@dataclass
class ReplayConfig:
    """Configuration for a trace replay run."""
    max_records: Optional[int] = None
    progress_interval: int = 100_000


class TraceReplayEngine:
    """Replays access traces into a BufferPool."""

    def __init__(
        self,
        buffer_pool: BufferPool,
        trace_loader: TraceLoader,
        metrics: Optional[MetricsCollector] = None,
        config: Optional[ReplayConfig] = None,
    ) -> None:
        """Initialize the replay engine.

        Args:
            buffer_pool: The BufferPool instance to replay into.
            trace_loader: The TraceLoader providing access records.
            metrics: Optional metrics collector (defaults to buffer_pool's metrics).
            config: Optional configuration for replay limits / logging.
        """
        self._pool = buffer_pool
        self._loader = trace_loader

        if metrics is not None:
            self._metrics = metrics
            if buffer_pool._metrics is None:
                buffer_pool._metrics = metrics
        elif buffer_pool._metrics is not None:
            self._metrics = buffer_pool._metrics
        else:
            self._metrics = MetricsCollector(policy_name=buffer_pool.policy.name)
            buffer_pool._metrics = self._metrics

        self._config = config or ReplayConfig()
        self._hooks: list[AccessHook] = []

    def add_hook(self, hook: AccessHook) -> None:
        """Register a callback hook called after each page access."""
        self._hooks.append(hook)

    def run(self) -> SimulationMetrics:
        """Execute the replay run.

        Returns:
            Final SimulationMetrics snapshot.
        """
        self._metrics.start()
        records = self._loader.load()
        max_recs = self._config.max_records or len(records)
        total_to_process = min(len(records), max_recs)

        logger.info(
            "Starting replay: %d records, buffer_size=%d, policy=%s",
            total_to_process,
            self._pool.size,
            self._pool.policy.name,
        )

        for idx in range(total_to_process):
            record = records[idx]
            is_hit = self._pool.access(record)

            # Invoke registered observer hooks
            for hook in self._hooks:
                hook(self._pool.access_counter, record, is_hit, self._pool)

            if (
                self._config.progress_interval > 0
                and (idx + 1) % self._config.progress_interval == 0
            ):
                logger.info(
                    "Replay progress: %d / %d accesses (%.1f%%)",
                    idx + 1,
                    total_to_process,
                    100.0 * (idx + 1) / total_to_process,
                )

        self._metrics.stop()
        final_metrics = self._metrics.snapshot()
        logger.info(
            "Replay complete: %d accesses, hit_ratio=%.4f, disk_io=%d, runtime=%.3fs",
            final_metrics.total_accesses,
            final_metrics.hit_ratio,
            final_metrics.total_disk_io,
            final_metrics.runtime_seconds,
        )
        return final_metrics
