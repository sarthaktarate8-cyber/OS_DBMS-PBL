"""MEMORA — 3D Cybernetic Buffer Pool Visualizer Server.

Zero-external-dependency HTTP & REST API server built on Python standard library.
Serves the 3D WebGL Frontend and exposes live PostgreSQL 17 and MEMORA telemetry.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Ensure src is on Python module search path
PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("memora.server")

# Try importing MEMORA modules
try:
    from memora.adaptive.controller import AdaptiveBufferManager, AdaptiveConfig
    from memora.decision.engine import EngineConfig
    from memora.detector.phase_detector import PhaseDetector
    from memora.postgres.collector import PostgresBufferCollector, PostgresConfig
    from memora.postgres.trace_bridge import (
        PgBenchTraceConfig,
        PostgresBenchTraceGenerator,
        PostgresComparator,
    )
    from memora.workloads.generators import (
        generate_frequency_heavy,
        generate_phase_transition,
        generate_recency_heavy,
        generate_sequential,
    )
    MEMORA_AVAILABLE = True
except Exception as e:
    logger.warning("Could not import MEMORA modules: %s", e)
    MEMORA_AVAILABLE = False


def get_live_postgres_status() -> dict[str, Any]:
    """Inspect local PostgreSQL 17 and pg_buffercache."""
    if not MEMORA_AVAILABLE:
        return {"connected": False, "error": "MEMORA python module not loaded"}

    # Attempt connection with default local credentials
    password = os.getenv("PGPASSWORD", "postgres")
    user = os.getenv("PGUSER", "postgres")
    dbname = os.getenv("PGDATABASE", "postgres")
    host = os.getenv("PGHOST", "127.0.0.1")
    port = int(os.getenv("PGPORT", "5432"))

    cfg = PostgresConfig(dbname=dbname, user=user, password=password, host=host, port=port, connect_timeout=1)
    collector = PostgresBufferCollector(cfg)

    try:
        if not collector.connect():
            return {
                "connected": False,
                "error": "PostgreSQL service reachable check failed (port 5432)",
                "host": f"{host}:{port}",
                "dbname": dbname,
            }

        stats = collector.get_database_buffer_stats()
        summary = collector.get_buffercache_summary()
        collector.close()

        return {
            "connected": True,
            "host": f"{host}:{port}",
            "dbname": dbname,
            "blks_read": stats.blks_read if stats else 0,
            "blks_hit": stats.blks_hit if stats else 0,
            "hit_ratio": stats.hit_ratio if stats else 0.0,
            "buffercache": summary or {
                "total_buffers": 16384,
                "dirty_buffers": 0,
                "clean_buffers": 16384,
                "avg_usagecount": 0.0,
            },
        }
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def run_backend_benchmark(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute end-to-end Python comparative benchmark."""
    if not MEMORA_AVAILABLE:
        return {"error": "MEMORA python module not loaded"}

    workload_type = payload.get("workload", "pgbench")
    buffer_size = int(payload.get("buffer_size", 64))
    num_records = int(payload.get("num_records", 1500))

    if workload_type == "pgbench":
        gen = PostgresBenchTraceGenerator(PgBenchTraceConfig(scale_factor=5, num_transactions=num_records))
        trace = gen.generate_trace()
    elif workload_type == "sequential":
        trace = generate_sequential(num_pages=buffer_size * 4, length=num_records)
    elif workload_type == "zipfian":
        trace = generate_frequency_heavy(num_pages=buffer_size * 4, length=num_records, zipf_alpha=1.3)
    else:  # phase_shift
        phases = [
            {"type": "sequential", "length": 0.33},
            {"type": "frequency_heavy", "length": 0.33},
            {"type": "recency_heavy", "length": 0.34},
        ]
        trace = generate_phase_transition(phases=phases, total_length=num_records)

    results = PostgresComparator.run_comparison(trace=trace, buffer_size=buffer_size)
    memora_res = results["memora"]
    clock_res = results["postgres_clock"]

    clock_io = clock_res.total_disk_io
    memora_io = memora_res.total_disk_io
    io_reduction = ((clock_io - memora_io) / clock_io * 100) if clock_io > 0 else 0.0
    hr_diff = (memora_res.hit_ratio - clock_res.hit_ratio) * 100

    return {
        "status": "success",
        "workload": workload_type,
        "buffer_size": buffer_size,
        "total_accesses": memora_res.total_accesses,
        "memora": {
            "hit_ratio": round(memora_res.hit_ratio * 100, 2),
            "hits": memora_res.hits,
            "misses": memora_res.misses,
            "disk_reads": memora_res.disk_reads,
            "disk_writes": memora_res.disk_writes,
            "total_disk_io": memora_res.total_disk_io,
            "switches": memora_res.switches,
        },
        "clock": {
            "hit_ratio": round(clock_res.hit_ratio * 100, 2),
            "hits": clock_res.hits,
            "misses": clock_res.misses,
            "disk_reads": clock_res.disk_reads,
            "disk_writes": clock_res.disk_writes,
            "total_disk_io": clock_res.total_disk_io,
        },
        "baselines": {
            name: {
                "hit_ratio": round(res.hit_ratio * 100, 2),
                "hits": res.hits,
                "misses": res.misses,
                "total_disk_io": res.total_disk_io,
            }
            for name, res in results.items()
            if name not in ("memora", "postgres_clock")
        },
        "io_reduction_pct": round(io_reduction, 2),
        "hit_ratio_improvement": round(hr_diff, 2),
    }


class MemoraHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler serving frontend assets and REST endpoints."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/pg_status":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            status_data = get_live_postgres_status()
            self.wfile.write(json.dumps(status_data).encode("utf-8"))
            return
        elif parsed.path == "/api/health":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "version": "0.1.0"}).encode("utf-8"))
            return

        # Serve static file from frontend directory
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/benchmark":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                payload = json.loads(body)
            except Exception:
                payload = {}

            res = run_backend_benchmark(payload)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        # Filter static asset noise from console
        if "/api/" in (args[0] if args else ""):
            logger.info("%s - - [%s] %s", self.client_address[0], self.log_date_time_string(), format % args)


def run_server(port: int = 8080) -> None:
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, MemoraHandler)
    logger.info("==================================================================")
    logger.info(" MEMORA 3D Cybernetic Buffer Pool Visualizer Server is running!")
    logger.info(" Open your browser at: http://localhost:%d", port)
    logger.info(" Serving 3D WebGL Client from: %s", FRONTEND_DIR)
    logger.info(" Live PostgreSQL & MEMORA REST APIs enabled at /api/*")
    logger.info("==================================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nShutting down MEMORA server gracefully...")
        httpd.server_close()


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port_arg)
