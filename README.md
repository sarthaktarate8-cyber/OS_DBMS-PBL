# MEMORA — Saviours of Memory

## Workload-Aware Adaptive Buffer Management for Database Systems

MEMORA is an intelligent, workload-aware buffer management system that dynamically evaluates page access patterns, detects phase shifts, and selectively transitions between eviction policies (LRU, LFU, FIFO) based on an analytical cost-benefit decision engine.

### Key Components

- **Trace-Driven Simulation Core**: High-performance buffer pool simulation supporting LRU, LFU, and FIFO eviction policies.
- **Workload Intelligence**: Sliding-window phase detector tracking frequency divergence (Jensen-Shannon), access entropy, sequentiality, and reuse distance.
- **Cost-Benefit Decision Engine**: Evaluates expected hit-ratio improvement against policy switching overheads and cold-miss penalties.
- **Anti-Thrashing Adaptive Controller**: Hysteresis, cooldown periods, and minimum net-benefit gating to ensure stability under noisy workloads.
- **Experimental Evaluation**: Benchmarking across diverse synthetic workloads (recency, frequency/Zipfian, sequential scans, mixed, phase-shifting).
- **PostgreSQL Validation**: Cross-validation against PostgreSQL buffer cache statistics via `pg_stat_statements` and `pgbench`.

### Architecture

```
Workload Trace / Real DBMS Access Stream
                  │
                  ▼
       ┌─────────────────────┐
       │     Buffer Pool     │◄────────────┐
       │ (Frames, Hit/Miss)  │             │ Policy Switch
       └──────────┬──────────┘             │ (LRU / LFU / FIFO)
                  │ Access Stream          │
                  ▼                        │
       ┌─────────────────────┐             │
       │   Phase Detector    │             │
       │ (JSD, Entropy, Seq) │             │
       └──────────┬──────────┘             │
                  │ Phase Detection Signal │
                  ▼                        │
       ┌─────────────────────┐             │
       │ Cost-Benefit Engine │─────────────┘
       │  (Net Benefit Gate) │
       └─────────────────────┘
```

### Installation & Quick Start

```bash
# Clone the repository and install dependencies
pip install -e .[dev]

# Run the test suite
pytest tests/ -v

# Run the demonstration script
python scripts/run_demo.py
```
