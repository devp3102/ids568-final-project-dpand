# Memo to CTO: AI Governance & Risk Findings

**To:** Chief Technology Officer  
**From:** ML Platform Team 
**Date:** 2026-05-01  
**Subject:** RAG-LLM Query Assistant v1.1.0 — Production Readiness Assessment

---

## Executive Summary

We have completed a full operational review of the RAG-LLM Query Assistant — our internal MLOps knowledge retrieval system. The system is **conditionally ready for limited production use**, but three issues require resolution before broader rollout:

1. **Hallucination risk on queries without matching knowledge base coverage** — currently unmitigated in the user interface
2. **A/B test shows significant retrieval improvement but a latency SLA breach** — top-k=5 configuration cannot ship yet without engineering optimization
3. **Knowledge base requires a weekly automated refresh cadence** — six weeks of production data shows measurable retrieval quality drift

No critical unmitigated risks remain. All findings have concrete, prioritized action items below.

---

## Key Findings

### 1. The System Is Healthy Under Normal Load

- P99 end-to-end latency: **1.80 seconds** (vs. 3.0s SLA) — 40% margin
- Error rate: **1.2%** (vs. 5% threshold)
- Cache hit ratio: **38%** — reducing redundant LLM compute by over one-third
- Uptime since deployment: 100% (no incidents in 30-day operational window)

The Prometheus/Grafana dashboard provides real-time visibility into all four system health dimensions: infrastructure, latency, LLM behavior, and retrieval quality.

### 2. Retrieval Quality Degrades Without Regular Knowledge Base Maintenance

Our drift analysis shows that after six weeks of production operation, retrieval similarity scores drift significantly (PSI = 0.25, exceeding the action threshold of 0.20). This translates to an estimated **3.8 percentage point drop** in task completion rate.

The root cause is straightforward: the MLOps knowledge domain evolves faster than our current manual refresh cadence. A weekly automated KB re-ingestion process would reduce the maximum staleness window from 6 weeks to 1 week, containing the quality impact to under 1 percentage point.

**Estimated engineering effort:** 2 days. **Expected business impact:** prevents silent quality erosion that users would otherwise attribute to the system being "unreliable."

### 3. The Planned Retrieval Improvement Needs One More Engineering Step

We ran a statistically rigorous A/B test comparing our current retrieval configuration (top-k=3) against a deeper retrieval setting (top-k=5). Results:

- Task completion rate: **+7.1% improvement** (p < 0.00001, Bonferroni-corrected)
- Retrieval quality: **+5.7% improvement**
- **However:** P99 latency increased from 2.79s to 3.22s — breaching our 3.0s SLA

We are not shipping top-k=5 until the latency issue is resolved. The recommended engineering solution (contextual compression of retrieved documents before prompt assembly) is estimated to recover 300ms from P99, bringing the treatment back within SLA. We expect to re-run the experiment and ship by 2026-05-17.

### 4. One High-Priority User Safety Gap Remains Open

Approximately 3.8% of queries return no matching documents from the knowledge base. In these cases, the LLM generates answers from its parametric memory alone — without any grounding — significantly increasing hallucination risk. Users currently receive no indication that this has occurred.

This is the highest-residual-risk item on our register (score = 8/25 after mitigations). Adding a simple UI disclaimer ("No matching documentation found — this response may not be accurate") would reduce the risk substantially with minimal engineering effort.

---

## Recommended Actions (Prioritized)

| Priority | Action | Owner | Deadline | Effort |
|---|---|---|---|---|
| P0 | Add empty-retrieval disclaimer to response | Product Owner | 2026-05-08 | 1 day |
| P1 | Implement weekly automated KB re-ingestion | Data Engineer | 2026-05-15 | 2 days |
| P1 | Implement contextual compression; re-run A/B test | ML Engineer | 2026-05-17 | 3 days |
| P2 | Add confidence-based escalation for low-score retrievals | Product Owner | 2026-05-31 | 2 days |
| P2 | Pin Ollama version in Docker image | ML Platform Lead | 2026-05-10 | 0.5 days |
| P3 | Draft user-facing PII policy | Compliance Officer | 2026-06-15 | 2 days |

---

## What We Are Not Doing (and Why)

- **Not replacing Ollama with a cloud LLM provider** — local inference eliminates third-party data exposure risk. Cloud migration would require a full privacy review and vendor DPA negotiation before any deployment.
- **Not implementing real-time hallucination scoring** — requires a judge-LLM pipeline with batch latency incompatible with sub-2-second SLA. Periodic quality audits (20 queries/week) are the appropriate mechanism.
- **Not shipping top-k=5** — the improvement is real and statistically validated, but we will not breach our own SLA to ship it. Contextual compression is the right path.

---

## Bottom Line

The RAG-LLM Query Assistant is operationally sound. With the P0 safety fix (empty-retrieval disclaimer) deployed by May 8 and weekly KB automation by May 15, the system will meet all documented SLAs and risk thresholds. The A/B-validated retrieval improvement will ship by May 17 after the latency fix. I recommend proceeding with limited production rollout now and full rollout upon completion of P1 actions.

*Full technical detail: `docs/governance-review.md`, `docs/risk-matrix.md`, `docs/drift-diagnostic-report.md`, `docs/experiment-specification.md`*
