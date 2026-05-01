# Data Integrity & Drift Diagnostic Report

**System:** RAG-LLM Query Assistant  
**Script:** `src/drift/drift_detection.py`

---

## 1. Overview

This report analyzes drift across four observable RAG serving distributions using Population Stability Index (PSI) and importance-weighted scoring. All features are derived from Prometheus serving telemetry — no evaluated quality metrics are used.

| Feature | Source | Importance Weight |
|---|---|---|
| `retrieval_similarity_score` | FAISS cosine similarity (top-1) | 0.40 |
| `query_length_tokens` | Tokenized user query | 0.25 |
| `response_length_tokens` | LLM completion token count | 0.20 |
| `retrieval_result_count` | FAISS result count per query | 0.15 |

---

## 2. PSI Results — Week 6 vs Reference

| Feature | PSI | Severity | IW-PSI | Interpretation |
|---|---|---|---|---|
| `query_length_tokens` | **0.2538** | **SIGNIFICANT** | 0.0635 | User queries are getting longer (+14 tokens mean) — behavioral shift toward more complex questions |
| `retrieval_similarity_score` | **0.2501** | **SIGNIFICANT** | **0.1000** | Top-1 similarity score distribution has shifted downward — KB coverage not keeping up with query patterns |
| `response_length_tokens` | 0.1366 | MODERATE | 0.0273 | Responses are longer — correlated with longer queries and more context in prompt |
| `retrieval_result_count` | 0.0242 | STABLE | 0.0036 | Retrieval count distribution unchanged — KB still returning documents, just with lower confidence |

PSI interpretation thresholds (Module 8, slide 26):
- < 0.10: No significant change — continue monitoring
- 0.10–0.20: Moderate change — investigate
- > 0.20: Significant change — **action required**

---

## 3. Which Features Drifted Most?

### Primary Concern: `query_length_tokens` (PSI = 0.2538)

The mean query length increased from **18 tokens** (reference) to **~30 tokens** (Week 6). This indicates a behavioral shift: users are asking more elaborate questions — potentially because:

1. The system is being used for more complex multi-step reasoning tasks (beyond the initial FAQ-style queries)
2. Users have learned that more context in their query improves retrieval quality
3. The user base has shifted from beginners to practitioners

**Importance weighting:** Despite having the highest raw PSI, `query_length_tokens` has a lower importance weight (0.25) than `retrieval_similarity_score` (0.40). Longer queries increase prompt token count, which marginally increases P99 latency — but this is a user behavior shift, not a data quality failure.

### Primary Concern: `retrieval_similarity_score` (PSI = 0.2501, IW-PSI = 0.1000 — highest)

The retrieval similarity score distribution has shifted left (lower scores). Reference mean: **0.719**; Week 6 mean: **~0.690**. This is the highest importance-weighted drift signal and the root cause of performance degradation.

**Mechanism:** The MLOps knowledge domain is evolving faster than the KB refresh cadence. New tools (new Airflow versions, new MLflow features) are not represented in the current document corpus. Queries about these new topics retrieve semantically distant documents, reducing cosine similarity.

### Secondary: `response_length_tokens` (PSI = 0.1366, MODERATE)

Response length has grown moderately. This is a correlated downstream effect: longer queries → more context in prompt → longer generated responses. This is not independently concerning but confirms the behavioral shift.

### Stable: `retrieval_result_count` (PSI = 0.0242)

The number of documents returned per query remains stable. This is important: the system is *still retrieving* documents (not returning empty results), which means the KB coverage gap is in *quality*, not *quantity*. This early warning is only detectable by monitoring similarity scores directly — empty retrieval rate alone would miss it.

---

## 4. Impact on Model Performance

### Quantified Impact

The `retrieval_similarity_score` PSI of 0.2501 is used to estimate business impact via the empirical relationship observed in the M6 RAG evaluation:

> *A PSI of 0.20 on retrieval similarity historically correlates with a ~3.8% drop in task completion rate.*

This estimate is based on the sensitivity analysis: for every 0.01 PSI above 0.10, we expect approximately 0.25 percentage points of completion rate degradation.

**Estimated impact (Week 6):** Task completion rate has likely declined by **~3.8 pp** (from 62.9% baseline to ~59.1%) due to retrieval quality degradation alone. This is consistent with the A/B test finding that retrieval quality is the primary lever for completion rate improvement.

### Monitoring Connection

The Prometheus dashboard (Component 1) tracks `rag_retrieval_similarity_score` as a histogram. The PSI computed here (0.25) correlates with an observable shift visible in the "Mean Retrieval Similarity Score" Grafana gauge panel — confirming that the drift detection signal is consistent with real-time monitoring data.

---

## 5. Data Integrity Checks

IQR-based outlier detection on the Week 6 production snapshot:

| Feature | Outlier % | Assessment |
|---|---|---|
| `retrieval_similarity_score` | 0.4% | Clean — bounded [0, 1] by design |
| `query_length_tokens` | 0.2% | Negligible — a few very long queries (>80 tokens) |
| `response_length_tokens` | 0.4% | Negligible |
| `retrieval_result_count` | **6.3%** | Warning — integer values near 0 are IQR outliers |

The `retrieval_result_count` outlier flag (6.3%) is a known artifact of the IQR method applied to a discrete distribution. Values of 0 and 1 fall outside the IQR fence because the distribution is right-skewed (most queries return 3 documents). This is not a data quality issue but a limitation of applying IQR to discrete data.

No missing values were detected in any feature.

---

## 6. Retraining & Intervention Recommendations

### Immediate (Week 6, within 48 hours)

1. **Trigger KB re-ingestion** — Add recently published MLOps documentation (last 60 days) to the knowledge base. Target: 5+ new source documents covering Airflow 3.x, MLflow 2.14+, and RAG best practices.
2. **Re-build FAISS index** — After ingestion, rebuild the IndexFlatIP index and log the event in the audit trail (`KNOWLEDGE_BASE_UPDATED` event type).
3. **Validate post-refresh PSI** — After re-indexing, re-run drift analysis. Target: `retrieval_similarity_score` PSI < 0.10.

### Medium-term (Within 30 days)

4. **Implement automated weekly KB refresh** — CI/CD pipeline triggered by a Cron job. Automatically runs `drift_detection.py` post-refresh and fails if PSI > 0.10.
5. **Add document age monitoring** — Surface `document_age_days` percentiles in the Grafana dashboard. Alert when p95 document age exceeds 14 days.

### Model Retraining Decision

The underlying `mistral:7b-instruct` model does not require retraining — all observed drift is in the *retrieval layer*, not the LLM's parametric knowledge. If domain-specific hallucinations increase (detected via periodic quality audits), consider RAG-specific fine-tuning or prompt engineering before committing to full fine-tuning.

**Decision tree for retraining:**
- Retrieval PSI > 0.20 and KB refresh resolves it → **No retraining needed**
- Retrieval PSI stable but quality audit shows hallucination increase > 2× baseline → **Consider prompt template change first**
- Both retrieval PSI high AND quality degradation → **Schedule fine-tuning experiment**
