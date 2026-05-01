# Dashboard Interpretation & Diagnostic Reasoning

## System: RAG-LLM Query Assistant — Production Monitoring Dashboard

---

## 1. What the Dashboard Reveals About System Health

The dashboard tracks five signal categories across the RAG-LLM serving pipeline: **request traffic**, **latency percentiles**, **LLM generation behavior**, **retrieval quality**, and **cache efficiency**. Together they answer three questions at a glance:

> *Is my infrastructure healthy? Is my model behaving as expected? Is my data still valid?*

### 1.1 Traffic & Error Rate

The `rag_requests_total` counter feeds a rolling 5-minute rate and error-rate percentage. Under baseline load the service processes **~8 req/s** with an error rate of **~1.2%**. This is well within acceptable bounds (SLA threshold: 5%).

**Observation:** If `rag_requests_total{status="error"}` spikes without a corresponding latency increase, the root cause is likely an upstream validation failure or malformed query — *not* a resource constraint. This distinguishes client-side issues from infrastructure issues.

### 1.2 Latency Percentiles (P50, P95, P99)

Under simulated load, the dashboard shows:

| Percentile | Observed | SLA Threshold | Assessment |
|---|---|---|---|
| P50 | ~0.55s | — | Healthy — median user wait is under 1s |
| P95 | ~1.4s | — | Acceptable — 95% of users complete in <1.5s |
| P99 | ~1.8s | **3.0s** | **Healthy — 2.0 std deviations below SLA** |

The P99 of 1.8s leaves a 1.2s margin before the SLA is breached. However, the A/B test results (Component 2) show that increasing `top_k` from 3 to 5 can push P99 to ~3.2s, which would breach the SLA. This cross-component finding justifies holding the treatment in "investigate" status rather than shipping.

### 1.3 Time to First Token (TTFT)

TTFT (approximated as total generation latency for non-streaming Ollama) P95 runs at **~1.45s**. This is the dominant contributor to end-to-end latency. Increases in TTFT signal:

- Larger prompt context (e.g., retrieving more documents raises prompt token count)
- Ollama model warmup / cold-start after idle periods
- GPU/CPU resource pressure during burst traffic

The dashboard plots TTFT alongside P99 request latency so operators can immediately determine whether a latency regression originates in retrieval or generation.

### 1.4 Token Throughput

Completion token throughput runs at **~180 tokens/s** under steady load. A sudden drop (>20%) without a corresponding request-rate drop indicates generation slowdown — typically caused by longer output sequences, model memory pressure, or Ollama thread contention.

### 1.5 Cache Hit Ratio

The cache hit ratio panel (target: ≥40%) reflects how often repeated or near-duplicate queries are served from the LRU cache (implemented in M5). A ratio below 25% is a cost signal: redundant LLM calls are being made for effectively identical inputs.

**Observation:** The cache hit ratio fluctuates between 35–45% under realistic load patterns, consistent with M5 benchmark results showing ~38% cache efficiency on the MLOps query corpus.

### 1.6 Empty Retrieval Rate

The empty retrieval rate — the fraction of FAISS queries returning zero matching documents — is a direct proxy for **knowledge base coverage gaps**. At baseline this sits at ~3.8%.

**Drift connection (Component 4):** The drift analysis (Week 6) shows `retrieval_result_count` PSI = 0.024 (still stable), but `retrieval_similarity_score` PSI = 0.25 (significant drift). This combination means retrieval is still *returning* documents but with decreasing confidence — the early warning of KB staleness before the empty-retrieval rate visibly spikes. The dashboard alert fires at 15% empty-retrieval rate; the drift system fires earlier at PSI > 0.20.

---

## 2. Identified Bottlenecks & Risks

### Bottleneck 1: Generation Latency Under High top-k

The P99 latency guardrail breach observed during the A/B test (P99 = 3.22s for top_k=5) reveals that **prompt assembly scales super-linearly with retrieved context length**. Each additional retrieved document adds ~120ms of median latency and ~200ms to P99 due to longer prompt tokenization.

**Mitigation:** Implement contextual compression (summarize retrieved docs before assembly) or dynamic top-k selection based on real-time retrieval confidence.

### Bottleneck 2: KB Staleness Erodes Retrieval Quality

Week 3 drift monitoring detected `retrieval_similarity_score` PSI = 0.11 (moderate). By Week 6 it reached PSI = 0.25 (significant). This silently degraded task completion rate by an estimated **~3.8%** before an alert fired (see Component 4). A 4-week refresh cadence is insufficient for a dynamic MLOps knowledge domain.

**Recommendation:** Weekly automated KB re-ingestion triggered by `retrieval_similarity_score` PSI > 0.10.

### Bottleneck 3: Cache Inefficiency for Novel Queries

Cache hit ratio drops to ~20% during new-topic surges (e.g., a new MLOps release announcement triggers many distinct queries). TTL-based cache eviction removes relevant entries before the query pattern repeats.

---

## 3. Alert Trigger Conditions for Production

| Alert | Condition | Severity | Action |
|---|---|---|---|
| `HighErrorRate` | `error_rate_5m > 0.05` (5%) | Critical | Page on-call; investigate immediately |
| `LatencySLABreach` | `P99_latency > 3.0s` for 5 min | Critical | Rollback to top_k=3 configuration |
| `TTFTDegraded` | `TTFT_P95 > 2.5s` for 10 min | Warning | Check Ollama model warmup, GPU utilization |
| `EmptyRetrievalHigh` | `empty_retrieval_rate > 0.15` | Warning | Schedule KB refresh within 24h |
| `CacheHitLow` | `cache_hit_ratio < 0.20` | Info | Evaluate TTL settings and query clustering |
| `DriftWarning` | PSI > 0.10 on any feature | Warning | Run drift diagnostic; prepare KB refresh |
| `DriftCritical` | PSI > 0.20 on `retrieval_similarity_score` | Critical | Trigger immediate KB re-ingestion |

---

## 4. Design Justification

### Why Prometheus + Grafana?

Prometheus was chosen because:
1. **Pull-based scraping** integrates natively with the FastAPI `/metrics` endpoint already in M5
2. **Time-series storage** enables the rolling-window PromQL queries needed for P50/P95/P99 percentiles
3. **OSS with no proprietary dependency** — satisfies the constraint of no proprietary cloud monitoring
4. **Grafana** provides rich alerting rules and shares the same datasource, avoiding a separate alert pipeline

### Why Observable Metrics Only?

The dashboard deliberately uses only **observable** metrics (token counts, latency, retrieval result counts, similarity scores from the serving path). Evaluated metrics like groundedness or hallucination rate require a judge-LLM pipeline with batch latency of minutes to hours — unsuitable for real-time dashboards and alerting. The similarity score drift (PSI on `rag_retrieval_similarity_score`) serves as a reliable proxy for quality degradation without requiring human annotation.

### Dashboard Layout (Pyramid Structure)

Following Module 8 guidance:
- **Top row (stat panels):** High-level health signals for on-call engineers — error rate, P99, request rate, cache ratio
- **Middle rows (time series):** Trend panels for SRE investigation — latency percentiles, TTFT, token throughput
- **Design principle:** Each panel answers a specific operational question; no metric appears without an interpretation and threshold
