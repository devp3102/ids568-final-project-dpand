# Model Card (System Card): RAG-LLM Query Assistant v1.1.0

> **Note:** This is a System Card, not a traditional model card, because the deployed system is a RAG pipeline wrapping a third-party hosted LLM (Ollama/Mistral). Following Module 8 guidance, this card documents only what can be independently verified from the deployed system — not vendor internals.

---

## Model / System Details

| Field | Value |
|---|---|
| System Name | RAG-LLM Query Assistant |
| Version | v1.1.0 |
| Type | Retrieval-Augmented Generation (RAG) pipeline |
| LLM Provider | Ollama (local self-hosted inference) |
| LLM Model ID | mistral:7b-instruct |
| Embedding Model | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector Index | FAISS `IndexFlatIP` (cosine similarity via L2-normalized vectors) |
| Retrieval depth | top-k = 3 (default production) |
| Prompt template | v1.1 (citation-format instruction, updated 2026-04-20) |
| Serving framework | FastAPI 0.111.0 + Uvicorn |
| Monitoring | Prometheus + Grafana |
| Developed by | devpandhare (IDS568, University of Illinois Chicago) |
| Last updated | 2026-05-01 |

---

## Intended Use

### Primary Use Cases
- Answering natural-language questions about MLOps concepts and pipelines
- Retrieving relevant documentation from a curated MLOps knowledge base (8 source documents, 387 chunks as of v2)
- Supporting ML engineers and students in understanding production AI system operation

### Out-of-Scope Applications
- **Medical, legal, or financial advice** — the knowledge base contains no domain-specific expert content; hallucination risk in these domains is unmitigated
- **Real-time market data or current events** — the knowledge base is static and refreshed on a weekly cadence; responses about recent events will be stale
- **High-stakes autonomous decision-making** — system outputs are informational and require human review before acting on them
- **Personally identifiable information (PII) queries** — the system does not store or reason over user data; queries containing PII are filtered at the input validation layer

---

## Performance Metrics

*All metrics are from observed serving telemetry (EVT-003 onwards) or from M6 RAG evaluation (10-query benchmark). Evaluated quality metrics (groundedness, hallucination rate) are not included in real-time dashboards — they belong in periodic quality audits.*

### Observed Serving Metrics (Prometheus)

| Metric | Value | Notes |
|---|---|---|
| Request P50 latency | ~0.55s | Includes retrieval + generation |
| Request P99 latency | ~1.80s | Well below 3.0s SLA |
| TTFT P95 | ~1.45s | Approximate (non-streaming Ollama) |
| Cache hit ratio | ~38% | LRU cache on SHA-256 query hash |
| Mean retrieval similarity score | 0.719 (reference) | Baseline; drifts to 0.69 by Week 6 |
| Empty retrieval rate | ~3.8% | Queries with 0 FAISS results |
| Error rate | ~1.2% | Mostly malformed query inputs |

### M6 RAG Evaluation Results (10-query benchmark)

| Metric | Score | Definition |
|---|---|---|
| Precision@5 (P@5) | 0.76 | Fraction of retrieved docs that are relevant |
| Recall@5 (R@5) | 0.81 | Fraction of relevant docs retrieved |
| MRR | 0.84 | Mean Reciprocal Rank of first relevant doc |
| Mean retrieval latency | 42ms | FAISS search on 387 chunks |

*These metrics were measured on the 8-document curated MLOps corpus. Performance on out-of-distribution queries or domains will be lower.*

---

## Training Data Description

The system does not fine-tune any model weights. The knowledge base consists of:

| Source Type | Description |
|---|---|
| MLOps course materials | Module slides, lab notes (8 documents) |
| Processed format | Text chunked at 512 tokens with 64-token overlap |
| Embedding pipeline | `all-MiniLM-L6-v2` from sentence-transformers |
| Index | FAISS `IndexFlatIP`, L2-normalized vectors |
| Current version | v2 (387 chunks, 11 documents as of 2026-04-17) |
| Refresh cadence | Weekly (triggered by drift alert or manual schedule) |

The underlying LLM (`mistral:7b-instruct`) was trained by Mistral AI on publicly available text data. We do not have access to or control over the LLM's pretraining data composition.

---

## Limitations and Failure Modes

1. **KB Staleness:** The knowledge base is refreshed weekly. Queries about content added after the last refresh will return low-similarity retrievals or empty results. Drift monitoring (Component 4) detects this via `retrieval_similarity_score` PSI > 0.10.

2. **Context Window Constraints:** `mistral:7b-instruct` has a context window of ~8,192 tokens. With top-k=3 and 512-token chunks, the maximum prompt size is ~1,800 tokens — safe margin. Increasing top-k to 5 during A/B testing revealed latency regression (P99 = 3.22s) without exceeding the context window.

3. **Hallucination on Unsupported Topics:** If no relevant documents are retrieved (empty retrieval), the LLM will generate an answer from its parametric knowledge alone. This significantly increases hallucination risk. The system does not currently detect this condition and warn the user.

4. **Multi-hop Reasoning Failures:** Questions requiring synthesis across 3+ source documents may produce incomplete answers because retrieval returns a fixed top-k and prompt assembly is non-hierarchical.

5. **Non-English Queries:** The embedding model performs well on English text. Queries in other languages will produce lower cosine similarity scores and degraded retrieval quality.

6. **Adversarial Inputs:** Prompt injection attacks that attempt to override the system prompt or extract retrieved document content are partially mitigated by the input validation layer, but no formal red-teaming has been performed.

---

## Ethical Risks and Considerations

1. **Differential Service Quality:** Retrieval quality varies by query domain. Topics well-represented in the knowledge base (Prometheus, Airflow, MLflow) receive higher-quality responses than underrepresented topics. This could disadvantage users whose workflows are not covered by the current corpus.

2. **Over-reliance on AI-Generated Answers:** Users may accept LLM-generated answers without verifying them against primary sources, especially when confidence signals (retrieval scores) are not surfaced in the UI.

3. **Data Provenance Opacity:** Retrieved document sources are not currently cited in the response, making it difficult for users to verify claims. Prompt template v1.1 adds a citation instruction, but compliance is not enforced by a post-processing check.

4. **Training Data Bias in Underlying LLM:** `mistral:7b-instruct` may reflect biases present in its pretraining corpus. Because we use it for informational retrieval in a technical domain, the risk of demographically harmful outputs is low but not zero.

---

## References

- Component 2 (A/B test): `docs/experiment-specification.md` — performance targets for planned v1.2
- Component 3 (Governance): `docs/risk-register.md` — full risk enumeration
- Component 4 (Drift): `docs/drift-diagnostic-report.md` — KB staleness analysis
- Component 5 (Risk): `docs/governance-review.md` — system-level risk assessment
- Audit Trail: `logs/audit-trail.json` — version history
