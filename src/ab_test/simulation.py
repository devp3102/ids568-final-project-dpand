import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from typing import Optional

import numpy as np
from scipy import stats


# Experiment specification

EXPERIMENT_NAME = "rag_topk_optimization_v1"
CONTROL_LABEL = "top_k=3"
TREATMENT_LABEL = "top_k=5"

# Power analysis parameters
BASELINE_COMPLETION_RATE = 0.62   # 62% of users complete task without re-querying
TARGET_MDE = 0.05                  # minimum detectable effect: +5 pp
ALPHA = 0.05                       # significance level
POWER = 0.80                       # desired statistical power

# Guardrail thresholds
MAX_P99_LATENCY_S = 3.0
MAX_ERROR_RATE_DELTA = 0.005       # treatment error rate must not exceed control + 0.5%
MAX_COST_PER_QUERY_USD = 0.015


# Deterministic user assignment (mirrors production routing)

def get_variant(user_id: str, experiment: str, control_weight: float = 0.5) -> str:
    """Deterministic assignment: same user always gets the same variant."""
    hash_input = f"{user_id}:{experiment}"
    hash_val = hashlib.md5(hash_input.encode()).hexdigest()
    bucket = int(hash_val[:8], 16) / (16**8)
    return CONTROL_LABEL if bucket < control_weight else TREATMENT_LABEL


# Sample size calculation

def calculate_sample_size(
    baseline_rate: float,
    mde: float,
    alpha: float = ALPHA,
    power: float = POWER,
) -> int:
    """
    Two-proportion sample size via Cohen's h.
    Returns the per-group sample size needed.
    """
    p1 = baseline_rate
    p2 = baseline_rate + mde

    # Cohen's h effect size for proportions
    h = 2 * (np.arcsin(np.sqrt(p2)) - np.arcsin(np.sqrt(p1)))

    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_power = stats.norm.ppf(power)

    n = 2 * ((z_alpha + z_power) / h) ** 2
    return int(np.ceil(n))


# Simulation: generate outcome distributions

@dataclass
class GroupOutcomes:
    label: str
    n: int
    # Primary binary metric: task completion (no re-query)
    completion_outcomes: np.ndarray      # 0/1 array
    # Secondary continuous metric: mean retrieval similarity score
    retrieval_scores: np.ndarray
    # Guardrail: P99 end-to-end latency
    latencies_s: np.ndarray
    # Guardrail: error flag per request
    error_flags: np.ndarray

    @property
    def completion_rate(self) -> float:
        return float(self.completion_outcomes.mean())

    @property
    def mean_retrieval_score(self) -> float:
        return float(self.retrieval_scores.mean())

    @property
    def p99_latency(self) -> float:
        return float(np.percentile(self.latencies_s, 99))

    @property
    def error_rate(self) -> float:
        return float(self.error_flags.mean())

    @property
    def mean_cost_per_query(self) -> float:
        # Cost proxy: $0.010 base + $0.001 per extra retrieved doc (top_k=5 costs slightly more)
        extra_docs = 2 if self.label == TREATMENT_LABEL else 0
        return 0.010 + extra_docs * 0.001


def simulate_group(
    label: str,
    n: int,
    completion_rate: float,
    retrieval_score_mean: float,
    latency_mean_s: float,
    latency_std_s: float,
    error_rate: float,
    rng: np.random.Generator,
) -> GroupOutcomes:
    """Generate synthetic outcomes for one experiment arm."""
    completion_outcomes = (rng.random(n) < completion_rate).astype(int)
    retrieval_scores = np.clip(rng.normal(retrieval_score_mean, 0.12, n), 0.0, 1.0)
    latencies = np.clip(rng.lognormal(
        mean=np.log(latency_mean_s),
        sigma=latency_std_s,
        size=n,
    ), 0.1, 30.0)
    error_flags = (rng.random(n) < error_rate).astype(int)

    return GroupOutcomes(
        label=label,
        n=n,
        completion_outcomes=completion_outcomes,
        retrieval_scores=retrieval_scores,
        latencies_s=latencies,
        error_flags=error_flags,
    )


# Statistical tests

@dataclass
class TestResult:
    metric: str
    control_value: float
    treatment_value: float
    delta: float
    relative_lift_pct: float
    test_type: str
    statistic: float
    p_value: float
    ci_lower: float
    ci_upper: float
    significant_raw: bool
    significant_bonferroni: bool


def two_proportion_ztest(
    control_successes: int,
    control_n: int,
    treatment_successes: int,
    treatment_n: int,
    alpha: float = ALPHA,
) -> tuple[float, float, float, float]:
    """
    Two-proportion z-test.
    Returns (z_stat, p_value, ci_lower, ci_upper) where CI is on the difference.
    """
    p_c = control_successes / control_n
    p_t = treatment_successes / treatment_n
    p_pool = (control_successes + treatment_successes) / (control_n + treatment_n)

    se_pool = np.sqrt(p_pool * (1 - p_pool) * (1 / control_n + 1 / treatment_n))
    if se_pool == 0:
        return 0.0, 1.0, 0.0, 0.0

    z = (p_t - p_c) / se_pool
    p_val = 2 * (1 - stats.norm.cdf(abs(z)))

    # CI on the raw difference (p_t - p_c)
    se_diff = np.sqrt(p_c * (1 - p_c) / control_n + p_t * (1 - p_t) / treatment_n)
    z_crit = stats.norm.ppf(1 - alpha / 2)
    ci_lo = (p_t - p_c) - z_crit * se_diff
    ci_hi = (p_t - p_c) + z_crit * se_diff

    return z, p_val, ci_lo, ci_hi


def welch_ttest(
    control_values: np.ndarray,
    treatment_values: np.ndarray,
    alpha: float = ALPHA,
) -> tuple[float, float, float, float]:
    """
    Welch's t-test for continuous metrics (unequal variance).
    Returns (t_stat, p_value, ci_lower, ci_upper) on mean difference.
    """
    t, p_val = stats.ttest_ind(treatment_values, control_values, equal_var=False)

    # Bootstrap 95% CI on the mean difference
    diff = treatment_values.mean() - control_values.mean()
    se = np.sqrt(treatment_values.var(ddof=1) / len(treatment_values)
                 + control_values.var(ddof=1) / len(control_values))
    df = (
        (se**2) ** 2
        / (
            (treatment_values.var(ddof=1) / len(treatment_values)) ** 2 / (len(treatment_values) - 1)
            + (control_values.var(ddof=1) / len(control_values)) ** 2 / (len(control_values) - 1)
        )
    )
    t_crit = stats.t.ppf(1 - alpha / 2, df=df)
    ci_lo = diff - t_crit * se
    ci_hi = diff + t_crit * se

    return t, p_val, ci_lo, ci_hi


def bonferroni_correction(p_values: list[float], alpha: float = ALPHA) -> list[bool]:
    """Return significance flags after Bonferroni correction."""
    adjusted_alpha = alpha / len(p_values)
    return [p < adjusted_alpha for p in p_values]


# Guardrail checks

@dataclass
class GuardrailResult:
    name: str
    control_value: float
    treatment_value: float
    threshold: str
    passed: bool
    note: str


def check_guardrails(control: GroupOutcomes, treatment: GroupOutcomes) -> list[GuardrailResult]:
    results = []

    # 1. P99 latency
    latency_ok = treatment.p99_latency <= MAX_P99_LATENCY_S
    results.append(GuardrailResult(
        name="P99 Latency",
        control_value=control.p99_latency,
        treatment_value=treatment.p99_latency,
        threshold=f"≤ {MAX_P99_LATENCY_S}s",
        passed=latency_ok,
        note="Treatment P99 within SLA" if latency_ok else "FAIL: exceeds 3.0s SLA",
    ))

    # 2. Error rate delta
    error_delta = treatment.error_rate - control.error_rate
    error_ok = error_delta <= MAX_ERROR_RATE_DELTA
    results.append(GuardrailResult(
        name="Error Rate Delta",
        control_value=control.error_rate,
        treatment_value=treatment.error_rate,
        threshold=f"delta ≤ {MAX_ERROR_RATE_DELTA:.1%}",
        passed=error_ok,
        note="Error rate acceptable" if error_ok else f"FAIL: delta={error_delta:.3%}",
    ))

    # 3. Cost per query
    cost_ok = treatment.mean_cost_per_query <= MAX_COST_PER_QUERY_USD
    results.append(GuardrailResult(
        name="Cost Per Query",
        control_value=control.mean_cost_per_query,
        treatment_value=treatment.mean_cost_per_query,
        threshold=f"≤ ${MAX_COST_PER_QUERY_USD:.3f}",
        passed=cost_ok,
        note="Cost acceptable" if cost_ok else f"FAIL: ${treatment.mean_cost_per_query:.4f}",
    ))

    return results


# Decision logic

def make_recommendation(
    primary_significant: bool,
    primary_positive: bool,
    guardrails_passed: bool,
    ci_lower: float,
) -> tuple[str, str]:
    """
    Returns (decision_code, rationale).
    Follows the recommendation table from Module 8 slides.
    """
    if primary_significant and primary_positive and guardrails_passed:
        return "SHIP_TREATMENT", (
            "Primary metric is significantly improved (p < 0.05), lift is positive, "
            "and all guardrail metrics pass. Ship top-k=5 to 100% of traffic."
        )
    elif primary_significant and primary_positive and not guardrails_passed:
        return "INVESTIGATE", (
            "Primary metric improved but a guardrail failed. "
            "Investigate the guardrail violation before shipping."
        )
    elif primary_significant and not primary_positive:
        return "KEEP_CONTROL", (
            "Treatment significantly degrades the primary metric. "
            "Keep top-k=3 as the serving configuration."
        )
    elif not primary_significant and ci_lower < -0.02:
        return "EXTEND_EXPERIMENT", (
            "Not significant yet; confidence interval includes meaningful negative values. "
            "Collect more data before deciding."
        )
    else:
        return "NO_DIFFERENCE", (
            "No statistically significant difference detected and CI is narrow. "
            "Consider other improvement vectors."
        )


# Main simulation runner

def run_simulation(n_per_group: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)

    # --- Simulate control arm (top_k=3) ---
    control = simulate_group(
        label=CONTROL_LABEL,
        n=n_per_group,
        completion_rate=BASELINE_COMPLETION_RATE,          # 62%
        retrieval_score_mean=0.72,
        latency_mean_s=1.10,
        latency_std_s=0.40,
        error_rate=0.018,
        rng=rng,
    )

    # --- Simulate treatment arm (top_k=5) ---
    # Treatment improves completion rate by ~6 pp and retrieval score by ~0.04
    # but adds ~120ms mean latency due to fetching extra docs
    treatment = simulate_group(
        label=TREATMENT_LABEL,
        n=n_per_group,
        completion_rate=BASELINE_COMPLETION_RATE + 0.058,  # +5.8 pp
        retrieval_score_mean=0.76,
        latency_mean_s=1.22,
        latency_std_s=0.42,
        error_rate=0.020,
        rng=rng,
    )

    # Statistical tests
    # Primary: task completion rate (binary → z-test)
    z, p_comp, ci_lo_comp, ci_hi_comp = two_proportion_ztest(
        int(control.completion_outcomes.sum()), control.n,
        int(treatment.completion_outcomes.sum()), treatment.n,
    )
    primary_result = TestResult(
        metric="task_completion_rate",
        control_value=control.completion_rate,
        treatment_value=treatment.completion_rate,
        delta=treatment.completion_rate - control.completion_rate,
        relative_lift_pct=(treatment.completion_rate - control.completion_rate)
                           / control.completion_rate * 100,
        test_type="two_proportion_z_test",
        statistic=z,
        p_value=p_comp,
        ci_lower=ci_lo_comp,
        ci_upper=ci_hi_comp,
        significant_raw=p_comp < ALPHA,
        significant_bonferroni=False,  # set below
    )

    # Secondary: mean retrieval similarity score (continuous → Welch's t-test)
    t, p_score, ci_lo_score, ci_hi_score = welch_ttest(
        control.retrieval_scores,
        treatment.retrieval_scores,
    )
    secondary_result = TestResult(
        metric="mean_retrieval_similarity_score",
        control_value=control.mean_retrieval_score,
        treatment_value=treatment.mean_retrieval_score,
        delta=treatment.mean_retrieval_score - control.mean_retrieval_score,
        relative_lift_pct=(treatment.mean_retrieval_score - control.mean_retrieval_score)
                           / control.mean_retrieval_score * 100,
        test_type="welch_t_test",
        statistic=t,
        p_value=p_score,
        ci_lower=ci_lo_score,
        ci_upper=ci_hi_score,
        significant_raw=p_score < ALPHA,
        significant_bonferroni=False,
    )

    # Bonferroni correction across both tests
    bonferroni_flags = bonferroni_correction([p_comp, p_score])
    primary_result.significant_bonferroni = bonferroni_flags[0]
    secondary_result.significant_bonferroni = bonferroni_flags[1]

    # Guardrail checks 
    guardrails = check_guardrails(control, treatment)
    guardrails_all_pass = all(g.passed for g in guardrails)

    # Decision
    decision, rationale = make_recommendation(
        primary_significant=primary_result.significant_raw,
        primary_positive=primary_result.delta > 0,
        guardrails_passed=guardrails_all_pass,
        ci_lower=ci_lo_comp,
    )

    return {
        "experiment": EXPERIMENT_NAME,
        "seed": seed,
        "n_per_group": n_per_group,
        "power_analysis": {
            "baseline_completion_rate": BASELINE_COMPLETION_RATE,
            "minimum_detectable_effect": TARGET_MDE,
            "alpha": ALPHA,
            "power": POWER,
            "required_n_per_group": calculate_sample_size(
                BASELINE_COMPLETION_RATE, TARGET_MDE, ALPHA, POWER
            ),
        },
        "control": {
            "label": control.label,
            "n": control.n,
            "completion_rate": round(control.completion_rate, 4),
            "mean_retrieval_score": round(control.mean_retrieval_score, 4),
            "p99_latency_s": round(control.p99_latency, 4),
            "error_rate": round(control.error_rate, 4),
            "mean_cost_per_query_usd": round(control.mean_cost_per_query, 5),
        },
        "treatment": {
            "label": treatment.label,
            "n": treatment.n,
            "completion_rate": round(treatment.completion_rate, 4),
            "mean_retrieval_score": round(treatment.mean_retrieval_score, 4),
            "p99_latency_s": round(treatment.p99_latency, 4),
            "error_rate": round(treatment.error_rate, 4),
            "mean_cost_per_query_usd": round(treatment.mean_cost_per_query, 5),
        },
        "statistical_tests": [
            asdict(primary_result),
            asdict(secondary_result),
        ],
        "guardrails": [asdict(g) for g in guardrails],
        "decision": decision,
        "rationale": rationale,
    }


# CLI entry point

def print_report(results: dict):
    print("\n" + "=" * 65)
    print(f"  A/B TEST REPORT: {results['experiment']}")
    print("=" * 65)

    pa = results["power_analysis"]
    print(f"\n  Power Analysis")
    print(f"  ─────────────")
    print(f"  Baseline completion rate : {pa['baseline_completion_rate']:.0%}")
    print(f"  Min detectable effect    : +{pa['minimum_detectable_effect']:.0%}")
    print(f"  Alpha / Power            : {pa['alpha']} / {pa['power']}")
    print(f"  Required n per group     : {pa['required_n_per_group']:,}")
    print(f"  Actual n per group       : {results['n_per_group']:,}  "
          f"({'✓ powered' if results['n_per_group'] >= pa['required_n_per_group'] else '✗ underpowered'})")

    print(f"\n  Group Results")
    print(f"  ─────────────")
    c, t = results["control"], results["treatment"]
    headers = ["Metric", "Control (k=3)", "Treatment (k=5)"]
    rows = [
        ["Completion rate", f"{c['completion_rate']:.1%}", f"{t['completion_rate']:.1%}"],
        ["Mean retrieval score", f"{c['mean_retrieval_score']:.4f}", f"{t['mean_retrieval_score']:.4f}"],
        ["P99 latency (s)", f"{c['p99_latency_s']:.3f}", f"{t['p99_latency_s']:.3f}"],
        ["Error rate", f"{c['error_rate']:.2%}", f"{t['error_rate']:.2%}"],
        ["Cost per query ($)", f"{c['mean_cost_per_query_usd']:.5f}", f"{t['mean_cost_per_query_usd']:.5f}"],
    ]
    col_w = [max(len(r[i]) for r in [headers] + rows) + 2 for i in range(3)]
    print("  " + "  ".join(h.ljust(col_w[i]) for i, h in enumerate(headers)))
    print("  " + "  ".join("-" * w for w in col_w))
    for row in rows:
        print("  " + "  ".join(v.ljust(col_w[i]) for i, v in enumerate(row)))

    print(f"\n  Statistical Tests")
    print(f"  ─────────────────")
    for test in results["statistical_tests"]:
        sig = "✓ SIGNIFICANT" if test["significant_raw"] else "✗ not significant"
        bonf = "✓ after Bonferroni" if test["significant_bonferroni"] else "✗ fails Bonferroni"
        print(f"\n  [{test['metric']}]")
        print(f"  Delta       : {test['delta']:+.4f}  ({test['relative_lift_pct']:+.2f}%)")
        print(f"  95% CI      : [{test['ci_lower']:+.4f}, {test['ci_upper']:+.4f}]")
        print(f"  {test['test_type']}: statistic={test['statistic']:.4f}, p={test['p_value']:.6f}")
        print(f"  Significance: {sig}  |  {bonf}")

    print(f"\n  Guardrails")
    print(f"  ──────────")
    for g in results["guardrails"]:
        status = "✓ PASS" if g["passed"] else "✗ FAIL"
        print(f"  {status}  {g['name']} — {g['note']}")

    print(f"\n  Decision: {results['decision']}")
    print(f"  ─────────")
    print(f"  {results['rationale']}")
    print("\n" + "=" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run the RAG top-k A/B test simulation.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--n-per-group", type=int, default=5000,
                        help="Observations per group (default: 5000)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON instead of formatted report")
    args = parser.parse_args()

    required_n = calculate_sample_size(BASELINE_COMPLETION_RATE, TARGET_MDE, ALPHA, POWER)
    if args.n_per_group < required_n:
        print(f"WARNING: n_per_group={args.n_per_group} is below the required {required_n} "
              f"for {POWER:.0%} power at MDE={TARGET_MDE:.0%}. Results may be unreliable.",
              file=sys.stderr)

    results = run_simulation(n_per_group=args.n_per_group, seed=args.seed)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_report(results)


if __name__ == "__main__":
    main()
