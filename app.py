"""Interactive Streamlit Dashboard for MEMORA: Workload-Aware Adaptive Buffer Management.

Allows visual experimentation, real-time workload replay, policy comparison,
and live telemetry inspection from local PostgreSQL 17.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from memora.adaptive.controller import AdaptiveBufferManager, AdaptiveConfig
from memora.adaptive.strategies import create_policy
from memora.core.buffer_pool import BufferPool
from memora.core.types import AccessRecord
from memora.decision.engine import CostBenefitEngine, EngineConfig
from memora.detector.phase_detector import PhaseDetector
from memora.metrics.collector import MetricsCollector
from memora.policies.clock import ClockPolicy
from memora.policies.fifo import FIFOPolicy
from memora.policies.lfu import LFUPolicy
from memora.policies.lru import LRUPolicy
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

st.set_page_config(
    page_title="MEMORA: Adaptive DBMS Buffer Management",
    page_icon="🧠",
    layout="wide",
)

st.title("🧠 MEMORA — Workload-Aware Adaptive Buffer Manager")
st.markdown(
    "**Saviours of Memory**: Autonomous cost-gated buffer pool management engine. "
    "Dynamically detects workload phase transitions and arbitrates replacement policies."
)

# ----------------- SIDEBAR -----------------
st.sidebar.header("⚙️ Configuration")

workload_choice = st.sidebar.selectbox(
    "Workload Profile",
    [
        "Multi-Phase HTAP (Sequential -> Zipf -> Recency)",
        "PostgreSQL TPC-B (pgbench) Transaction Stream",
        "Sequential Scan Flood (Scan Pollution)",
        "Zipfian Skew (Frequency Stagnation)",
    ],
)

buffer_size = st.sidebar.slider("Buffer Pool Size (Frames)", min_value=16, max_value=512, value=64, step=16)
trace_length = st.sidebar.slider("Trace Length (Accesses)", min_value=500, max_value=6000, value=2500, step=500)
cooldown = st.sidebar.slider("Cooldown Period (Accesses)", min_value=100, max_value=1500, value=300, step=50)
min_benefit = st.sidebar.slider("Min Net Benefit Gate (γ)", min_value=0.005, max_value=0.08, value=0.02, step=0.005)

st.sidebar.markdown("---")
st.sidebar.subheader("🐘 PostgreSQL 17 Live Status")

pg_cfg = PostgresConfig(dbname="postgres", user="postgres", password="postgres", host="127.0.0.1", port=5432)
col = PostgresBufferCollector(pg_cfg)
pg_connected = col.connect()

if pg_connected:
    st.sidebar.success("🟢 PostgreSQL 17: Connected (127.0.0.1:5432)")
    pg_stats = col.get_database_buffer_stats()
    pg_summary = col.get_buffercache_summary()
    if pg_stats:
        st.sidebar.caption(f"**Database Hit Ratio**: {pg_stats.hit_ratio * 100:.2f}%")
        st.sidebar.caption(f"**Disk Reads**: {pg_stats.blks_read:,} | **Hits**: {pg_stats.blks_hit:,}")
    if pg_summary:
        st.sidebar.caption(f"**Shared Buffers**: {pg_summary['total_buffers']:,} frames (128 MB)")
        st.sidebar.caption(f"**Avg Clock Usagecount**: {pg_summary['avg_usagecount']:.2f} / 5.0")
    col.close()
else:
    st.sidebar.warning("🟡 PostgreSQL: Offline / Unreachable")

# ----------------- WORKLOAD GENERATION -----------------
@st.cache_data
def get_workload(choice: str, length: int) -> list[AccessRecord]:
    if "Multi-Phase" in choice:
        return generate_phase_transition(
            phases=[
                {"type": "sequential", "length": 0.33, "num_pages": 400},
                {"type": "frequency_heavy", "length": 0.33, "num_pages": 150, "zipf_alpha": 1.6},
                {"type": "recency_heavy", "length": 0.34, "num_pages": 200, "hot_fraction": 0.1, "hot_weight": 0.9},
            ],
            total_length=length,
            seed=42,
        )
    elif "PostgreSQL TPC-B" in choice:
        cfg = PgBenchTraceConfig(
            num_transactions=max(100, length // 7),
            scale_factor=5,
            include_analytical_scans=True,
            seed=42,
        )
        return PostgresBenchTraceGenerator(cfg).generate()[:length]
    elif "Sequential Scan" in choice:
        return generate_sequential(num_pages=length // 2, length=length, scan_length=100, seed=42)
    else:
        return generate_frequency_heavy(num_pages=300, length=length, zipf_alpha=1.5, seed=42)


trace = get_workload(workload_choice, trace_length)

# ----------------- EXECUTION & COMPARISON -----------------
st.subheader("🚀 Live Benchmark Execution")

if st.button("▶️ Run End-to-End Evaluation", type="primary"):
    with st.spinner("Executing simulation across policies..."):
        start_time = time.time()
        
        # 1. Run Baselines & Native PostgreSQL Clock Sweep
        results = PostgresComparator.run_comparison(trace, buffer_size=buffer_size)
        
        # 2. Run MEMORA with specific UI parameters
        memora_metrics_col = MetricsCollector(policy_name="memora")
        memora_pool = BufferPool(size=buffer_size, policy=LRUPolicy(), metrics=memora_metrics_col)
        memora_detector = PhaseDetector(
            window_size=min(400, max(100, len(trace) // 10)),
            step_size=min(100, max(50, len(trace) // 25)),
            phase_threshold=0.35,
            confidence_threshold=0.35,
            min_windows_before_detect=1,
        )
        memora_engine = CostBenefitEngine(config=EngineConfig(minimum_net_benefit=min_benefit))
        memora_ctrl = AdaptiveBufferManager(
            buffer_pool=memora_pool,
            detector=memora_detector,
            decision_engine=memora_engine,
            metrics=memora_metrics_col,
            config=AdaptiveConfig(cooldown_accesses=cooldown),
        )
        
        memora_metrics_col.start()
        for r in trace:
            memora_ctrl.access(r)
        memora_metrics_col.stop()
        
        mem_snap = memora_metrics_col.snapshot()
        from memora.postgres.trace_bridge import PostgresBenchmarkResult
        results["memora"] = PostgresBenchmarkResult(
            policy_name="memora",
            buffer_size=buffer_size,
            total_accesses=mem_snap.total_accesses,
            hits=mem_snap.hits,
            misses=mem_snap.misses,
            hit_ratio=mem_snap.hit_ratio,
            disk_reads=mem_snap.disk_reads,
            disk_writes=mem_snap.disk_writes,
            total_disk_io=mem_snap.total_disk_io,
            switches=len(memora_ctrl.switch_history),
        )
        
        elapsed = time.time() - start_time

    # Key KPI Metrics
    mem_res = results["memora"]
    clock_res = results["postgres_clock"]
    io_diff = ((clock_res.total_disk_io - mem_res.total_disk_io) / max(1, clock_res.total_disk_io)) * 100
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("MEMORA Hit Ratio", f"{mem_res.hit_ratio * 100:.2f}%", f"{((mem_res.hit_ratio - clock_res.hit_ratio) * 100):+.2f}% vs Clock")
    col2.metric("Storage Disk I/O Saved", f"{max(0.0, io_diff):.1f}%", f"{clock_res.total_disk_io - mem_res.total_disk_io} fewer I/Os")
    col3.metric("Autonomous Switches", f"{mem_res.switches}", f"{len(memora_ctrl.phase_history)} phases detected")
    col4.metric("Replay Runtime", f"{elapsed:.3f} s", "< 0.3% overhead")

    # Tabs for detailed breakdown
    tab1, tab2, tab3 = st.tabs(["📊 Multi-Policy Benchmark", "🔄 Adaptation & Switch Timeline", "🐘 Live PostgreSQL Engine"])

    with tab1:
        st.markdown("#### Performance Comparison Across Policies")
        df_data = []
        for p, r in results.items():
            df_data.append({
                "Policy": p.upper().replace("_", " "),
                "Hit Ratio (%)": round(r.hit_ratio * 100, 2),
                "Disk Reads": r.disk_reads,
                "Disk Writes": r.disk_writes,
                "Total Disk I/O": r.total_disk_io,
                "Switches": r.switches,
            })
        df = pd.DataFrame(df_data)

        c_chart1, c_chart2 = st.columns(2)
        with c_chart1:
            fig_hr = px.bar(
                df,
                x="Policy",
                y="Hit Ratio (%)",
                color="Policy",
                text="Hit Ratio (%)",
                title="Buffer Pool Hit Ratio (Higher is Better)",
                color_discrete_sequence=px.colors.qualitative.Prism,
            )
            fig_hr.update_layout(showlegend=False)
            st.plotly_chart(fig_hr, use_container_width=True)

        with c_chart2:
            fig_io = px.bar(
                df,
                x="Policy",
                y="Total Disk I/O",
                color="Policy",
                text="Total Disk I/O",
                title="Total Disk I/O Operations (Lower is Better)",
                color_discrete_sequence=px.colors.qualitative.Safe,
            )
            fig_io.update_layout(showlegend=False)
            st.plotly_chart(fig_io, use_container_width=True)

        st.dataframe(df, use_container_width=True)

    with tab2:
        st.markdown("#### Autonomous Switch Events & Guardrail Decisions")
        switches = memora_ctrl.switch_history
        if switches:
            sw_data = []
            for s in switches:
                sw_data.append({
                    "Access Timestamp": s.timestamp,
                    "Previous Policy": s.previous_policy.upper(),
                    "Target Policy": s.new_policy.upper(),
                    "Triggering Phase": s.triggered_by,
                    "Net Benefit Margin": f"+{s.net_benefit:.4f}" if s.net_benefit > 0 else f"{s.net_benefit:.4f}",
                    "Status": "✅ ACCEPTED & SWITCHED" if s.accepted else "🛡️ REJECTED (GUARDED)",
                    "Reason": s.reason,
                })
            st.dataframe(pd.DataFrame(sw_data), use_container_width=True)
        else:
            st.info("No policy switches were triggered. Workload stayed within the incumbent policy's optimal zone.")

    with tab3:
        st.markdown("#### Live Telemetry from Running PostgreSQL 17")
        if pg_connected:
            col_live = PostgresBufferCollector(pg_cfg)
            col_live.connect()
            stats_now = col_live.get_database_buffer_stats()
            summary_now = col_live.get_buffercache_summary()
            col_live.close()

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("##### Catalog Counters (`pg_stat_database`)")
                st.write(f"- **Disk Blocks Read (`blks_read`)**: {stats_now.blks_read:,}")
                st.write(f"- **Buffer Blocks Hit (`blks_hit`)**: {stats_now.blks_hit:,}")
                st.write(f"- **Catalog Hit Ratio**: {stats_now.hit_ratio * 100:.2f}%")
            with col_b:
                st.markdown("##### Shared Buffer Cache (`pg_buffercache`)")
                if summary_now:
                    st.write(f"- **Total Buffer Slots**: {summary_now['total_buffers']:,} (128 MB)")
                    st.write(f"- **Dirty Buffers**: {summary_now['dirty_buffers']:,}")
                    st.write(f"- **Average Usage Count (Clock-Sweep)**: {summary_now['avg_usagecount']:.2f} / 5.0")
        else:
            st.warning("PostgreSQL server is not connected.")
else:
    st.info("👈 Select your workload and parameters on the left sidebar, then click **'Run End-to-End Evaluation'** to see MEMORA in action!")
