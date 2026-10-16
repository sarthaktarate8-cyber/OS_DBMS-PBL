"""PostgreSQL buffer pool statistics collector using psycopg2.

Inspects PostgreSQL buffer cache activity via standard catalog views:
- pg_stat_database (blks_read, blks_hit)
- pg_statio_user_tables (heap_blks_read, heap_blks_hit)
- pg_buffercache extension (buffer-level frame inspection if enabled)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

import psycopg2

__all__ = ["PostgresConfig", "PostgresBufferStats", "PostgresBufferCollector"]

logger = logging.getLogger(__name__)


@dataclass
class PostgresConfig:
    """Connection parameters for target PostgreSQL instance."""
    dbname: str = "postgres"
    user: str = "postgres"
    password: Optional[str] = None
    host: str = "127.0.0.1"
    port: int = 5432
    connect_timeout: int = 2

    @classmethod
    def from_env(cls) -> PostgresConfig:
        """Populate config from standard PG environment variables."""
        return cls(
            dbname=os.getenv("PGDATABASE", "postgres"),
            user=os.getenv("PGUSER", "postgres"),
            password=os.getenv("PGPASSWORD", None),
            host=os.getenv("PGHOST", "127.0.0.1"),
            port=int(os.getenv("PGPORT", "5432")),
        )


@dataclass(frozen=True)
class PostgresBufferStats:
    """Snapshot of buffer pool metrics from PostgreSQL catalog."""
    blks_read: int
    blks_hit: int
    hit_ratio: float
    total_buffers: Optional[int] = None
    dirty_buffers: Optional[int] = None
    is_live: bool = True


class PostgresBufferCollector:
    """Connects to PostgreSQL and extracts buffer cache statistics."""

    def __init__(self, config: Optional[PostgresConfig] = None) -> None:
        self._cfg = config or PostgresConfig.from_env()
        self._conn: Optional[Any] = None

    def connect(self) -> bool:
        """Attempt connection to PostgreSQL. Returns True if successful."""
        try:
            kwargs: dict[str, Any] = {
                "dbname": self._cfg.dbname,
                "user": self._cfg.user,
                "host": self._cfg.host,
                "port": self._cfg.port,
                "connect_timeout": self._cfg.connect_timeout,
            }
            if self._cfg.password:
                kwargs["password"] = self._cfg.password

            self._conn = psycopg2.connect(**kwargs)
            logger.info("Connected to PostgreSQL on %s:%d/%s", self._cfg.host, self._cfg.port, self._cfg.dbname)
            return True
        except Exception as e:
            logger.warning("PostgreSQL connection failed: %s", e)
            self._conn = None
            return False

    def is_available(self) -> bool:
        """Check if connection is open and active."""
        if self._conn is None:
            return self.connect()
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            return False

    def get_database_buffer_stats(self) -> Optional[PostgresBufferStats]:
        """Query blks_read and blks_hit from pg_stat_database."""
        if not self.is_available() or self._conn is None:
            logger.warning("Cannot collect stats: PostgreSQL is not connected")
            return None

        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT blks_read, blks_hit
                    FROM pg_stat_database
                    WHERE datname = %s
                    """,
                    (self._cfg.dbname,),
                )
                row = cur.fetchone()
                if not row:
                    return None

                reads, hits = row[0] or 0, row[1] or 0
                total = reads + hits
                ratio = (hits / total) if total > 0 else 0.0

                return PostgresBufferStats(
                    blks_read=reads,
                    blks_hit=hits,
                    hit_ratio=round(ratio, 4),
                    is_live=True,
                )
        except Exception as e:
            logger.error("Failed to query pg_stat_database: %s", e)
            return None

    def get_buffercache_summary(self) -> Optional[dict[str, Any]]:
        """Query pg_buffercache extension for frame-level diagnostics."""
        if not self.is_available() or self._conn is None:
            return None

        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        count(*) AS total_buffers,
                        count(*) FILTER (WHERE isdirty) AS dirty_buffers,
                        avg(usagecount) AS avg_usagecount
                    FROM pg_buffercache
                    """
                )
                row = cur.fetchone()
                if row:
                    return {
                        "total_buffers": row[0],
                        "dirty_buffers": row[1],
                        "avg_usagecount": float(row[2]) if row[2] is not None else 0.0,
                    }
        except Exception as e:
            logger.debug("pg_buffercache not installed or unavailable: %s", e)
            return None

    def close(self) -> None:
        """Close connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
