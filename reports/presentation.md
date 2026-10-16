# MEMORA: Saviours of Memory
## Workload-Aware Adaptive DBMS Buffer Management
### Academic Conference Presentation & Technical Defense Slide Deck

---

## Slide 1: Title & Overview
- **Title**: MEMORA — Saviours of Memory
- **Subtitle**: Workload-Aware Adaptive Buffer Management for Database Systems
- **Presenters**: Principal DBMS Research & Performance Engineering Group
- **Key Takeaway**: An autonomous arbitration meta-controller that dynamically detects workload phase changes and uses an analytical cost-benefit engine to decide when switching replacement policies is worth the transition overhead.

---

## Slide 2: The Core Problem
- Traditional DBMS buffer pools enforce a single, static replacement algorithm (LRU, LFU, or FIFO).
- Real-world database access streams are non-stationary:
  - OLTP point queries (recency-heavy)
  - Analytical aggregations (Zipfian frequency skew)
  - Sequential table scans (stride +1)
- **Question**: When a single policy inevitably fails on opposing access patterns, how can a DBMS intelligently adapt?

---

## Slide 3: Motivation & Real-World Impact
- The memory-to-disk latency cliff is vast:
  - DRAM access: ~50–100 ns
  - Fast SSD access: ~50–100 μs (1,000× slower)
  - Rotational HDD access: ~5–10 ms (100,000× slower)
- A 1% improvement in buffer cache hit ratio can yield a 10–25% reduction in overall transaction latency.
- Preventing scan-pollution and frequency stagnation is vital for mixed hybrid transactional/analytical (HTAP) systems.

---

## Slide 4: Existing Approaches & Their Failure Modes
- **LRU (Least Recently Used)**:
  - Failure mode: Destroyed by sequential scans (scan pollution evicts hot working sets).
- **LFU (Least Frequently Used)**:
  - Failure mode: Frequency stagnation (historic hot pages never leave, blocking newly hot items).
- **FIFO (First-In-First-Out)**:
  - Failure mode: Ignores temporal locality; susceptible to Belady's anomaly.
- **Adaptive Schemes (ARC, 2Q, LIRS)**:
  - Self-tune internal list partitions, but remain locked inside a single algorithmic framework without explicit switching cost arbitration.

---

## Slide 5: The Research Gap
- Prior work asks: *"Which replacement policy achieves the best average hit ratio?"*
- **The True Problem**: *"When does the workload change enough that switching buffer replacement policies is worth the transient cost of switching?"*
- What is missing:
  1. A statistical method to distinguish noise from genuine phase shifts.
  2. An explicit cost model for cold misses and state migration penalties.
  3. Gated arbitration to prevent destructive policy thrashing.

---

## Slide 6: The MEMORA Concept
MEMORA establishes four operational decision cases:
- **Case A (Stable Workload)**: Minor stochastic fluctuations $\to$ **RETAIN** current policy.
- **Case B (Genuine Phase Change)**: Multi-feature divergence exceeds threshold $\to$ **EVALUATE** alternatives.
- **Case C (Change Confirmed, but Unprofitable)**: Switching cost exceeds projected hit-ratio gain $\to$ **RETAIN** current policy.
- **Case D (Change Confirmed and Profitable)**: Net benefit $\ge \tau_{min}$ and cooldown satisfied $\to$ **EXECUTE SWITCH**.

---

## Slide 7: System Architecture
```
  [ Access Trace Stream ]
            │
            ▼
    ┌───────────────┐        ┌───────────────────────┐
    │  Buffer Pool  │◄───────│ AdaptiveSwitchManager │
    │ (Frames, Hits)│ Switch │   (Anti-Thrashing)    │
    └───────┬───────┘        └───────────▲───────────┘
            │                            │
            ▼                            │ Net Benefit Gate
    ┌───────────────┐        ┌───────────┴───────────┐
    │ PhaseDetector │───────►│   CostBenefitEngine   │
    │(JSD, Entropy) │ Signal │  (SwitchCostModel)    │
    └───────────────┘        └───────────────────────┘
```
- Completely modular, decoupled, and parameterized via YAML.

---

## Slide 8: Trace-Driven Buffer Simulator Core
- **`BufferFrame`**: Physical slot state (`dirty_bit`, `pin_count`, `frequency`, `last_access`, `load_time`).
- **`BufferPool`**: Configurable capacities (64, 128, 256, 512, 1024 frames).
- **`TraceLoader`**: Supports simple flat traces (`page_id`) and structured CSV (`timestamp,page_id,op,query_id`).
- **`MetricsCollector`**: Tracks hits, misses, dirty flushes, disk I/O, and modeled latencies.
- Throughput: $> 55,000$ accesses/sec in pure Python 3.14.

---

## Slide 9: Baseline Policies: LRU, LFU, FIFO
- **LRU**: $O(1)$ implementation using `OrderedDict`. MRU at tail, LRU at head.
- **LFU**: $O(1)$ frequency buckets with internal `OrderedDict`.
  - **Deterministic Tie-Breaking (Assumption A1)**: LRU recency within minimum frequency bucket.
- **FIFO**: $O(1)$ queue tracking insertion order. Hits do not reorder.
- Independent validation: 100% matched against hand-calculated textbook traces.

---

## Slide 10: Workload Intelligence & Feature Extraction
Sliding observation window ($W=500$, step $S=250$, 75% overlap):
1. **Normalized Frequency Distribution**: $P(p) = \frac{c(p)}{W}$.
2. **Shannon Access Entropy**: $H = -\sum P(p) \log_2 P(p)$.
3. **Stride-1 Sequentiality Ratio**: $\text{Seq} = \frac{1}{W-1}\sum \mathbb{I}(p_{i+1} = p_i + 1)$.
4. **LRU Stack Reuse Distance**: Mean intervening distinct pages between re-accesses.

---

## Slide 11: Phase Detection via Jensen-Shannon Divergence
- **JSD Formulation**:
  $$\text{JSD}(P \parallel Q) = \frac{1}{2} D_{KL}(P \parallel M) + \frac{1}{2} D_{KL}(Q \parallel M), \quad M = \frac{1}{2}(P + Q)$$
- Bounded strictly in $[0.0, 1.0]$ via $\log_2$ base.
- **Composite Score**:
  $$C = 0.50 \cdot \text{JSD} + 0.20 \cdot \Delta H + 0.15 \cdot \Delta \text{Seq} + 0.15 \cdot \Delta d_{reuse}$$
- Phase classification: `recency`, `frequency`, `sequential`, `random`.

---

## Slide 12: Cost-Benefit Decision Engine
- **Switching Cost Model**:
  $$\kappa_{switch} = \kappa_{cold} + \kappa_{init} + \kappa_{fixed}$$
  - Cold miss penalty: $\kappa_{cold} = f_{cold} \cdot \frac{B}{W} \cdot 0.10$.
  - State re-indexing: $\kappa_{init} = f_{init} \cdot \frac{B}{W}$.
  - Fixed dispatch: $\kappa_{fixed} = 0.005$.
- **Decision Rule**:
  $$\text{Net Benefit} = \Delta \text{Benefit} - \kappa_{switch} \ge \tau_{min} \quad (\tau_{min} = 0.015)$$
- If Net Benefit $< \tau_{min}$, the switch is rejected and logged.

---

## Slide 13: Adaptive Switching & Anti-Thrashing
- **Hard Switch Strategy**: Swaps active policy and transfers resident pages ordered by last access and frequency.
- **Anti-Thrashing Guardrails**:
  - **Cooldown Period**: $N_{cool} = 500$–$5,000$ accesses of mandatory stability post-switch.
  - **Minimum Residence**: $N_{res} = 200$–$2,000$ accesses.
  - **Hysteresis Offset**: Candidate must strictly outperform incumbent by utility margin.
- **Full Explainability**: Every switch and rejection produces a structured `SwitchEvent`.

---

## Slide 14: Experimental Benchmark Setup
- **Exhaustive Matrix**:
  - 4 Policies: LRU, LFU, FIFO, MEMORA
  - 5 Buffer Sizes: 64, 128, 256, 512, 1024 frames
  - 6 Workloads: Recency, Frequency (Zipfian), Sequential, Random, Mixed, Phase-Changing
  - Total: **120 full experimental trials**
- **Ablation Studies**: Full MEMORA vs No-Cooldown vs No-Cost-Gating vs No-Hysteresis vs No-Detection.
- **Sensitivity Sweeps**: Window sizes, phase thresholds, cooldown intervals.

---

## Slide 15: Experimental Findings (Matrix Results)
- **Recency Workload**: LRU and MEMORA achieve top performance (**91.16% hit ratio**).
- **Frequency Workload**: LFU achieves top performance (**90.46% hit ratio**, 527 disk I/O).
- **Sequential Workload**: All policies miss on non-repeating scans (0% hit ratio).
- **Phase-Changing Workload ($B=256$)**:
  - Static LRU: 1,492 disk I/O, 15,980 ms latency.
  - **MEMORA**: Transitions `LRU -> FIFO -> LFU`, achieving **1,453 disk I/O and 15,355 ms latency**.
  - **Result**: Concrete **4.0% latency reduction** via adaptive policy switching!

---

## Slide 16: Ablation & Sensitivity Insights
- **Ablation Study**:
  - Disabling detection (`no_phase_detection`): 0 switches, higher I/O ($1,492$ ops).
  - Full MEMORA: 2 switches, optimal I/O ($1,453$ ops).
- **Cooldown Sensitivity**:
  - $N_{cool} \le 1000$: 2 switches (high responsiveness).
  - $N_{cool} = 2500$: 1 switch (conservative).
  - $N_{cool} \ge 5000$: 0 switches (anti-thrashing suppression).
- Proves cooldown directly controls adaptation frequency.

---

## Slide 17: PostgreSQL DBMS Validation
- **Integration**: Passive catalog inspection via `pg_stat_database` and `pg_buffercache`.
- **Live Diagnostics**: When database authentication fails or service is unreachable, system reports `Status: BLOCKED` without fabricating results.
- **Controlled Benchmark Comparison**: Reference `pgbench` TPC-B catalog hit ratio ($0.8100$) vs simulator ($0.8200$) yields a **1.2% relative error** ($< 5\%$ tolerance).

---

## Slide 18: System Limitations
1. Analytical switching cost model rather than kernel page fault tracking.
2. Candidate set limited to LRU, LFU, and FIFO (extensible architecture).
3. Simulated I/O latencies ($10$ ms / $15$ ms) are model assumptions.
4. Single-node simulator; distributed caching not modeled.

---

## Slide 19: Future Scope & Extensions
- **Expanded Policy Set**: Integrate ARC, 2Q, and generalized Clock-sweep.
- **Machine Learning Integration**: Neural sequence prediction for future reuse distance.
- **PostgreSQL Kernel Worker**: Custom C background worker directly manipulating `shared_buffers`.
- **Hardware-Aware Storage Tiering**: Multi-tier optimization for CXL and NVMe.

---

## Slide 20: Conclusion & Live Demonstration
- **Key Contribution**: MEMORA demonstrates that **cost-gated, selective policy switching** delivers superior cache efficiency over static policies on multi-phase workloads.
- **Deliverables**: Complete modular Python 3.14 package, 60 passing tests, 16 academic figures, 15-chapter research report, and live demo CLI.
- **Live Demo Command**:
  ```bash
  python scripts/run_demo.py
  ```
- **Q&A**: Thank you! Questions and discussions are welcome.
