# MEMORA Algorithmic & Mathematical Formulations

This document provides formal specifications of the core algorithms and mathematical models implemented in MEMORA.

---

## 1. Baseline Replacement Algorithms

### 1.1 Least Recently Used (LRU)
- **Concept**: Evicts the page whose last access timestamp is the oldest.
- **Data Structure**: Doubly-linked hash map (`collections.OrderedDict`).
- **Complexity**:
  - `access(p)`: $O(1)$ amortized (hash lookup + node relocation to MRU tail).
  - `insert(p)`: $O(1)$ (insertion at MRU tail).
  - `evict()`: $O(1)$ (pop from LRU head).
  - `remove(p)`: $O(1)$ (hash deletion + pointer adjustment).

### 1.2 Least Frequently Used (LFU) with LRU Tie-Breaking
- **Concept**: Evicts the page with the lowest cumulative access count since load.
- **Tie-Breaking Formulation (Assumption A1)**: If a set of pages $P_{min} = \{p \in \text{Resident} \mid \text{freq}(p) = \min_q \text{freq}(q)\}$ has $|P_{min}| > 1$, evict $p^* \in P_{min}$ such that:
  $$p^* = \arg\min_{p \in P_{min}} \text{last\_access}(p)$$
- **Data Structure**:
  - `_page_freq`: Dictionary mapping `page_id -> int`.
  - `_freq_buckets`: Dictionary mapping `freq -> OrderedDict[page_id, None]`.
  - `_min_freq`: Integer tracking current minimum non-empty frequency bucket.
- **Complexity**:
  - `access(p)`: $O(1)$ (removes $p$ from bucket $f$, increments to $f+1$, inserts into bucket $f+1$, updates `_min_freq`).
  - `insert(p)`: $O(1)$ (inserts into bucket $1$, sets `_min_freq = 1`).
  - `evict()`: $O(1)$ (pops head from bucket `_min_freq`).

### 1.3 First-In-First-Out (FIFO)
- **Concept**: Evicts the page that was loaded earliest into memory, independent of subsequent hit accesses.
- **Data Structure**: `collections.OrderedDict` tracking load order.
- **Complexity**: $O(1)$ for all operations. Subsequent hits do not alter queue order.

---

## 2. Workload Intelligence & Statistical Metrics

Let a sliding observation window $W$ contain a sequence of $N$ access records:
$$W = \langle r_1, r_2, \dots, r_N \rangle, \quad r_i = (\text{page\_id}_i, t_i, \text{op}_i)$$

### 2.1 Frequency Distribution & Normalization
Let $U(W) = \{p \mid \exists r_i \in W, \text{page\_id}_i = p\}$ denote the set of distinct pages in window $W$.
The raw access count for page $p$ is:
$$c(p) = \sum_{i=1}^N \mathbb{I}(\text{page\_id}_i = p)$$
The normalized empirical probability mass function $P$ is:
$$P(p) = \frac{c(p)}{N}, \quad \sum_{p \in U(W)} P(p) = 1.0$$

### 2.2 Shannon Access Entropy
The access entropy measures the uniformity of page access distribution:
$$H(W) = - \sum_{p \in U(W)} P(p) \log_2 P(p)$$
- **Lower Bound**: $H = 0$ bits (all accesses reference a single page).
- **Upper Bound**: $H = \log_2 |U(W)|$ bits (perfectly uniform random distribution).

### 2.3 Sequentiality Ratio
Measures the proportion of consecutive accesses that follow a forward unit stride:
$$\text{Seq}(W) = \frac{1}{N - 1} \sum_{i=1}^{N - 1} \mathbb{I}(\text{page\_id}_{i+1} = \text{page\_id}_i + 1)$$
$\text{Seq}(W) \in [0.0, 1.0]$. A pure sequential table scan yields $\text{Seq}(W) \approx 1.0$.

### 2.4 LRU Stack Reuse Distance
For each access $r_i$ to page $p$ where $p$ was previously accessed at index $j < i$:
$$d_{reuse}(i) = |\{ \text{page\_id}_k \mid j < k < i \}|$$
The mean reuse distance for window $W$ is:
$$\bar{d}_{reuse}(W) = \frac{1}{|R_{reuse}|} \sum_{i \in R_{reuse}} \min(d_{reuse}(i), D_{max})$$
where $D_{max}$ is an upper capping constant (default $10,000$).

---

## 3. Phase Change Detection

### 3.1 Jensen-Shannon Divergence (JSD)
To compare probability distributions $P$ (from window $W_{t-1}$) and $Q$ (from window $W_t$) over the combined page universe $U = U(W_{t-1}) \cup U(W_t)$:
$$M = \frac{1}{2}(P + Q)$$
The Kullback-Leibler divergence with $\log_2$ base is:
$$D_{KL}(P \parallel M) = \sum_{p \in U, P(p) > 0} P(p) \log_2 \left(\frac{P(p)}{M(p)}\right)$$
The Jensen-Shannon Divergence is:
$$\text{JSD}(P \parallel Q) = \frac{1}{2} D_{KL}(P \parallel M) + \frac{1}{2} D_{KL}(Q \parallel M)$$
**Properties (Assumption A5)**:
1. Symmetric: $\text{JSD}(P \parallel Q) = \text{JSD}(Q \parallel P)$
2. Strictly bounded: $0.0 \le \text{JSD}(P \parallel Q) \le 1.0$ (when using $\log_2$).
3. $\text{JSD} = 0.0$ if and only if $P \equiv Q$.
4. $\text{JSD} = 1.0$ if $P$ and $Q$ have completely disjoint supports.

### 3.2 Multi-Feature Composite Divergence Score
The overall phase change divergence score $C(W_{t-1}, W_t)$ is:
$$C = w_{jsd} \cdot \text{JSD}(P \parallel Q) + w_{ent} \cdot \Delta H_{norm} + w_{seq} \cdot \Delta \text{Seq} + w_{reuse} \cdot \Delta d_{norm}$$
where:
- $\Delta H_{norm} = \frac{|H(W_t) - H(W_{t-1})|}{\max(H(W_t), H(W_{t-1}), 1.0)}$
- $\Delta \text{Seq} = |\text{Seq}(W_t) - \text{Seq}(W_{t-1})|$
- $\Delta d_{norm} = \frac{|\bar{d}_{reuse}(W_t) - \bar{d}_{reuse}(W_{t-1})|}{\max(\bar{d}_{reuse}(W_t), \bar{d}_{reuse}(W_{t-1}), 1.0)}$
- Weights satisfy $\sum w_i = 1.0$ (default: $0.50, 0.20, 0.15, 0.15$).

### 3.3 Detection Decision Rule
A phase change is declared if and only if:
$$C \ge \theta_{phase} \quad \wedge \quad \text{Confidence} \ge \theta_{conf} \quad \wedge \quad \text{windows\_analyzed} \ge N_{warmup}$$

---

## 4. Cost-Benefit Switching Engine

### 4.1 Switching Cost Model ($\kappa_{switch}$)
Transitioning from policy $\Pi_{curr}$ to policy $\Pi_{target}$ induces a transient hit-ratio penalty:
$$\kappa_{switch} = \kappa_{cold} + \kappa_{init} + \kappa_{fixed}$$
where:
- $\beta = \min\left(1.0, \frac{B_{size}}{W_{size}}\right)$ represents the buffer capacity relative to the observation window.
- $\kappa_{cold} = f_{cold} \cdot \beta \cdot 0.10$ models cold misses arising from uncalibrated metadata.
- $\kappa_{init} = f_{init} \cdot \beta$ models memory re-indexing and state transfer overhead.
- $\kappa_{fixed}$ is fixed dispatch latency overhead (default $0.005$).

### 4.2 Net Benefit Decision Rule
For candidate policy $\Pi_{target}$:
$$\Delta B = \max(0.0, \text{Affinity}(\text{Phase}, \Pi_{target}) - \text{Affinity}(\text{Phase}, \Pi_{curr}))$$
$$\text{Net Benefit} = (w_b \cdot \Delta B) - (w_c \cdot \kappa_{switch})$$

The system executes a transition to $\Pi_{target}^* = \arg\max \text{Net Benefit}$ if:
$$\Pi_{target}^* \neq \Pi_{curr} \quad \wedge \quad \text{Net Benefit} \ge \tau_{min}$$
Otherwise, the incumbent policy $\Pi_{curr}$ is retained.
