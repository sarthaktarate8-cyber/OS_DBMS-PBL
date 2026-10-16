# MEMORA Experimental Evaluation Methodology

## 1. Research Questions (RQs)

The experimental evaluation of MEMORA is designed to answer six fundamental research questions:

- **RQ1 (Arbitration vs Fixed Strategy)**: Does selective, cost-gated policy switching achieve superior hit-ratio and lower disk I/O compared to static single-policy deployments under non-stationary workloads?
- **RQ2 (Overhead Quantification)**: What computational and memory overhead is introduced by real-time sliding-window profiling, JSD divergence calculations, and cost-benefit arbitration?
- **RQ3 (Detection Accuracy)**: How accurately can the multi-feature detector identify genuine workload phase transitions while suppressing false alarms under stochastic noise?
- **RQ4 (Parameter Sensitivity)**: How sensitive is system performance to changes in observation window size ($W \in [250, 4000]$), step stride ($S$), and divergence threshold ($\theta \in [0.30, 0.90]$)?
- **RQ5 (Cost-Gating Utility)**: Under what specific workload dynamics does cost-benefit gating prevent destructive thrashing that would otherwise degrade cache throughput?
- **RQ6 (Baseline Comparative Defensibility)**: How does MEMORA perform across traditional static baselines (LRU, LFU, FIFO) across diverse buffer capacities?

---

## 2. Experimental Variables

### 2.1 Independent Variables
1. **Replacement Policy**:
   - `LRU`: Least Recently Used baseline.
   - `LFU`: Least Frequently Used baseline.
   - `FIFO`: First-In-First-Out baseline.
   - `MEMORA`: Adaptive workload-aware arbitrator.
2. **Buffer Pool Size ($B$)**:
   - $B \in \{64, 128, 256, 512, 1024\}$ frames.
3. **Workload Characteristic ($W_{type}$)**:
   - **Recency-heavy**: Geometric decay back-references to a hot set (20% pages receiving 80% accesses).
   - **Frequency-heavy (Zipfian)**: Power-law access distribution with skew parameter $\alpha = 1.2 \dots 1.8$.
   - **Sequential**: Forward scans of blocks with stride 1 (scan length 50–100 pages).
   - **Uniform Random**: Stress test with no temporal or spatial locality.
   - **Mixed**: Blended composite with parameterized probabilities.
   - **Phase-Changing**: Explicit alternating sequence: Recency $\to$ Sequential $\to$ Frequency $\to$ Random.
4. **Trace Length ($L$)**:
   - Small: $10,000$ accesses (development & fast validation).
   - Medium: $100,000$ accesses (matrix benchmarking).
   - Large: $1,000,000$ accesses (stress testing).

### 2.2 Dependent Variables (Metrics)
- **Hit Ratio ($H_r$)**: $H_r = \frac{\text{Hits}}{\text{Total Accesses}} \in [0.0, 1.0]$.
- **Miss Ratio ($M_r$)**: $M_r = 1.0 - H_r$.
- **Total Disk I/O**: $\text{Disk Reads} + \text{Disk Writes}$ (where reads = misses, writes = dirty flushes).
- **Modeled I/O Latency**: Analytical latency accumulation ($10.0$ ms / read, $15.0$ ms / dirty write).
- **Policy Switches**: Total number of executed policy transitions.
- **Wall-Clock Runtime**: Measured simulation execution time in seconds.

---

## 3. Benchmark Matrix & Ablation Design

### 3.1 Matrix Benchmark
The full factorial matrix evaluates:
$$\text{4 Policies} \times \text{5 Buffer Sizes} \times \text{6 Workloads} = 120 \text{ experimental trials}$$
All runs are performed deterministically with a fixed seed (default `seed=42`).

### 3.2 Component Ablation Studies
Conducted on the `phase_changing` workload at buffer size $B=256$:
1. **Full MEMORA**: Complete system with all guardrails enabled.
2. **No Cooldown (`cooldown_accesses=0`)**: Evaluates susceptibility to rapid re-triggering.
3. **No Cost Gating (`minimum_net_benefit=0.0`)**: Switches whenever a candidate has any positive raw benefit, ignoring switching penalties.
4. **No Hysteresis (`hysteresis_factor=0.0`)**: Removes stability margin for switching.
5. **No Phase Detection (`phase_threshold=999.0`)**: Disables adaptation (equivalent to static baseline).

### 3.3 Sensitivity Analysis Grids
- **Window Size Sweep**: $W \in [250, 500, 1000, 2000, 4000]$ accesses.
- **Phase Threshold Sweep**: $\theta_{phase} \in [0.30, 0.50, 0.60, 0.70, 0.80, 0.90]$.
- **Cooldown Interval Sweep**: $N_{cool} \in [0, 1000, 2500, 5000, 10000]$ accesses.

---

## 4. PostgreSQL Real-World Case Study Protocol

1. **Environment Setup**: Target PostgreSQL 14+ instance.
2. **Monitoring Instrumentation**:
   - Enable `pg_stat_statements` for query-level cache statistics.
   - Query `pg_stat_database` for cumulative `blks_read` and `blks_hit`.
   - Query `pg_buffercache` for frame dirty and usage count distribution.
3. **Workload Driving via `pgbench`**:
   - TPC-B-like transactions (read/write intensive).
   - Read-only OLTP benchmark (`-S`).
   - Large analytical sequential table scans (`SELECT count(*) FROM ...`).
4. **Comparison Protocol**:
   - Simulator hit ratio is juxtaposed with PostgreSQL's buffer pool hit ratio:
     $$\text{Rel Error} = \frac{|\text{HitRatio}_{sim} - \text{HitRatio}_{pg}|}{\max(\text{HitRatio}_{pg}, 10^{-4})}$$
   - Clearly delineate simulator assumptions from DBMS kernel buffer management internals.
