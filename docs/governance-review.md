# AI Governance & Structured Risk Review

**System:** RAG-LLM Query Assistant v1.1.0  
**Review Date:** 2026-05-01    
**Framework:** NIST AI RMF + Module 8 Governance Guidelines

---

## System Overview

The RAG-LLM Query Assistant is a local RAG pipeline that retrieves MLOps documentation chunks using FAISS vector search (sentence-transformers embeddings) and generates grounded responses via a locally-hosted Ollama LLM (`mistral:7b-instruct`). The system boundary spans: user input → input validation → FAISS retrieval → prompt assembly → Ollama LLM API → response filter → user output.

See `docs/system-boundary-diagram.png` for the full boundary diagram and trust zone map.

---

## 1. Data Security

### What data flows through the system?

| Data Type | Where It Flows | Sensitivity |
|---|---|---|
| User query text | Client → Input validation → Prompt assembly → Ollama API | Medium (may contain PII) |
| Retrieved document chunks | FAISS index → Prompt assembly → Ollama | Low (public MLOps docs) |
| Full constructed prompt | Prompt assembly → Ollama API | Medium |
| LLM-generated response | Ollama API → Response filter → Client | Low |
| Prometheus metrics | Service → Prometheus scrape endpoint | Low (no PII) |

### Security controls in place

- **No persistent user data storage:** Queries are processed in-memory and not logged to disk unless explicitly enabled
- **Local Ollama deployment:** All LLM inference occurs on-premise; no query data is transmitted to external cloud APIs in the current configuration
- **Input sanitization:** Regex-based PII detection (email, phone, SSN patterns) at the validation layer before prompt assembly
- **Metrics redaction:** Prometheus metrics expose aggregate distributions only — no individual query content is exported
- **KB access control:** The FAISS index and source documents are read-only at runtime; ingestion requires separate authenticated pipeline (audit trail EVT-001, EVT-005)

### Residual data security risk

The primary residual risk is an undetected PII pattern (e.g., internal employee IDs or proprietary project names) that bypasses the regex-based sanitizer. Mitigation: quarterly review of the sanitizer pattern set and red-team testing with adversarial inputs.

---

## 2. Retrieval Risks

### 2a. Data Exposure via Retrieval

Retrieved document chunks are included verbatim in the LLM prompt. If the KB were to contain confidential documents (e.g., internal project roadmaps accidentally ingested), those chunks could be reproduced in the model's response.

**Current mitigation:** The KB ingestion pipeline requires human review approval for any non-public document source (logged in audit trail). All current KB documents are public MLOps course materials.

### 2b. Retrieval Contamination / Poisoning

An attacker with access to the KB ingestion pipeline could inject adversarially crafted documents designed to redirect the LLM's responses. For example, a document claiming "the correct way to monitor ML systems is to disable all alerts" would be retrieved and included in the prompt context.

**Current mitigation:** Document hash recorded at ingestion (EVT-001, EVT-005); unexpected chunk count changes trigger alert (R006). No automated content-quality filter exists yet.

**Gap:** No semantic anomaly detection on ingested documents. Adding cosine similarity check against existing corpus mean (flag documents with similarity < 0.30 to any existing chunk) would detect outlier injections.

### 2c. Stale Knowledge

The knowledge base reflects MLOps tooling as of the last ingestion date. Queries about new features in Airflow 3.x, MLflow 2.14+, or Prometheus 2.50+ will be answered using outdated context.

**Monitoring signal:** `retrieval_similarity_score` PSI (tracked in Component 4). Week 6 PSI = 0.25 (significant drift), triggering KB refresh. After refresh (EVT-005), PSI returned to 0.041.

**Mitigation:** Automated weekly PSI check; KB refresh triggered when PSI > 0.10.

---

## 3. Hallucination Risk Points

Hallucination occurs when the LLM generates factually incorrect content. In a RAG system, there are three primary hallucination pathways:

### 3a. Empty Retrieval Hallucination (Highest Risk)

When FAISS returns zero matching documents (`retrieval_result_count = 0`, ~3.8% of queries), the LLM has no grounding context and generates answers entirely from parametric memory. The model may confidently produce incorrect or fabricated information.

**Current risk level:** HIGH (R003, score = 16 before mitigation)  
**Mitigation:** Add response-layer disclaimer when `retrieval_result_count = 0`; surface uncertainty indicator in UI.

### 3b. Low-Confidence Retrieval Hallucination

When retrieval similarity score < 0.40, retrieved documents are semantically distant from the query. The LLM may blend the weak context with parametric knowledge in unpredictable ways.

**Mitigation (planned):** Threshold-based confidence check: if `top_score < 0.40`, prepend disclaimer and offer escalation link (R008).

### 3c. Citation Fabrication

Without explicit grounding instructions, LLMs sometimes fabricate specific citations (paper titles, version numbers, configuration values). Prompt template v1.1 added a citation instruction: "Only cite specific values that appear verbatim in the retrieved context."

**Monitoring:** No automated hallucination rate tracking currently. Periodic manual review of 20 random queries per week is the current quality audit mechanism.

---

## 4. Tool-Misuse Pathways (Agentic Considerations)

The current system (v1.1.0) is **not agentic** — it is a single-turn RAG pipeline with no tool calls, no multi-step reasoning loops, and no ability to execute external actions. The M6 `agent_controller.py` ReAct agent was evaluated but not deployed to production.

**If the agentic controller were deployed**, the following tool-misuse risks would apply:

| Tool | Misuse Pathway | Mitigation |
|---|---|---|
| `summarizer` tool | Produce misleading summaries of retrieved docs | Output comparison against source chunks |
| `retriever` tool | Infinite retrieval loop draining compute | Max-iteration guard (already in M6: max_steps=10) |
| `retriever` tool | Query reformulation that probes for sensitive docs | Input sanitization on reformulated queries |
| Future `code_executor` tool | LLM-generated code executes malicious commands | Sandboxed execution environment required |

**Recommendation:** Before enabling the agentic controller in production, conduct a full tool-misuse red-team exercise and add per-tool rate limiting.

---

## 5. Compliance Concerns

### 5a. PII (GDPR / CCPA)

User queries may contain PII (email addresses, names in example scenarios). The system currently:
- Does not persist raw query text to disk
- Applies regex PII detection at the input layer
- Does not transmit queries to external APIs (Ollama is local)

**Gap:** No formal data retention policy document; no user consent mechanism. If deployed to external users, a GDPR-compliant privacy notice and data processing agreement would be required.

### 5b. EU AI Act (General-Purpose AI)

The system wraps `mistral:7b-instruct`, a general-purpose AI system. Under the EU AI Act (effective August 2024), deployers of GPAI systems must:
- Maintain technical documentation (satisfied by this model card + audit trail)
- Implement transparency measures (currently partial — no user-facing disclosure)
- Assess copyright compliance of training data (vendor responsibility for Mistral)

**Current compliance status:** Partial. Technical documentation is complete; user-facing transparency and copyright assessment remain open items.

### 5c. Vendor Lock-in and Schema Change Risk

Ollama's model API may change between versions, silently altering response format. Docker image pins the model version (`mistral:7b-instruct-v0.2`) but does not pin Ollama itself.

**Mitigation:** Add Ollama version pin to Docker image; implement a startup health check that validates response schema on a canary query (R009).

---

## 6. Summary of Open Governance Gaps

| Gap | Priority | Owner | Target Date |
|---|---|---|---|
| Hallucination disclaimer for empty retrieval | HIGH | Product Owner | 2026-05-15 |
| Automated content anomaly detection on KB ingestion | MEDIUM | Data Engineer | 2026-06-01 |
| User-facing PII policy and consent mechanism | MEDIUM | Compliance Officer | 2026-06-15 |
| Ollama version pinning in Docker | LOW | ML Platform Lead | 2026-05-10 |
| Semantic grounding check (citation validation) | MEDIUM | ML Engineer | 2026-06-01 |
