# MEMORA Developer & Extensibility Guide

## 1. Codebase Architecture & Key Classes

```
src/memora/
├── core/
│   ├── frame.py            # BufferFrame (slot state, dirty bit, pin count, touch/load)
│   ├── buffer_pool.py      # BufferPool (fixed frames, page table, allocation, eviction)
│   └── types.py            # AccessRecord, EvictionRecord, SwitchEvent, PhaseChangeEvent
├── policies/
│   ├── base.py             # ReplacementPolicy (abstract interface)
│   ├── lru.py              # LRUPolicy (O(1) OrderedDict)
│   ├── lfu.py              # LFUPolicy (O(1) frequency buckets with LRU tie-breaking)
│   └── fifo.py             # FIFOPolicy (O(1) insertion order queue)
├── simulator/
│   ├── trace_loader.py     # TraceLoader (parses simple & structured CSV traces)
│   └── replay_engine.py    # TraceReplayEngine (drives simulation & invokes hooks)
├── workloads/
│   └── generators.py       # Deterministic synthetic generators (recency, zipf, scan, etc.)
├── detector/
│   ├── window.py           # SlidingWindowManager (rolling FIFO buffer with step stride)
│   ├── profile.py          # WorkloadProfile, compute_jsd, compute_profile
│   └── phase_detector.py   # PhaseDetector (multi-feature divergence & classification)
├── decision/
│   ├── cost_model.py       # SwitchCostModel (analytical cold-miss & initialization costs)
│   └── engine.py           # CostBenefitEngine (estimates candidate gain, net-benefit gate)
├── adaptive/
│   ├── controller.py       # AdaptiveBufferManager (coordinates adaptation, anti-thrashing)
│   └── strategies.py       # SwitchStrategy (HardSwitchStrategy, SoftSwitchStrategy)
├── metrics/
│   └── collector.py        # MetricsCollector, SimulationMetrics
├── experiments/
│   ├── config.py           # ExperimentConfig (YAML loader)
│   ├── runner.py           # ExperimentRunner (single trial, matrix, ablations)
│   └── store.py            # ResultStore (persists JSON and CSV output)
├── visualization/
│   └── plots.py            # Academic Matplotlib plotters (hit ratio, latency, ablation, timeline)
└── postgres/
    ├── collector.py        # PostgresBufferCollector (pg_stat_database, pg_buffercache)
    └── validator.py        # PostgresValidator (compares simulator vs PG ground truth)
```

---

## 2. Implementing a New Replacement Policy (Extension Point)

To integrate a new replacement policy (such as **ARC**, **2Q**, or **CLOCK**):

1. Inherit from `ReplacementPolicy` in `memora.policies.base`:
   ```python
   from memora.policies.base import ReplacementPolicy

   class ClockPolicy(ReplacementPolicy):
       def __init__(self) -> None:
           self._clock_hand = 0
           self._usage_bits = {}

       def access(self, page_id: int, timestamp: int) -> None:
           self._usage_bits[page_id] = 1

       def insert(self, page_id: int, timestamp: int) -> None:
           self._usage_bits[page_id] = 1

       def evict(self) -> Optional[int]:
           # Implement clock sweep logic
           ...

       def remove(self, page_id: int) -> None:
           self._usage_bits.pop(page_id, None)

       def contains(self, page_id: int) -> bool:
           return page_id in self._usage_bits

       def size(self) -> int:
           return len(self._usage_bits)

       def reset(self) -> None:
           self._usage_bits.clear()

       @property
       def name(self) -> str:
           return "clock"
   ```

2. Register the policy in `memora.adaptive.strategies.create_policy()`:
   ```python
   elif clean_name == "clock":
       return ClockPolicy()
   ```

3. Declare candidate switching affinities in `configs/cost_model.yaml`.

---

## 3. Running the Test Suite

```bash
# Run all unit, integration, and regression tests
python -m pytest tests/ -v

# Run specifically unit tests
python -m pytest tests/unit/ -v

# Run integration tests
python -m pytest tests/integration/ -v

# Run regression tests with hand-calculated traces
python -m pytest tests/regression/ -v
```

---

## 4. Running Scripts

```bash
# Execute end-to-end interactive demo
python scripts/run_demo.py

# Run single baseline execution
python scripts/run_baseline.py --policy lru --buffer-size 128 --length 5000

# Run MEMORA execution
python scripts/run_memora.py --buffer-size 256 --length 5000

# Run complete experimental matrix & ablations
python scripts/run_experiments.py --config configs/experiments.yaml --length 10000
```
