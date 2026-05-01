# Risk Register: RAG-LLM Query Assistant

**Version:** 1.1  
**Last Updated:** 2026-05-01  
**Framework:** NIST AI RMF (Govern → Map → Measure → Manage)

---

## Category Definitions

- **Bias** — differential performance or unfair treatment across user groups or query domains
- **Robustness** — system failures under adversarial, unexpected, or distributional-shift conditions
- **Privacy** — exposure or misuse of personally identifiable or sensitive information
- **Compliance** — adherence to organizational policies, vendor contracts, and applicable regulations

---

## Risk Register

| ID | Risk Description | Category | Likelihood (1–5) | Severity (1–5) | Score | Level | Treatment | Mitigation | Owner | Review Trigger |
|---|---|---|---|---|---|---|---|---|---|---|
| R001 | **KB Staleness** — Retrieved documents become outdated after product/course updates, silently degrading answer quality | Robustness | 4 | 3 | 12 | HIGH | Mitigate | Weekly PSI-triggered KB re-ingestion; Prometheus alert at `retrieval_similarity_score` PSI > 0.10 | Data Engineer | PSI > 0.10 or doc age p95 > 14 days |
| R002 | **Prompt Injection** — Adversarial user inputs attempt to override system prompt or exfiltrate retrieved documents | Robustness | 3 | 4 | 12 | HIGH | Mitigate | Input validation layer strips common injection patterns; response filter detects instruction-following anomalies | ML Platform Lead | Red-team finding or flagged interaction |
| R003 | **Hallucination on Unsupported Queries** — Empty or near-empty retrieval causes LLM to fabricate answers from parametric memory | Robustness | 4 | 4 | 16 | CRITICAL | Mitigate | Surface empty-retrieval indicator in response; add disclaimer when `retrieval_result_count = 0`; escalation protocol to human review | Product Owner | Empty retrieval rate > 10% |
| R004 | **PII Leakage in Queries** — Users inadvertently include PII (emails, IDs) in query text, which is then included in LLM prompt | Privacy | 3 | 4 | 12 | HIGH | Mitigate | Input sanitization: regex-based PII detection for emails, phone numbers, SSNs before prompt assembly; log redaction | Security Lead | PII detection trigger rate > 0.5% |
| R005 | **Third-party Data Exposure** — Full user query + retrieved document context is sent to Ollama API (currently local; risk increases if vendor is changed to cloud API) | Privacy | 2 | 5 | 10 | HIGH | Accept/Transfer | Current: Ollama local — no data leaves infrastructure. Future cloud migration requires vendor DPA review and data classification approval | Security Lead | Any LLM provider change |
| R006 | **Retrieval Contamination** — Malicious or incorrect documents injected into the knowledge base corrupt retrieval results | Privacy | 2 | 4 | 8 | MEDIUM | Mitigate | KB ingestion pipeline requires human review approval for external documents; document hash recorded in audit trail (EVT-005) | Data Engineer | Unexpected chunk count change > 10% |
| R007 | **Differential Service Quality** — Users whose queries focus on underrepresented KB topics (e.g., non-English MLOps resources) receive systematically lower-quality answers | Bias | 3 | 3 | 9 | HIGH | Mitigate | Quarterly KB coverage audit by topic; monitor retrieval score distribution by query cluster; add underrepresented topics to ingestion backlog | ML Team Lead | Retrieval score P25 drops below 0.50 |
| R008 | **No Human Override for High-Stakes Outputs** — System has no mechanism to flag uncertain or potentially harmful responses for human review before delivery | Compliance | 3 | 4 | 12 | HIGH | Mitigate | Add confidence threshold check: if `retrieval_similarity_score < 0.40`, prepend disclaimer and offer escalation link | Product Owner | User complaint rate > 2% |
| R009 | **Vendor Model Version Drift** — Ollama pulls updated model weights silently, changing response behavior without a system deployment event | Compliance | 2 | 3 | 6 | MEDIUM | Mitigate | Pin Ollama model version in Docker image (`mistral:7b-instruct-v0.2`); model hash check on service startup | ML Platform Lead | Post-deployment behavioral anomaly |
| R010 | **Regulatory Non-Compliance (EU AI Act)** — System may be classified as a general-purpose AI system subject to transparency and documentation requirements | Compliance | 2 | 4 | 8 | MEDIUM | Accept | System Card (model-card.md) documents capabilities and limitations per Article 13; audit trail satisfies documentation requirement | Compliance Officer | Regulatory guidance update |

---

## Risk Matrix Visualization

```
Severity →
        2(Minor)   3(Moderate)   4(Major)   5(Critical)
Likely(4)            R001/R007      R003       —
Possible(3)          R002/R004/R008/R009  R003  R005
Unlikely(2)     R006    R009        R005/R006  —
```

See `docs/risk-matrix.md` for the full scored matrix with residual risk after mitigations.

---

## Residual Risk Summary

After applying all documented mitigations:

| ID | Inherent Score | Residual Score | Reduction |
|---|---|---|---|
| R003 | 16 (CRITICAL) | 8 (MEDIUM) | −50% |
| R001 | 12 (HIGH) | 4 (LOW) | −67% |
| R002 | 12 (HIGH) | 6 (MEDIUM) | −50% |
| R004 | 12 (HIGH) | 4 (LOW) | −67% |
| R007 | 9 (HIGH) | 6 (MEDIUM) | −33% |
| R008 | 12 (HIGH) | 6 (MEDIUM) | −50% |

No risks remain at CRITICAL level after mitigations. R003 (hallucination) at MEDIUM (8) is the highest residual risk and the primary focus of the next engineering sprint.
