# IDS568 Final Project: Monitoring, Governance & Reflection
---

## System Overview

This project builds a complete production operations framework around the **RAG-LLM Query Assistant** — a Retrieval-Augmented Generation pipeline that answers MLOps questions by retrieving relevant documentation chunks (FAISS + sentence-transformers) and generating grounded responses (Ollama / Mistral 7B). The system was developed across Milestones 5 and 6 of this course.

The final project adds five production-readiness layers on top of that system:

| Component | What it covers |
|---|---|
| C1: Production Monitoring | Prometheus metrics instrumentation + Grafana dashboard |
| C2: A/B Test Design & Simulation | top-k=3 vs top-k=5 retrieval experiment with full statistical analysis |
| C3: Model Card & Governance | System Card, lineage diagram, risk register, audit trail |
| C4: Data Integrity & Drift Detection | PSI-based feature drift over 6 weekly windows, impact analysis |
| C5: AI Risk Assessment | System boundary diagram, risk matrix, CTO memo |

---

## Component Deliverables

### Component 1 — Production Monitoring Dashboard

| File | Description |
|---|---|
| [src/monitoring/instrumentation.py](src/monitoring/instrumentation.py) | FastAPI service with Prometheus metrics: latency, TTFT, token throughput, cache hits, retrieval scores |
| [src/monitoring/traffic_simulator.py](src/monitoring/traffic_simulator.py) | Synthetic traffic generator to populate dashboard metrics |
| [config/prometheus.yml](config/prometheus.yml) | Prometheus scrape configuration |
| [dashboards/grafana-export.json](dashboards/grafana-export.json) | Grafana dashboard JSON (importable) |
| [screenshots/dashboard-simulated.png](screenshots/dashboard-simulated.png) | Dashboard screenshot with simulated traffic |
| [docs/dashboard-interpretation.md](docs/dashboard-interpretation.md) | Interpretation: system health, bottlenecks, alert conditions, design justification |

### Component 2 — A/B Test Design & Simulation

| File | Description |
|---|---|
| [docs/experiment-specification.md](docs/experiment-specification.md) | Hypothesis, metrics, randomization, power analysis, stopping rules |
| [src/ab_test/simulation.py](src/ab_test/simulation.py) | Full simulation: A/B distributions, z-test, t-test, Bonferroni correction, guardrails, decision |
| [notebooks/ab_analysis.ipynb](notebooks/ab_analysis.ipynb) | Interactive analysis: power curves, CI visualization, sensitivity analysis across 20 seeds |
| [docs/recommendation-memo.md](docs/recommendation-memo.md) | Decision memo: INVESTIGATE — significant improvement but P99 latency SLA breach |

### Component 3 — Model Card & Governance Packet

| File | Description |
|---|---|
| [docs/model-card.md](docs/model-card.md) | System Card: deployment config, performance metrics, limitations, ethical risks |
| [docs/lineage-diagram.png](docs/lineage-diagram.png) | Data → embedding → indexing → inference → monitoring lineage |
| [docs/risk-register.md](docs/risk-register.md) | 10-item risk register: bias, robustness, privacy, compliance categories with mitigations |
| [logs/audit-trail.json](logs/audit-trail.json) | 8-event hash-chained audit trail: deployments, KB updates, drift alerts, config changes |

### Component 4 — Data Integrity & Drift Detection

| File | Description |
|---|---|
| [src/drift/drift_detection.py](src/drift/drift_detection.py) | PSI drift detection across 6 weekly windows + IQR integrity checks |
| [visualizations/drift_overview.png](visualizations/drift_overview.png) | Reference vs production distributions for all 4 features (Week 6) |
| [visualizations/drift_over_time.png](visualizations/drift_over_time.png) | PSI time series: 6 weekly production windows |
| [visualizations/drift_heatmap.png](visualizations/drift_heatmap.png) | Importance-weighted PSI heatmap |
| [visualizations/integrity_summary.png](visualizations/integrity_summary.png) | Outlier percentage by feature |
| [docs/drift-diagnostic-report.md](docs/drift-diagnostic-report.md) | Which features drifted, business impact (~3.8% completion drop), intervention plan |

### Component 5 — AI Risk Assessment & Reflective Summary

| File | Description |
|---|---|
| [docs/system-boundary-diagram.png](docs/system-boundary-diagram.png) | Trust boundary diagram: risks and mitigations at each system boundary crossing |
| [docs/governance-review.md](docs/governance-review.md) | Structured review: data security, retrieval risks, hallucination, tool-misuse, compliance |
| [docs/risk-matrix.md](docs/risk-matrix.md) | Likelihood × severity matrix with full mitigation detail, inherent vs residual scores |
| [docs/cto-memo.md](docs/cto-memo.md) | Executive memo: 4 key findings, prioritized action items, deployment recommendation |

---

## Setup & Reproduction

### Prerequisites

```bash
python >= 3.11
docker (for Prometheus + Grafana stack)
```

### Install dependencies

```bash
# From repo root
pip install -r requirements.txt
```

### Run the monitoring service

```bash
# Start the instrumented FastAPI service
uvicorn src.monitoring.instrumentation:app --host 0.0.0.0 --port 8000

# In a second terminal — simulate traffic to populate metrics
python src/monitoring/traffic_simulator.py --requests 500 --concurrency 10
```

### Start Prometheus + Grafana (Docker)

```bash
# Uses config/prometheus.yml to scrape the local service
docker run -d --name prometheus \
  -p 9090:9090 \
  -v $(pwd)/config/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus:v2.45.0

docker run -d --name grafana \
  -p 3000:3000 \
  grafana/grafana:10.0.0
```

Then import `dashboards/grafana-export.json` into Grafana (Dashboards → Import).

### Run the A/B test simulation

```bash
python src/ab_test/simulation.py
# Or with custom parameters:
python src/ab_test/simulation.py --seed 99 --n-per-group 5000

# For JSON output (used by notebook):
python src/ab_test/simulation.py --json
```

### Run drift detection

```bash
python src/drift/drift_detection.py
# Outputs 4 PNG plots to visualizations/ and drift_summary.json
```

### Regenerate all diagrams

```bash
python src/drift/generate_diagrams.py
# Outputs lineage-diagram.png, system-boundary-diagram.png, dashboard-simulated.png
```

### Run Jupyter notebook (A/B analysis)

```bash
jupyter notebook notebooks/ab_analysis.ipynb
```

---

## Component Connections

The best submissions show how components tell a coherent story. Here's how the components connect in this project:

- **C1 → C4:** The Grafana dashboard's `retrieval_similarity_score` histogram is the real-time signal of the drift that C4 analyzes in detail. The PSI alert threshold (0.10) is the quantitative trigger for the dashboard alert rule.
- **C2 → C3:** The A/B test (C2) validates the top-k improvement. The model card (C3) documents current performance metrics and references the A/B test as the path to v1.2 configuration changes.
- **C3 → C5:** Model card limitations (hallucination on empty retrieval, KB staleness) map directly to R001 and R003 in the risk register and risk matrix.
- **C4 → C3:** The Week 6 drift detection (C4) triggered KB re-ingestion logged as EVT-005 in the audit trail (C3). This closes the loop between monitoring and governance.
- **C5 → C1:** Every HIGH/CRITICAL risk in the risk matrix (C5) has a corresponding observable Prometheus metric and dashboard alert threshold (C1).

---

## Lessons Learned

**Milestone 1–2 (Serving & Containerization):** The FastAPI + Docker pattern from M1 made C1 instrumentation straightforward. Adding Prometheus counters and histograms to an existing FastAPI service is a 30-minute task once you understand the metric type semantics (Counter vs Histogram vs Gauge).

**Milestone 3 (MLflow + Airflow):** MLflow's experiment tracking pattern — tagging every run with data hash, model hash, git commit — directly inspired the audit trail design in C3. An audit trail is just experiment tracking applied to production events rather than training runs.

**Milestone 4 (Data Generation):** The `generate_data.py` synthetic data pattern from M4 was the foundation for the drift simulation in C4. Generating realistic reference and drifted distributions requires the same thinking as generating synthetic training data — you need to model the underlying data-generating process, not just add noise.

**Milestone 5 (LLM Inference):** The caching and batching work from M5 directly informs C1 (cache hit ratio metric) and C2 (cost-per-query guardrail). The benchmark framework from M5 also established the P50/P95/P99 latency analysis pattern used throughout this project.

**Milestone 6 (RAG Pipeline):** The FAISS retrieval quality metrics from M6 (P@5, R@5, MRR) became the foundation for C4 drift detection (retrieval similarity score as the primary drift signal) and the model card performance section in C3.

**Key insight:** Production MLOps is mostly about connecting signals. The same retrieval similarity score appears in: the Grafana dashboard (C1), as the drift detection target (C4), as the A/B test secondary metric (C2), as a KB staleness proxy in the model card (C3), and as the trigger for risk register items R001 and R007 (C3/C5). Building each component in isolation would miss this.

---

## Repository Structure

```
ids568-final-project-dpand/
├── src/
│   ├── monitoring/        # C1: FastAPI + Prometheus instrumentation
│   ├── ab_test/           # C2: A/B test simulation and statistical analysis
│   └── drift/             # C4: PSI drift detection + diagram generation
├── docs/                  # All markdown documentation + diagrams
├── dashboards/            # Grafana JSON export
├── config/                # Prometheus configuration
├── logs/                  # Structured audit trail
├── visualizations/        # Drift plots, heatmaps, A/B results
├── screenshots/           # Dashboard screenshot
├── notebooks/             # Jupyter analysis notebook
├── requirements.txt
└── README.md
```
