# Risk Matrix: RAG-LLM Query Assistant

**System:** RAG-LLM Query Assistant v1.1.0  
**Date:** 2026-05-01  
**Framework:** NIST AI RMF Likelihood × Severity scoring

---

## Scoring Scale

| Score | Likelihood | Severity |
|---|---|---|
| 5 | Almost certain (>70% chance in 12 months) | Critical (system-wide failure, regulatory action, user harm) |
| 4 | Likely (40–70%) | Major (significant performance degradation, data breach) |
| 3 | Possible (20–40%) | Moderate (noticeable quality drop, user-visible errors) |
| 2 | Unlikely (5–20%) | Minor (internal metric anomaly, recoverable issue) |
| 1 | Rare (<5%) | Negligible (cosmetic, no user impact) |

**Risk Score = Likelihood × Severity**

| Score Range | Level | Action Required |
|---|---|---|
| 15–25 | CRITICAL | Immediate action; block deployment until resolved |
| 9–14 | HIGH | Action within 7 days; owner assigned |
| 4–8 | MEDIUM | Action within 30 days; monitor closely |
| 1–3 | LOW | Accept; review quarterly |

---

## Risk Matrix (Inherent Risk — Before Mitigations)

| | **Minor (2)** | **Moderate (3)** | **Major (4)** | **Critical (5)** |
|---|---|---|---|---|
| **Almost Certain (5)** | — | — | — | — |
| **Likely (4)** | — | **R001** KB Staleness (12) | **R003** Hallucination/Empty Retrieval (16) | — |
| **Possible (3)** | — | **R007** Differential Quality (9) | **R002** Prompt Injection (12) · **R004** PII Leakage (12) · **R008** No Override (12) | **R005** Third-party Exposure (15) |
| **Unlikely (2)** | **R009** Model Drift (4) | **R010** Regulatory Gap (6) | **R006** KB Contamination (8) | — |

---

## Full Risk Details with Mitigations

### R003 — Hallucination / Empty Retrieval *(CRITICAL → MEDIUM after mitigation)*

| Attribute | Value |
|---|---|
| Category | Robustness |
| Inherent Likelihood | 4 (Likely — ~3.8% of queries return 0 docs today) |
| Inherent Severity | 4 (Major — user acts on fabricated information) |
| **Inherent Score** | **16 (CRITICAL)** |
| **Mitigation** | 1. Surface `retrieval_result_count=0` as a visible disclaimer in response. 2. Route zero-retrieval queries to human escalation queue. 3. Monitor empty-retrieval rate on Grafana dashboard; alert at >10%. |
| Residual Likelihood | 2 (mitigations reduce undetected hallucination) |
| Residual Severity | 4 (severity of harm unchanged; we've reduced exposure) |
| **Residual Score** | **8 (MEDIUM)** |
| Owner | Product Owner |
| Review Trigger | Empty retrieval rate > 10% for >1 hour |

---

### R005 — Third-party Data Exposure *(HIGH — managed by architecture)*

| Attribute | Value |
|---|---|
| Category | Privacy |
| Inherent Likelihood | 3 (Possible — risk materializes if Ollama replaced by cloud API) |
| Inherent Severity | 5 (Critical — full prompt including user query sent to vendor) |
| **Inherent Score** | **15 (HIGH)** |
| **Mitigation** | 1. Current: Ollama runs locally — zero data egress. 2. Any LLM provider migration requires Security Lead sign-off, vendor DPA review, and data classification audit before deployment. 3. If cloud migration proceeds: PII masking applied before prompt transmission. |
| Residual Likelihood | 1 (local deployment eliminates current risk) |
| Residual Severity | 5 (unchanged — severity is inherent to cloud API architecture) |
| **Residual Score** | **5 (MEDIUM)** |
| Owner | Security Lead |
| Review Trigger | Any LLM provider change; contract expiry review annually |

---

### R001 — KB Staleness *(HIGH → LOW after mitigation)*

| Attribute | Value |
|---|---|
| Category | Robustness |
| Inherent Likelihood | 4 (Likely — MLOps domain evolves rapidly) |
| Inherent Severity | 3 (Moderate — silent quality degradation, ~3.8% completion rate drop per PSI unit) |
| **Inherent Score** | **12 (HIGH)** |
| **Mitigation** | 1. Automated weekly KB re-ingestion via CI/CD. 2. PSI-triggered alert at `retrieval_similarity_score` PSI > 0.10 (Component 4). 3. Post-refresh PSI validation — refresh fails CI if PSI > 0.10 after ingestion. 4. Document age Prometheus metric; alert if p95 > 14 days. |
| Residual Likelihood | 2 (weekly refresh significantly reduces staleness window) |
| Residual Severity | 2 (detectable early; impact bounded to <1 week before correction) |
| **Residual Score** | **4 (LOW)** |
| Owner | Data Engineer |
| Review Trigger | PSI > 0.10 on `retrieval_similarity_score` |

---

### R002 — Prompt Injection *(HIGH → MEDIUM)*

| Attribute | Value |
|---|---|
| Category | Robustness |
| Inherent Likelihood | 3 (Possible — public-facing API) |
| Inherent Severity | 4 (Major — attacker could exfiltrate KB contents or override system behavior) |
| **Inherent Score** | **12 (HIGH)** |
| **Mitigation** | 1. Input validation strips known injection patterns (ignore previous instructions, DAN prompts). 2. Response filter checks for instruction-following anomalies (e.g., response starting with "Sure, I'll ignore..." ). 3. Quarterly red-team exercise. 4. Rate limiting on /query endpoint (max 30 req/min per IP). |
| Residual Likelihood | 2 |
| Residual Severity | 3 |
| **Residual Score** | **6 (MEDIUM)** |
| Owner | ML Platform Lead |
| Review Trigger | Red-team finding or anomalous response pattern in logs |

---

### R004 — PII Leakage *(HIGH → LOW)*

| Attribute | Value |
|---|---|
| Category | Privacy |
| Inherent Likelihood | 3 (Possible — technical users sometimes include real data in example queries) |
| Inherent Severity | 4 (Major — PII transmitted to LLM and potentially logged) |
| **Inherent Score** | **12 (HIGH)** |
| **Mitigation** | 1. Regex-based PII detection at input layer (email, phone, SSN, credit card patterns). 2. Detected PII replaced with `[REDACTED]` before prompt assembly. 3. No raw query text persisted to disk; in-memory only. 4. Prometheus metrics contain only aggregate statistics. |
| Residual Likelihood | 1 |
| Residual Severity | 4 (severity remains — unknown PII patterns could bypass filter) |
| **Residual Score** | **4 (LOW)** |
| Owner | Security Lead |
| Review Trigger | PII detection trigger rate > 0.5% |

---

### R007 — Differential Service Quality *(HIGH → MEDIUM)*

| Attribute | Value |
|---|---|
| Category | Bias |
| Inherent Likelihood | 3 (Possible — KB is English-only, MLOps-only) |
| Inherent Severity | 3 (Moderate — some user groups receive systematically worse answers) |
| **Inherent Score** | **9 (HIGH)** |
| **Mitigation** | 1. Quarterly KB coverage audit by topic cluster. 2. Monitor retrieval score P25 in Grafana; alert if P25 < 0.50 (indicates underrepresented queries becoming common). 3. Track query clustering over time; identify growing topic clusters with low similarity scores. 4. Prioritize underrepresented topics in next KB ingestion cycle. |
| Residual Likelihood | 2 |
| Residual Severity | 3 |
| **Residual Score** | **6 (MEDIUM)** |
| Owner | ML Team Lead |
| Review Trigger | Retrieval score P25 < 0.50 |

---

### R008 — No Human Override *(HIGH → MEDIUM)*

| Attribute | Value |
|---|---|
| Category | Compliance |
| Inherent Likelihood | 3 |
| Inherent Severity | 4 |
| **Inherent Score** | **12 (HIGH)** |
| **Mitigation** | 1. Add confidence threshold: if `top_retrieval_score < 0.40`, prepend disclaimer and surface escalation link. 2. Implement `/feedback` endpoint where users flag incorrect responses; flagged responses trigger human review queue. 3. Weekly human review of 20 random flagged responses. |
| Residual Likelihood | 2 |
| Residual Severity | 3 |
| **Residual Score** | **6 (MEDIUM)** |
| Owner | Product Owner |
| Review Trigger | User complaint rate > 2% of daily requests |

---

### R006, R009, R010 — Lower Priority Risks

| ID | Risk | Inherent | Mitigation Summary | Residual |
|---|---|---|---|---|
| R006 | KB Contamination | 8 (MEDIUM) | Human review for all KB ingestion; doc hash in audit trail | 4 (LOW) |
| R009 | Ollama Model Version Drift | 4 (LOW) | Pin model version in Docker; startup schema validation | 2 (LOW) |
| R010 | Regulatory Non-Compliance | 6 (MEDIUM) | System Card + audit trail satisfies NIST AI RMF and EU AI Act Article 13 documentation requirements | 4 (LOW) |

---

## Residual Risk Summary (Post-Mitigation)

| ID | Risk | Inherent Score | Residual Score | Level Change |
|---|---|---|---|---|
| R003 | Hallucination / Empty Retrieval | 16 | **8** | CRITICAL → MEDIUM |
| R005 | Third-party Data Exposure | 15 | **5** | HIGH → MEDIUM |
| R001 | KB Staleness | 12 | **4** | HIGH → LOW |
| R002 | Prompt Injection | 12 | **6** | HIGH → MEDIUM |
| R004 | PII Leakage | 12 | **4** | HIGH → LOW |
| R007 | Differential Quality | 9 | **6** | HIGH → MEDIUM |
| R008 | No Human Override | 12 | **6** | HIGH → MEDIUM |
| R006 | KB Contamination | 8 | **4** | MEDIUM → LOW |
| R009 | Model Version Drift | 4 | **2** | LOW → LOW |
| R010 | Regulatory Gap | 6 | **4** | MEDIUM → LOW |

**No risks remain at CRITICAL level after mitigations.** The system is ready for limited production deployment with ongoing monitoring. R003 (hallucination) is the highest residual risk and must be addressed before scaling to external users.

---

## Connection to Monitoring (Component 1)

Each HIGH/CRITICAL risk has a corresponding observable signal on the Grafana dashboard:

| Risk | Dashboard Signal | Alert Threshold |
|---|---|---|
| R001 KB Staleness | `rag_retrieval_similarity_score` histogram | PSI > 0.10 weekly |
| R003 Hallucination | `rag_retrieval_result_count` bucket (le=0) | Empty retrieval rate > 10% |
| R007 Differential Quality | `rag_retrieval_similarity_score` P25 gauge | P25 < 0.50 |
| R002 Prompt Injection | `rag_requests_total{status="error"}` | Error rate > 5% |
