# A/B Experiment Specification

## Experiment: RAG Top-k Optimization — `rag_topk_optimization_v1`

---

## 1. Hypothesis

> **H₀ (null):** Changing RAG retrieval depth from top-k=3 to top-k=5 produces no meaningful change in task completion rate.
>
> **H₁ (alternative):** top-k=5 increases task completion rate by at least 5 percentage points compared to top-k=3, without breaching the P99 latency SLA of 3.0 seconds.

**Rationale:** FAISS retrieval in the M6 pipeline is fast (P95 < 80ms), so the cost of fetching 2 additional documents is dominated by prompt assembly and LLM token processing. We hypothesize that richer context will reduce re-query behavior — users reformulating questions because the first answer was insufficient.

---

## 2. Variants

| Variant | Label | Traffic Split | Configuration |
|---|---|---|---|
| Control | `top_k=3` | 50% | Current production default |
| Treatment | `top_k=5` | 50% | +2 retrieved documents per query |

---

## 3. Success Metrics

### Primary Metric (Binary — Observable)

**Task Completion Rate:** Fraction of sessions where the user does not re-query within 60 seconds.

- Baseline (control): 62%
- Minimum Detectable Effect (MDE): +5 percentage points
- Statistical test: Two-proportion z-test (two-tailed)

This metric is observable from serving telemetry — a second request from the same session within 60s is flagged as a re-query.

### Secondary Metric (Continuous — Observable)

**Mean Retrieval Similarity Score:** The mean cosine similarity of the top-1 FAISS result across all queries.

- Expected improvement: +0.04 (from 0.72 → 0.76)
- Statistical test: Welch's t-test (unequal variance)

---

## 4. Guardrail Metrics

These must *not* regress in the treatment group:

| Guardrail | Threshold | Measurement |
|---|---|---|
| P99 end-to-end latency | ≤ 3.0s | `histogram_quantile(0.99, ...)` |
| Error rate delta | ≤ +0.5% vs control | `rag_requests_total{status="error"}` |
| Cost per query | ≤ $0.015 | Token count × unit cost proxy |

---

## 5. Randomization Method

**Deterministic hash-based assignment** via MD5(user_id + experiment_name). This ensures:

1. The same user always receives the same variant (no within-session inconsistency)
2. Splitting is statistically independent of user characteristics (hash bucketing is uniform)
3. No external service or database dependency for assignment

```python
hash_input = f"{user_id}:{experiment_name}"
hash_val = hashlib.md5(hash_input.encode()).hexdigest()
bucket = int(hash_val[:8], 16) / (16**8)
variant = "control" if bucket < 0.5 else "treatment"
```

---

## 6. Sample Size & Duration Calculation

### Power Analysis

| Parameter | Value |
|---|---|
| Baseline completion rate (p₁) | 62% |
| Expected treatment rate (p₂) | 67% (+5 pp) |
| Significance level (α) | 0.05 (two-tailed) |
| Statistical power (1−β) | 80% |
| Effect size (Cohen's h) | 0.103 |
| **Required n per group** | **1,437** |

Formula used (Cohen's h for proportions):

```
h = 2 * (arcsin(√p₂) − arcsin(√p₁))
n = 2 * ((z_{α/2} + z_β) / h)²
```

### Duration Estimate

At observed request rate of ~8 req/s with 50% split:
- Control receives 4 req/s → ~345,600 observations/day
- Required 1,437 observations per group → achievable in **< 1 day**
- Recommended minimum runtime: **7 days** to account for day-of-week traffic variation and novelty effects

The simulation uses n=5,000 per group (3.5× the minimum required) to ensure high power and tight confidence intervals.

### Multiple Comparison Correction

Since two metrics are tested simultaneously (completion rate and retrieval score), **Bonferroni correction** is applied:

- Raw α = 0.05, k = 2 metrics → adjusted threshold = 0.025
- Both metrics must remain significant after this correction for a "SHIP" decision to stand
- In the simulation both pass Bonferroni (p < 0.00001 for both), making the correction non-binding in this scenario — but it is correctly applied by the code regardless

---

## 7. Stopping Rules

- **Early stopping for harm:** If error rate in treatment exceeds control by 2% at any point, experiment terminates immediately and control is reinstated.
- **Minimum runtime:** Experiment runs for at least 7 days regardless of when significance is reached (prevents peeking bias).
- **Maximum runtime:** 28 days; if not significant by then, collect more data or revisit MDE assumption.
