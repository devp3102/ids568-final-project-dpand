# A/B Test Recommendation Memo

**To:** Engineering Lead, Product  
**From:** ML Platform Team  
**Date:** 2026-05-01  
**Re:** Experiment `rag_topk_optimization_v1` — top-k=3 vs top-k=5  
**Decision: INVESTIGATE (do not ship yet)**

---

## Executive Summary

The top-k=5 treatment significantly improves task completion rate (+7.1%, p < 0.00001) and retrieval similarity (+5.7%, p < 0.00001). **However, the P99 end-to-end latency in the treatment group reaches 3.22 seconds — exceeding our 3.0-second SLA guardrail.** Until the latency issue is resolved, we should not ship top-k=5 to 100% of traffic.

---

## Statistical Results

| Metric | Control (k=3) | Treatment (k=5) | Delta | p-value | Significant? |
|---|---|---|---|---|---|
| Task completion rate | 62.9% | 67.4% | **+4.5 pp (+7.1%)** | 0.000003 | ✓ Yes (Bonferroni) |
| Mean retrieval score | 0.719 | 0.760 | **+0.041 (+5.7%)** | <0.000001 | ✓ Yes (Bonferroni) |

95% CI for completion rate delta: [+2.6 pp, +6.4 pp] — the entire interval is positive and above the MDE threshold of 5 pp. The treatment effect is real.

## Guardrail Status

| Guardrail | Control | Treatment | Threshold | Result |
|---|---|---|---|---|
| P99 Latency | 2.79s | **3.22s** | ≤ 3.0s | **✗ FAIL** |
| Error rate delta | 2.22% | 1.92% | ≤ +0.5% | ✓ PASS |
| Cost per query | $0.010 | $0.012 | ≤ $0.015 | ✓ PASS |

The P99 latency breach is driven by longer prompt assembly when two additional documents are included. The LLM prompt grows by ~200–350 tokens per query, adding ~420ms to P99 under the current Ollama configuration.

---

## Recommendation

**Do not ship top-k=5 in its current form.** Pursue one of three paths:

### Path A (Recommended): Contextual Compression
Apply a compression step after retrieval: summarize each retrieved document chunk to ≤100 tokens before prompt assembly. Expected P99 reduction: ~300ms. Re-run A/B test with compressed context; the completion rate benefit should be preserved with reduced latency overhead.

### Path B: Dynamic top-k
Default to top-k=3 but increase to top-k=5 only when the top-1 retrieval score falls below 0.60 (indicating weak retrieval). This selectively applies richer context where it is most needed without the blanket latency penalty.

### Path C: Extend experiment with SLA relaxation request
If the product team determines that 3.2s P99 is acceptable given the +7% completion rate improvement, formally update the SLA threshold. This requires sign-off from the engineering lead and a user-experience review.

---

## Next Steps

1. Implement Path A (contextual compression) by 2026-05-10
2. Re-run experiment with same randomization seed and n=5,000 per group
3. If P99 ≤ 3.0s and completion rate delta ≥ +5 pp: ship treatment
4. Model card (Component 3) will be updated to reflect the new top-k configuration upon ship decision
