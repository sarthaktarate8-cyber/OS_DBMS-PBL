"""Simulation metrics collection for MEMORA.

The MetricsCollector records all observable events during a simulation run.
Metrics are reset between experiments to avoid contamination.

All latency values are in milliseconds and represent MODEL ASSUMPTIONS,
not hardware measurements. This is explicitly documented.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from memora.core.types import SwitchEvent

__all__ = ["SimulationMetrics", "MetricsCollector"]


@dataclass
class SimulationMetrics:
    """Snapshot of simulation statistics.

    Attributes:
        total_accesses: Total number of page access requests.
        hits: Accesses that found the page already in the buffer pool.
        misses: Accesses that required loading the page from disk.
        evictions: Number of pages evicted from the buffer pool.
        dirty_evictions: Evictions where a dirty page had to be written to disk.
        disk_reads: Number of disk read operations (= misses).
        disk_writes: Number of disk write operations (= dirty_evictions).
        policy_name: Name of the policy that produced these metrics.
        runtime_seconds: Wall-clock execution time of the simulation run.
        switches: Number of policy switches executed.
        simulated_read_latency_ms: Accumulated modeled disk read latency.
        simulated_write_latency_ms: Accumulated modeled disk write latency.
    """

    total_accesses: int = 0
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    dirty_evictions: int = 0
    disk_reads: int = 0
    disk_writes: int = 0
    policy_name: str = "unknown"
    runtime_seconds: float = 0.0
    switches: int = 0
    simulated_read_latency_ms: float = 0.0
    simulated_write_latency_ms: float = 0.0

    @property
    def hit_ratio(self) -> float:
        """Fraction of accesses that were hits."""
        if self.total_accesses == 0:
            return 0.0
        return self.hits / self.total_accesses

    @property
    def miss_ratio(self) -> float:
        """Fraction of accesses that were misses."""
        if self.total_accesses == 0:
            return 0.0
        return self.misses / self.total_accesses

    @property
    def total_disk_io(self) -> int:
        """Total number of disk I/O operations (reads + writes)."""
        return self.disk_reads + self.disk_writes

    @property
    def total_simulated_latency_ms(self) -> float:
        """Total modeled disk I/O latency in milliseconds."""
        return self.simulated_read_latency_ms + self.simulated_write_latency_ms

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to a clean serializable dictionary."""
        return {
            "policy_name": self.policy_name,
            "total_accesses": self.total_accesses,
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": round(self.hit_ratio, 6),
            "miss_ratio": round(self.miss_ratio, 6),
            "evictions": self.evictions,
            "dirty_evictions": self.dirty_evictions,
            "disk_reads": self.disk_reads,
            "disk_writes": self.disk_writes,
            "total_disk_io": self.total_disk_io,
            "simulated_read_latency_ms": round(self.simulated_read_latency_ms, 2),
            "simulated_write_latency_ms": round(self.simulated_write_latency_ms, 2),
            "total_simulated_latency_ms": round(self.total_simulated_latency_ms, 2),
            "switches": self.switches,
            "runtime_seconds": round(self.runtime_seconds, 4),
        }


class MetricsCollector:
    """Collects and aggregates simulation events."""

    def __init__(
        self,
        policy_name: str = "unknown",
        disk_read_latency_ms: float = 10.0,
        disk_write_latency_ms: float = 15.0,
    ) -> None:
        """Initialize the collector.

        Args:
            policy_name: Name of the active policy.
            disk_read_latency_ms: Modeled disk read latency (assumption).
            disk_write_latency_ms: Modeled disk write latency (assumption).
        """
        self._policy_name = policy_name
        self._read_latency_ms = disk_read_latency_ms
        self._write_latency_ms = disk_write_latency_ms

        self._total_accesses = 0
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._dirty_evictions = 0
        self._disk_reads = 0
        self._disk_writes = 0
        self._switches = 0
        self._sim_read_latency = 0.0
        self._sim_write_latency = 0.0

        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._elapsed_time: float = 0.0

        self._switch_history: list[SwitchEvent] = []

    def start(self) -> None:
        """Start or restart the wall-clock timer."""
        self._start_time = time.perf_counter()
        self._end_time = None

    def stop(self) -> None:
        """Stop the wall-clock timer and record duration."""
        if self._start_time is not None:
            self._end_time = time.perf_counter()
            self._elapsed_time = self._end_time - self._start_time

    def record_access(self) -> None:
        """Record an access event."""
        self._total_accesses += 1

    def record_hit(self) -> None:
        """Record a buffer hit."""
        self._hits += 1

    def record_miss(self) -> None:
        """Record a buffer miss and associated disk read latency."""
        self._misses += 1
        self._disk_reads += 1
        self._sim_read_latency += self._read_latency_ms

    def record_eviction(self, was_dirty: bool = False) -> None:
        """Record a frame eviction and optional dirty disk write."""
        self._evictions += 1
        if was_dirty:
            self._dirty_evictions += 1
            self._disk_writes += 1
            self._sim_write_latency += self._write_latency_ms

    def record_switch(self, event: Optional[SwitchEvent] = None) -> None:
        """Record a policy switch event."""
        self._switches += 1
        if event is not None:
            self._switch_history.append(event)

    @property
    def switch_history(self) -> list[SwitchEvent]:
        """Return full history of recorded policy switch events."""
        return list(self._switch_history)

    def set_policy_name(self, name: str) -> None:
        """Update the active policy name."""
        self._policy_name = name

    def snapshot(self) -> SimulationMetrics:
        """Return an immutable snapshot of current metrics."""
        runtime = self._elapsed_time
        if self._start_time is not None and self._end_time is None:
            runtime = time.perf_counter() - self._start_time

        return SimulationMetrics(
            total_accesses=self._total_accesses,
            hits=self._hits,
            misses=self._misses,
            evictions=self._evictions,
            dirty_evictions=self._dirty_evictions,
            disk_reads=self._disk_reads,
            disk_writes=self._disk_writes,
            policy_name=self._policy_name,
            runtime_seconds=runtime,
            switches=self._switches,
            simulated_read_latency_ms=self._sim_read_latency,
            simulated_write_latency_ms=self._sim_write_latency,
        )

    def reset(self) -> None:
        """Reset all metrics to initial state."""
        self._total_accesses = 0
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._dirty_evictions = 0
        self._disk_reads = 0
        self._disk_writes = 0
        self._switches = 0
        self._sim_read_latency = 0.0
        self._sim_write_latency = 0.0
        self._start_time = None
        self._end_time = None
        self._elapsed_time = 0.0
        self._switch_history.clear()
