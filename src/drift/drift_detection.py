import argparse
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # non-interactive backend for headless generation
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
from scipy import stats


# Feature importance weights (from M3 MLflow experiment and M6 RAG evaluation)
# Importance reflects how strongly each feature correlates with answer quality.

FEATURE_IMPORTANCE = {
    "retrieval_similarity_score": 0.40,
    "query_length_tokens":        0.25,
    "response_length_tokens":     0.20,
    "retrieval_result_count":     0.15,
}

PSI_THRESHOLDS = {
    "stable":     0.10,
    "moderate":   0.20,   # investigate
    # > 0.20 → significant, action required
}

N_BINS = 10
N_TIME_WINDOWS = 6   # simulate 6 weekly production snapshots


# PSI calculation

def calculate_psi(reference: np.ndarray, current: np.ndarray, n_bins: int = N_BINS) -> float:
    """
    Population Stability Index (PSI).
    Laplace smoothing (+1) prevents log(0) when a bin is empty.
    Returns PSI score; interpretable via PSI_THRESHOLDS.
    """
    _, bin_edges = np.histogram(reference, bins=n_bins)
    ref_counts, _ = np.histogram(reference, bins=bin_edges)
    cur_counts, _ = np.histogram(current, bins=bin_edges)

    # Laplace smoothing
    ref_pct = (ref_counts + 1) / (len(reference) + n_bins)
    cur_pct = (cur_counts + 1) / (len(current) + n_bins)

    psi = float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))
    return psi


def psi_severity(psi: float) -> str:
    if psi < PSI_THRESHOLDS["stable"]:
        return "stable"
    elif psi < PSI_THRESHOLDS["moderate"]:
        return "moderate"
    else:
        return "significant"


def importance_weighted_drift(psi: float, feature: str) -> float:
    """Scale PSI by normalized feature importance for prioritization."""
    importance = FEATURE_IMPORTANCE.get(feature, 0.0)
    total = sum(FEATURE_IMPORTANCE.values())
    return psi * (importance / total)


# Outlier / integrity checks

@dataclass
class IntegrityReport:
    feature: str
    n_total: int
    n_outliers: int
    outlier_pct: float
    n_missing: int
    q1: float
    q3: float
    iqr: float
    lower_fence: float
    upper_fence: float


def check_integrity(data: np.ndarray, feature: str, iqr_multiplier: float = 1.5) -> IntegrityReport:
    """IQR-based outlier detection + missing value check."""
    q1 = float(np.percentile(data, 25))
    q3 = float(np.percentile(data, 75))
    iqr = q3 - q1
    lower_fence = q1 - iqr_multiplier * iqr
    upper_fence = q3 + iqr_multiplier * iqr

    outliers = np.sum((data < lower_fence) | (data > upper_fence))
    missing = int(np.sum(np.isnan(data)))

    return IntegrityReport(
        feature=feature,
        n_total=len(data),
        n_outliers=int(outliers),
        outlier_pct=round(float(outliers) / len(data) * 100, 2),
        n_missing=missing,
        q1=round(q1, 4),
        q3=round(q3, 4),
        iqr=round(iqr, 4),
        lower_fence=round(lower_fence, 4),
        upper_fence=round(upper_fence, 4),
    )


# Synthetic reference + production data generation

def generate_reference_data(n: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    """
    Reference distributions representing training-time query patterns.
    Derived from M6 RAG evaluation (10 curated MLOps queries).
    Extrapolated to realistic production scale.
    """
    return {
        "query_length_tokens": rng.normal(18, 6, n).clip(4, 80).astype(int),
        "retrieval_similarity_score": rng.beta(6, 2.5, n),          # mean ≈ 0.71
        "response_length_tokens": rng.normal(140, 45, n).clip(20, 400).astype(int),
        "retrieval_result_count": rng.choice([0, 1, 2, 3], n,
                                              p=[0.04, 0.08, 0.13, 0.75]),
    }


def generate_drifted_data(
    reference: dict[str, np.ndarray],
    drift_factor: float,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """
    Generate a 'production' snapshot with injected drift.
    drift_factor ∈ [0, 1] controls severity: 0 = no drift, 1 = max drift.
    Models the real-world scenario where:
      - Users ask progressively longer, more complex questions (query drift)
      - KB staleness causes retrieval scores to drop (retrieval drift)
      - Longer contexts produce longer responses (response drift)
    """
    n = len(reference["query_length_tokens"])
    shift = drift_factor

    return {
        # User behavior shift: longer queries over time
        "query_length_tokens": rng.normal(18 + shift * 14, 6 + shift * 4, n
                                          ).clip(4, 120).astype(int),
        # KB staleness: retrieval scores degrade
        "retrieval_similarity_score": rng.beta(
            max(1.5, 6 - shift * 3.5),
            max(1.5, 2.5 + shift * 2.5),
            n,
        ),
        # More context → longer responses
        "response_length_tokens": rng.normal(140 + shift * 80, 45 + shift * 25, n
                                             ).clip(20, 600).astype(int),
        # KB coverage gap: more empty retrievals
        "retrieval_result_count": rng.choice(
            [0, 1, 2, 3], n,
            p=[min(0.04 + shift * 0.14, 0.18),
               min(0.08 + shift * 0.06, 0.14),
               0.13,
               max(0.75 - shift * 0.20, 0.55)],
        ),
    }


# Visualization helpers

FEATURE_UNITS = {
    "query_length_tokens":        "tokens",
    "retrieval_similarity_score": "cosine similarity",
    "response_length_tokens":     "tokens",
    "retrieval_result_count":     "count",
}

COLORS = {
    "reference": "#4C72B0",
    "production": "#DD8452",
    "stable":    "#2CA02C",
    "moderate":  "#FF7F0E",
    "significant": "#D62728",
}


def plot_drift_overview(
    reference: dict,
    current: dict,
    psi_results: dict,
    output_dir: Path,
    window_label: str = "Production (Week 6)",
):
    """Four-panel comparison plot: reference vs production for all features."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(
        f"Feature Distribution Drift: Reference vs {window_label}",
        fontsize=14,
        fontweight="bold",
    )

    for ax, feature in zip(axes.flatten(), FEATURE_IMPORTANCE.keys()):
        psi = psi_results[feature]
        severity = psi_severity(psi)
        color = COLORS[severity]
        unit = FEATURE_UNITS[feature]

        ref_data = reference[feature].astype(float)
        cur_data = current[feature].astype(float)

        bins = np.histogram_bin_edges(
            np.concatenate([ref_data, cur_data]), bins=N_BINS
        )

        ax.hist(ref_data, bins=bins, alpha=0.6, color=COLORS["reference"],
                label="Reference", density=True, edgecolor="white", linewidth=0.5)
        ax.hist(cur_data, bins=bins, alpha=0.6, color=COLORS["production"],
                label=window_label, density=True, edgecolor="white", linewidth=0.5)

        ax.set_title(
            f"{feature.replace('_', ' ').title()}\n"
            f"PSI = {psi:.3f}  ({severity.upper()})",
            fontsize=10, color=color, fontweight="bold",
        )
        ax.set_xlabel(unit, fontsize=9)
        ax.set_ylabel("Density", fontsize=9)
        ax.legend(fontsize=8)
        ax.tick_params(labelsize=8)

        # Importance-weighted score annotation
        weighted = importance_weighted_drift(psi, feature)
        ax.text(0.97, 0.95, f"IW-PSI: {weighted:.3f}",
                transform=ax.transAxes, ha="right", va="top",
                fontsize=8, color="gray")

    plt.tight_layout()
    path = output_dir / "drift_overview.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")
    return path


def plot_drift_over_time(
    time_psi: dict[str, list[float]],
    output_dir: Path,
):
    """Line chart showing PSI evolution across 6 weekly windows."""
    fig, ax = plt.subplots(figsize=(12, 5))
    weeks = [f"Week {i+1}" for i in range(N_TIME_WINDOWS)]

    for feature, psi_values in time_psi.items():
        color = COLORS[psi_severity(psi_values[-1])]
        ax.plot(weeks, psi_values, marker="o", label=feature.replace("_", " "),
                color=color, linewidth=2)

    ax.axhline(PSI_THRESHOLDS["stable"], color="orange", linestyle="--",
               linewidth=1.2, label="Investigate threshold (0.10)")
    ax.axhline(PSI_THRESHOLDS["moderate"], color="red", linestyle="--",
               linewidth=1.2, label="Action required threshold (0.20)")

    ax.set_title("PSI Over Time — 6-Week Production Window", fontsize=13, fontweight="bold")
    ax.set_xlabel("Production Window", fontsize=11)
    ax.set_ylabel("Population Stability Index (PSI)", fontsize=11)
    ax.legend(fontsize=9, loc="upper left")
    ax.set_ylim(bottom=-0.01)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = output_dir / "drift_over_time.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")
    return path


def plot_importance_weighted_heatmap(
    time_iw_psi: dict[str, list[float]],
    output_dir: Path,
):
    """Heatmap of importance-weighted PSI per feature per week."""
    weeks = [f"W{i+1}" for i in range(N_TIME_WINDOWS)]
    features = list(time_iw_psi.keys())
    data = np.array([time_iw_psi[f] for f in features])

    fig, ax = plt.subplots(figsize=(10, 4))
    im = ax.imshow(data, aspect="auto", cmap="YlOrRd", vmin=0, vmax=0.12)

    ax.set_xticks(range(N_TIME_WINDOWS))
    ax.set_xticklabels(weeks, fontsize=10)
    ax.set_yticks(range(len(features)))
    ax.set_yticklabels([f.replace("_", "\n") for f in features], fontsize=9)

    for i in range(len(features)):
        for j in range(N_TIME_WINDOWS):
            ax.text(j, i, f"{data[i, j]:.3f}", ha="center", va="center",
                    fontsize=8, color="black" if data[i, j] < 0.06 else "white")

    fig.colorbar(im, ax=ax, label="Importance-Weighted PSI")
    ax.set_title("Importance-Weighted Drift Heatmap (Higher = More Urgent)",
                 fontsize=12, fontweight="bold")

    plt.tight_layout()
    path = output_dir / "drift_heatmap.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")
    return path


def plot_integrity_summary(integrity_reports: list[IntegrityReport], output_dir: Path):
    """Bar chart: outlier percentage per feature."""
    features = [r.feature.replace("_", "\n") for r in integrity_reports]
    pcts = [r.outlier_pct for r in integrity_reports]
    colors = ["#D62728" if p > 5 else "#FF7F0E" if p > 2 else "#2CA02C" for p in pcts]

    fig, ax = plt.subplots(figsize=(9, 4))
    bars = ax.bar(features, pcts, color=colors, edgecolor="white", linewidth=0.8)

    for bar, pct in zip(bars, pcts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                f"{pct:.1f}%", ha="center", va="bottom", fontsize=9)

    ax.axhline(5.0, color="red", linestyle="--", linewidth=1.2, label="5% alert threshold")
    ax.axhline(2.0, color="orange", linestyle="--", linewidth=1.2, label="2% warning threshold")

    ax.set_title("Data Integrity: Outlier Percentage by Feature (Production Data)",
                 fontsize=12, fontweight="bold")
    ax.set_ylabel("Outlier %", fontsize=11)
    ax.legend(fontsize=9)
    ax.set_ylim(0, max(pcts) * 1.3 + 1)
    ax.grid(True, axis="y", alpha=0.3)

    plt.tight_layout()
    path = output_dir / "integrity_summary.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")
    return path


# Main driver

def run_drift_analysis(seed: int, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    N_REF = 2000
    N_PROD = 1000

    print("\n  Generating reference and production distributions...")
    reference = generate_reference_data(N_REF, rng)

    # Simulate PSI across 6 weekly production snapshots
    # Drift factor increases gradually: simulates realistic KB staleness over 6 weeks
    drift_factors = [0.02, 0.04, 0.07, 0.11, 0.15, 0.20]
    time_psi: dict[str, list[float]] = {f: [] for f in FEATURE_IMPORTANCE}
    time_iw_psi: dict[str, list[float]] = {f: [] for f in FEATURE_IMPORTANCE}

    for week_i, df in enumerate(drift_factors):
        prod_data = generate_drifted_data(reference, df, rng)
        for feature in FEATURE_IMPORTANCE:
            psi = calculate_psi(reference[feature].astype(float),
                                prod_data[feature].astype(float))
            iw = importance_weighted_drift(psi, feature)
            time_psi[feature].append(round(psi, 4))
            time_iw_psi[feature].append(round(iw, 4))

    # Use week-6 (most drifted) for detailed analysis
    current = generate_drifted_data(reference, drift_factors[-1], rng)
    psi_results = {
        f: calculate_psi(reference[f].astype(float), current[f].astype(float))
        for f in FEATURE_IMPORTANCE
    }

    # Integrity checks on production data
    integrity_reports = [
        check_integrity(current[f].astype(float), f)
        for f in FEATURE_IMPORTANCE
    ]

    # Identify top drifting feature
    top_feature = max(psi_results, key=lambda f: psi_results[f])
    top_psi = psi_results[top_feature]

    # Business impact: retrieval_similarity_score PSI of 0.23 historically
    # correlates with ~5% drop in task completion rate (from M6 RAG evaluation)
    score_psi = psi_results["retrieval_similarity_score"]
    estimated_completion_drop = max(0.0, (score_psi - 0.10) * 0.25) * 100

    print("\n  Generating visualizations...")
    plt.rcParams.update({"figure.dpi": 150, "font.size": 10})

    plot_drift_overview(reference, current, psi_results, output_dir)
    plot_drift_over_time(time_psi, output_dir)
    plot_importance_weighted_heatmap(time_iw_psi, output_dir)
    plot_integrity_summary(integrity_reports, output_dir)

    return {
        "analysis_date": datetime.now().isoformat(),
        "seed": seed,
        "n_reference": N_REF,
        "n_production": N_PROD,
        "n_time_windows": N_TIME_WINDOWS,
        "psi_results": {f: round(v, 4) for f, v in psi_results.items()},
        "importance_weighted_psi": {
            f: round(importance_weighted_drift(psi_results[f], f), 4)
            for f in FEATURE_IMPORTANCE
        },
        "psi_severity": {f: psi_severity(psi_results[f]) for f in FEATURE_IMPORTANCE},
        "top_drifting_feature": top_feature,
        "top_psi": round(top_psi, 4),
        "estimated_task_completion_drop_pct": round(estimated_completion_drop, 1),
        "time_series_psi": time_psi,
        "integrity_reports": [asdict(r) for r in integrity_reports],
        "recommended_action": (
            "Trigger knowledge base re-ingestion and schedule model retraining. "
            "Alert on retrieval_similarity_score PSI > 0.20."
        ) if top_psi > 0.20 else (
            "Monitor weekly. Consider KB refresh if retrieval scores continue declining."
        ),
    }


def print_drift_report(results: dict):
    print("\n" + "=" * 60)
    print("  DRIFT DETECTION REPORT")
    print("=" * 60)

    print(f"\n  PSI Results (Week 6 vs Reference):")
    print(f"  {'Feature':<35} {'PSI':>6}  {'Severity':<12} {'IW-PSI':>7}")
    print(f"  {'-'*35} {'-'*6}  {'-'*12} {'-'*7}")
    for f in FEATURE_IMPORTANCE:
        psi = results["psi_results"][f]
        sev = results["psi_severity"][f]
        iw = results["importance_weighted_psi"][f]
        print(f"  {f:<35} {psi:>6.4f}  {sev:<12} {iw:>7.4f}")

    print(f"\n  Top drifting feature  : {results['top_drifting_feature']} (PSI={results['top_psi']:.4f})")
    print(f"  Est. completion drop  : ~{results['estimated_task_completion_drop_pct']:.1f}%")
    print(f"\n  Recommendation: {results['recommended_action']}")

    print(f"\n  Data Integrity (outliers in production data):")
    for ir in results["integrity_reports"]:
        flag = "⚠" if ir["outlier_pct"] > 2 else "✓"
        print(f"  {flag} {ir['feature']:<35}: {ir['outlier_pct']:.1f}% outliers  "
              f"(missing: {ir['n_missing']})")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run drift detection analysis.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="visualizations")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    print(f"\nRunning drift analysis → saving plots to {output_dir}/")

    results = run_drift_analysis(seed=args.seed, output_dir=output_dir)
    print_drift_report(results)

    # Save JSON summary
    summary_path = output_dir / "drift_summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  JSON summary saved: {summary_path}")


if __name__ == "__main__":
    main()
