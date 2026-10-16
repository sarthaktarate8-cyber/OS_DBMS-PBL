"""PostgreSQL trace generator, query log bridge, and benchmark comparator.

Bridges real-world PostgreSQL execution patterns into MEMORA:
1. PostgresBenchTraceGenerator: Generates realistic TPC-B (pgbench) transactional
   and mixed OLTP/OLAP access traces modeled on PostgreSQL catalog structures.
2. PostgresLogTraceParser: Parses PostgreSQL query statement sequences into
   block-level access traces.
3. PostgresComparator: Runs identical traces through PostgreSQL Clock-Sweep,
   LRU, LFU, FIFO, and MEMORA to provide rigorous empirical validation.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from memora.adaptive.controller import AdaptiveBufferManager, AdaptiveConfig
from memora.core.buffer_pool import BufferPool
from memora.core.types import AccessRecord, Operation
from memora.decision.engine import CostBenefitEngine
from memora.detector.phase_detector import PhaseDetector
from memora.metrics.collector import MetricsCollector, SimulationMetrics
from memora.policies.clock import ClockPolicy
from memora.policies.fifo import FIFOPolicy
from memora.policies.lfu import LFUPolicy
from memora.policies.lru import LRUPolicy
from memora.simulator.replay_engine import TraceReplayEngine

__all__ = [
    "PgBenchTraceConfig",
    "PostgresBenchTraceGenerator",
    "PostgresLogTraceParser",
    "PostgresComparator",
    "PostgresBenchmarkResult",
]

logger = logging.getLogger(__name__)


@dataclass
class PgBenchTraceConfig:
    """Configuration for synthetic pgbench (TPC-B) trace generation."""
    num_transactions: int = 2000
    scale_factor: int = 10
    zipf_alpha: float = 1.2
    include_analytical_scans: bool = True
    analytical_scan_interval: int = 400
    scan_length_pages: int = 50
    seed: int = 42


class PostgresBenchTraceGenerator:
    """Generates access traces matching PostgreSQL pgbench (TPC-B) workload profiles.

    Table layout (pages mapped deterministically):
    - Branch pages: [1 .. scale_factor] (ultra-hot working set)
    - Teller pages: [100 .. 100 + scale_factor * 10] (hot working set)
    - Account pages: [1000 .. 1000 + scale_factor * 500] (skewed Zipfian distribution)
    - History pages: [8000 .. 8100] (sequential append-only writes)
    - Analytical scan pages: [9000 .. 9500] (sequential table scans)
    """

    def __init__(self, config: Optional[PgBenchTraceConfig] = None) -> None:
        self._cfg = config or PgBenchTraceConfig()
        self._rng = random.Random(self._cfg.seed)

    def generate(self) -> list[AccessRecord]:
        """Generate access records replicating pgbench transaction cycles."""
        records: list[AccessRecord] = []
        ts = 1

        scale = max(1, self._cfg.scale_factor)
        branch_max = max(1, scale)
        teller_max = max(1, scale * 10)
        account_max = max(10, scale * 500)

        # Precompute Zipfian weights for accounts
        weights = [1.0 / (i ** self._cfg.zipf_alpha) for i in range(1, account_max + 1)]
        sum_w = sum(weights)
        cum_weights = []
        cum = 0.0
        for w in weights:
            cum += w / sum_w
            cum_weights.append(cum)

        history_cursor = 8000

        for txn_idx in range(1, self._cfg.num_transactions + 1):
            # Analytical scan injection (OLTP + OLAP phase shift)
            if (
                self._cfg.include_analytical_scans
                and txn_idx % self._cfg.analytical_scan_interval == 0
            ):
                scan_start = 9000 + (txn_idx % 200)
                for p in range(scan_start, scan_start + self._cfg.scan_length_pages):
                    records.append(
                        AccessRecord(
                            page_id=p,
                            operation=Operation.READ,
                            timestamp=ts,
                            query_id=f"OLAP_SCAN_{txn_idx}",
                        )
                    )
                    ts += 1

            # Standard pgbench TPC-B transaction:
            # 1. Update Account (Zipfian read + write)
            r = self._rng.random()
            # Fast binary search or linear search for account page
            acc_offset = 0
            for idx, cw in enumerate(cum_weights):
                if r <= cw:
                    acc_offset = idx
                    break
            acc_page = 1000 + acc_offset

            records.append(
                AccessRecord(
                    page_id=acc_page,
                    operation=Operation.READ,
                    timestamp=ts,
                    query_id=f"TXN_{txn_idx}",
                )
            )
            ts += 1
            records.append(
                AccessRecord(
                    page_id=acc_page,
                    operation=Operation.WRITE,
                    timestamp=ts,
                    query_id=f"TXN_{txn_idx}",
                )
            )
            ts += 1

            # 2. Update Teller (Hot read + write)
            teller_page = 100 + self._rng.randint(0, teller_max - 1)
            records.append(
                AccessRecord(
                    page_id=teller_page,
                    operation=Operation.READ,
                    timestamp=ts,
                    query_id=f"TXN_{txn_idx}",
                )
            )
            ts += 1
            records.append(
                AccessRecord(
                    page_id=teller_page,
                    operation=Operation.WRITE,
                    timestamp=ts,
                    query_id=f"TXN_{txn_idx}",
                )
            )
            ts += 1

            # 3. Update Branch (Ultra-hot read + write)
            branch_page = 1 + self._rng.randint(0, branch_max - 1)
            records.append(
                AccessRecord(
                    page_id=branch_page,
                    operation=Operation.READ,
                    timestamp=ts,
                    query_id=f"TXN_{txn_idx}",
                )
            )
            ts += 1
            records.append(
                AccessRecord(
                    page_id=branch_page,
                    operation=Operation.WRITE,
                    timestamp=ts,
                    query_id=f"TXN_{txn_idx}",
                )
            )
            ts += 1

            # 4. Insert History (Sequential append write)
            records.append(
                AccessRecord(
                    page_id=history_cursor,
                    operation=Operation.WRITE,
                    timestamp=ts,
                    query_id=f"TXN_{txn_idx}",
                )
            )
            ts += 1
            if txn_idx % 20 == 0:
                history_cursor = 8000 + ((history_cursor - 8000 + 1) % 100)

        logger.info(
            "Generated pgbench trace: %d records across %d transactions",
            len(records),
            self._cfg.num_transactions,
        )
        return records


class PostgresLogTraceParser:
    """Parses SQL queries or text log lines into simulated block-level access records."""

    def __init__(self, block_size_bytes: int = 8192) -> None:
        self._block_size = block_size_bytes

    def parse_query_sequence(
        self,
        queries: Sequence[str],
        base_page_map: Optional[dict[str, int]] = None,
    ) -> list[AccessRecord]:
        """Convert a sequence of SQL table references into simulated page accesses.

        Args:
            queries: SQL strings like 'SELECT * FROM users WHERE id = 10'.
            base_page_map: Mapping from relation name to starting page offset.
        """
        table_map = base_page_map or {
            "pgbench_accounts": 1000,
            "pgbench_tellers": 100,
            "pgbench_branches": 1,
            "pgbench_history": 8000,
            "users": 2000,
            "orders": 3000,
        }

        records: list[AccessRecord] = []
        ts = 1

        for idx, q in enumerate(queries, start=1):
            q_lower = q.lower().strip()
            is_write = q_lower.startswith(("insert", "update", "delete"))
            op = Operation.WRITE if is_write else Operation.READ

            # Identify target relation
            matched_table = "users"
            for tbl in table_map:
                if tbl in q_lower:
                    matched_table = tbl
                    break

            base_page = table_map.get(matched_table, 2000)
            page_id = base_page + (hash(q_lower) % 250)

            records.append(
                AccessRecord(
                    page_id=page_id,
                    operation=op,
                    timestamp=ts,
                    query_id=f"Q_{idx}",
                )
            )
            ts += 1

        return records


@dataclass(frozen=True)
class PostgresBenchmarkResult:
    """Performance evaluation record for a policy on a PostgreSQL workload trace."""
    policy_name: str
    buffer_size: int
    total_accesses: int
    hits: int
    misses: int
    hit_ratio: float
    disk_reads: int
    disk_writes: int
    total_disk_io: int
    switches: int = 0


class PostgresComparator:
    """Compares PostgreSQL native Clock Sweep against MEMORA and classical baselines."""

    @staticmethod
    def run_comparison(
        trace: list[AccessRecord],
        buffer_size: int = 128,
    ) -> dict[str, PostgresBenchmarkResult]:
        """Execute identical trace across Clock, LRU, LFU, FIFO, and MEMORA.

        Args:
            trace: List of AccessRecord objects.
            buffer_size: Capacity of buffer pool in frames.

        Returns:
            Dictionary mapping policy name to PostgresBenchmarkResult.
        """
        results: dict[str, PostgresBenchmarkResult] = {}

        # 1. Baseline: PostgreSQL Generalized Clock Sweep (usage count max=5)
        clock_metrics_collector = MetricsCollector(policy_name="postgres_clock")
        clock_pool = BufferPool(size=buffer_size, policy=ClockPolicy(max_usage_count=5), metrics=clock_metrics_collector)
        clock_metrics_collector.start()
        for rec in trace:
            clock_pool.access(rec)
        clock_metrics_collector.stop()
        clock_metrics = clock_metrics_collector.snapshot()
        results["postgres_clock"] = PostgresBenchmarkResult(
            policy_name="postgres_clock",
            buffer_size=buffer_size,
            total_accesses=clock_metrics.total_accesses,
            hits=clock_metrics.hits,
            misses=clock_metrics.misses,
            hit_ratio=clock_metrics.hit_ratio,
            disk_reads=clock_metrics.disk_reads,
            disk_writes=clock_metrics.disk_writes,
            total_disk_io=clock_metrics.total_disk_io,
            switches=0,
        )

        # 2. Baseline: LRU
        lru_metrics_collector = MetricsCollector(policy_name="lru")
        lru_pool = BufferPool(size=buffer_size, policy=LRUPolicy(), metrics=lru_metrics_collector)
        lru_metrics_collector.start()
        for rec in trace:
            lru_pool.access(rec)
        lru_metrics_collector.stop()
        lru_metrics = lru_metrics_collector.snapshot()
        results["lru"] = PostgresBenchmarkResult(
            policy_name="lru",
            buffer_size=buffer_size,
            total_accesses=lru_metrics.total_accesses,
            hits=lru_metrics.hits,
            misses=lru_metrics.misses,
            hit_ratio=lru_metrics.hit_ratio,
            disk_reads=lru_metrics.disk_reads,
            disk_writes=lru_metrics.disk_writes,
            total_disk_io=lru_metrics.total_disk_io,
            switches=0,
        )

        # 3. Baseline: LFU
        lfu_metrics_collector = MetricsCollector(policy_name="lfu")
        lfu_pool = BufferPool(size=buffer_size, policy=LFUPolicy(), metrics=lfu_metrics_collector)
        lfu_metrics_collector.start()
        for rec in trace:
            lfu_pool.access(rec)
        lfu_metrics_collector.stop()
        lfu_metrics = lfu_metrics_collector.snapshot()
        results["lfu"] = PostgresBenchmarkResult(
            policy_name="lfu",
            buffer_size=buffer_size,
            total_accesses=lfu_metrics.total_accesses,
            hits=lfu_metrics.hits,
            misses=lfu_metrics.misses,
            hit_ratio=lfu_metrics.hit_ratio,
            disk_reads=lfu_metrics.disk_reads,
            disk_writes=lfu_metrics.disk_writes,
            total_disk_io=lfu_metrics.total_disk_io,
            switches=0,
        )

        # 4. Baseline: FIFO
        fifo_metrics_collector = MetricsCollector(policy_name="fifo")
        fifo_pool = BufferPool(size=buffer_size, policy=FIFOPolicy(), metrics=fifo_metrics_collector)
        fifo_metrics_collector.start()
        for rec in trace:
            fifo_pool.access(rec)
        fifo_metrics_collector.stop()
        fifo_metrics = fifo_metrics_collector.snapshot()
        results["fifo"] = PostgresBenchmarkResult(
            policy_name="fifo",
            buffer_size=buffer_size,
            total_accesses=fifo_metrics.total_accesses,
            hits=fifo_metrics.hits,
            misses=fifo_metrics.misses,
            hit_ratio=fifo_metrics.hit_ratio,
            disk_reads=fifo_metrics.disk_reads,
            disk_writes=fifo_metrics.disk_writes,
            total_disk_io=fifo_metrics.total_disk_io,
            switches=0,
        )

        # 5. MEMORA: Closed-loop Adaptive Controller
        memora_metrics_collector = MetricsCollector(policy_name="memora")
        memora_pool = BufferPool(size=buffer_size, policy=LRUPolicy(), metrics=memora_metrics_collector)
        memora_detector = PhaseDetector(window_size=500, step_size=100)
        memora_engine_dec = CostBenefitEngine()
        memora_controller = AdaptiveBufferManager(
            buffer_pool=memora_pool,
            detector=memora_detector,
            decision_engine=memora_engine_dec,
            metrics=memora_metrics_collector,
            config=AdaptiveConfig(cooldown_accesses=1000),
        )

        memora_metrics_collector.start()
        for rec in trace:
            memora_controller.access(rec)
        memora_metrics_collector.stop()

        memora_metrics = memora_metrics_collector.snapshot()
        results["memora"] = PostgresBenchmarkResult(
            policy_name="memora",
            buffer_size=buffer_size,
            total_accesses=memora_metrics.total_accesses,
            hits=memora_metrics.hits,
            misses=memora_metrics.misses,
            hit_ratio=memora_metrics.hit_ratio,
            disk_reads=memora_metrics.disk_reads,
            disk_writes=memora_metrics.disk_writes,
            total_disk_io=memora_metrics.total_disk_io,
            switches=len(memora_controller.switch_history),
        )

        return results
