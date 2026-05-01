from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import numpy as np


# Helper: draw a rounded-rect box

def draw_box(ax, x, y, w, h, text, color="#4C72B0", text_color="white",
             fontsize=9, style="round,pad=0.1"):
    rect = mpatches.FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle=style, linewidth=1.2,
        edgecolor="white", facecolor=color, zorder=3,
    )
    ax.add_patch(rect)
    ax.text(x, y, text, ha="center", va="center",
            fontsize=fontsize, color=text_color, fontweight="bold", zorder=4,
            wrap=True)


def draw_arrow(ax, x1, y1, x2, y2, label="", color="#555555"):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="-|>", color=color,
                        lw=1.5, connectionstyle="arc3,rad=0.0"),
        zorder=2,
    )
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx, my + 0.03, label, ha="center", va="bottom",
                fontsize=7.5, color="#333333",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))


# 1. Data lineage diagram  (Component 3)

def generate_lineage_diagram(output_path: Path):
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 5)
    ax.axis("off")
    fig.patch.set_facecolor("#F8F9FA")
    ax.set_facecolor("#F8F9FA")

    ax.text(7, 4.65, "RAG-LLM Query Assistant — Data & Model Lineage",
            ha="center", va="center", fontsize=13, fontweight="bold", color="#222")

    # Nodes  (x, y, label, color)
    nodes = [
        (1.3,  2.5, "MLOps\nDocument\nCorpus",       "#6C757D"),
        (3.4,  2.5, "Text\nChunking\n(512 tok, 64 ovlp)", "#17A2B8"),
        (5.5,  2.5, "Sentence\nEmbeddings\n(all-MiniLM-L6-v2)", "#17A2B8"),
        (7.7,  2.5, "FAISS\nVector Index\n(IndexFlatIP)", "#0D6EFD"),
        (9.8,  3.8, "LLM Inference\n(Ollama / local)", "#6610F2"),
        (9.8,  1.2, "Prometheus\nMetrics Store",       "#198754"),
        (12.2, 2.5, "RAG\nQuery\nResponse",            "#DC3545"),
    ]

    for x, y, label, color in nodes:
        draw_box(ax, x, y, 1.7, 1.1, label, color=color, fontsize=8)

    # Arrows
    edges = [
        (1.3, 2.5, 3.4, 2.5, "raw docs"),
        (3.4, 2.5, 5.5, 2.5, "chunks"),
        (5.5, 2.5, 7.7, 2.5, "vectors"),
        (7.7, 2.5, 9.8, 3.8, "top-k docs"),
        (7.7, 2.5, 9.8, 1.2, "latency / score"),
        (9.8, 3.8, 12.2, 2.5, "generated text"),
        (9.8, 1.2, 12.2, 2.5, "telemetry"),
    ]
    for x1, y1, x2, y2, lbl in edges:
        draw_arrow(ax, x1, y1, x2, y2, lbl)

    # Stage labels below
    stages = [
        (1.3, 1.7, "DATA"),
        (3.4, 1.7, "PROCESSING"),
        (5.5, 1.7, "EMBEDDING"),
        (7.7, 1.7, "INDEXING"),
        (9.8, 0.6, "INFERENCE /\nMONITORING"),
        (12.2, 1.7, "OUTPUT"),
    ]
    for x, y, lbl in stages:
        ax.text(x, y, lbl, ha="center", va="center",
                fontsize=7, color="#888", fontstyle="italic")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved lineage diagram: {output_path}")


# 2. System boundary diagram  (Component 5)

def generate_boundary_diagram(output_path: Path):
    fig, ax = plt.subplots(figsize=(15, 6))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 6)
    ax.axis("off")
    fig.patch.set_facecolor("#F8F9FA")
    ax.set_facecolor("#F8F9FA")

    ax.text(7.5, 5.65, "RAG-LLM Query Assistant — System Boundary & Risk Diagram",
            ha="center", va="center", fontsize=13, fontweight="bold", color="#222")

    # Trust boundary rectangle
    trust_box = mpatches.FancyBboxPatch(
        (2.8, 0.6), 9.2, 4.2,
        boxstyle="round,pad=0.1", linewidth=2,
        edgecolor="#FF7F0E", facecolor="none",
        linestyle="--", zorder=1,
    )
    ax.add_patch(trust_box)
    ax.text(3.1, 4.65, "Trust Boundary (Internal System)", fontsize=8,
            color="#FF7F0E", fontstyle="italic")

    # Nodes
    nodes = [
        (1.4,  3.0, "USER\nINPUT",      "#6C757D",  "white"),
        (4.0,  3.0, "INPUT\nVALIDATION","#17A2B8",  "white"),
        (6.6,  3.0, "RETRIEVER\n(FAISS)","#0D6EFD", "white"),
        (9.4,  3.0, "LLM API\n(Ollama)", "#6610F2", "white"),
        (11.8, 3.0, "RESPONSE\nFILTER", "#198754",  "white"),
        (13.8, 3.0, "USER\nOUTPUT",     "#DC3545",  "white"),
    ]
    for x, y, label, color, tc in nodes:
        draw_box(ax, x, y, 1.8, 1.0, label, color=color, text_color=tc, fontsize=8)

    # Main flow arrows
    flow_edges = [
        (1.4, 3.0, 4.0, 3.0),
        (4.0, 3.0, 6.6, 3.0),
        (6.6, 3.0, 9.4, 3.0),
        (9.4, 3.0, 11.8, 3.0),
        (11.8, 3.0, 13.8, 3.0),
    ]
    for x1, y1, x2, y2 in flow_edges:
        draw_arrow(ax, x1, y1, x2, y2)

    # Risk annotations
    risks = [
        (1.4,  1.8, "Risk: PII, prompt injection",  "#D62728"),
        (4.0,  1.8, "Risk: schema validation bypass","#FF7F0E"),
        (6.6,  1.8, "Risk: data exposure, KB staleness","#D62728"),
        (9.4,  1.8, "Risk: third-party leak,\nhallucination","#D62728"),
        (11.8, 1.8, "Risk: unsafe output\nreaches user","#FF7F0E"),
    ]
    for x, y, label, color in risks:
        ax.text(x, y, label, ha="center", va="center", fontsize=7,
                color=color, style="italic",
                bbox=dict(boxstyle="round,pad=0.2", fc="#FFF3E0", ec=color, alpha=0.8))
        ax.annotate("", xy=(x, 2.51), xytext=(x, y + 0.2),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=1.0))

    # Mitigations
    mitigations = [
        (1.4,  4.5, "Sanitize inputs\nblock PII patterns"),
        (4.0,  4.5, "Schema validation\nrate limiting"),
        (6.6,  4.5, "Access control\ndoc age alerting"),
        (9.4,  4.5, "Vendor DPA\ndata masking"),
        (11.8, 4.5, "Grounding checks\nescalation protocol"),
    ]
    for x, y, label in mitigations:
        ax.text(x, y, label, ha="center", va="center", fontsize=6.5,
                color="#155724",
                bbox=dict(boxstyle="round,pad=0.2", fc="#D4EDDA", ec="#155724", alpha=0.8))
        ax.annotate("", xy=(x, 3.52), xytext=(x, y - 0.2),
                    arrowprops=dict(arrowstyle="-|>", color="#155724", lw=1.0))

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved boundary diagram: {output_path}")


# 3. Dashboard screenshot  (Component 1)

def generate_dashboard_screenshot(output_path: Path):
    """Generate a matplotlib mock-up of the Grafana dashboard with simulated data."""
    rng = np.random.default_rng(42)
    minutes = 60
    t = np.linspace(0, minutes, minutes * 4)

    # Simulated metric time series
    request_rate = 8 + rng.normal(0, 0.5, len(t)) + np.sin(t / 10) * 2
    error_rate = np.clip(0.012 + rng.normal(0, 0.003, len(t)), 0, 0.08)
    p50 = np.clip(rng.normal(0.55, 0.08, len(t)), 0.2, 2.0)
    p99 = np.clip(rng.normal(1.80, 0.25, len(t)), 0.5, 4.0)
    ttft_p95 = np.clip(rng.normal(1.45, 0.20, len(t)), 0.5, 3.5)
    cache_hit_ratio = np.clip(0.38 + rng.normal(0, 0.04, len(t)), 0, 1)
    token_throughput = np.clip(180 + rng.normal(0, 15, len(t)), 80, 300)

    fig = plt.figure(figsize=(16, 10))
    fig.patch.set_facecolor("#1F1F1F")

    # Title
    fig.text(0.5, 0.97, "RAG-LLM Query Assistant — Production Dashboard (Simulated Traffic)",
             ha="center", va="top", fontsize=13, fontweight="bold", color="white")
    fig.text(0.5, 0.945, "Datasource: Prometheus  |  Refresh: 10s  |  Last 1h",
             ha="center", va="top", fontsize=8.5, color="#AAAAAA")

    # Stat panels row
    stat_ax_positions = [
        [0.04, 0.82, 0.12, 0.10],
        [0.18, 0.82, 0.12, 0.10],
        [0.32, 0.82, 0.12, 0.10],
        [0.46, 0.82, 0.12, 0.10],
        [0.60, 0.82, 0.12, 0.10],
        [0.74, 0.82, 0.12, 0.10],
    ]
    stat_data = [
        ("Error Rate (5m)", f"{error_rate[-1]*100:.2f}%", "#F28B82" if error_rate[-1] > 0.03 else "#81C995"),
        ("P99 Latency",     f"{p99[-1]:.2f}s",            "#F28B82" if p99[-1] > 3.0 else "#81C995"),
        ("Request Rate",    f"{request_rate[-1]:.1f} req/s","#8AB4F8"),
        ("Cache Hit Ratio", f"{cache_hit_ratio[-1]*100:.1f}%","#81C995"),
        ("Empty Retr. %",   "3.8%",                       "#FFD666"),
        ("Active Requests", "7",                           "#8AB4F8"),
    ]
    for pos, (label, value, color) in zip(stat_ax_positions, stat_data):
        ax = fig.add_axes(pos)
        ax.set_facecolor("#2D2D2D")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.axis("off")
        ax.text(0.5, 0.75, label, ha="center", va="center", fontsize=8,
                color="#BBBBBB", transform=ax.transAxes)
        ax.text(0.5, 0.35, value, ha="center", va="center", fontsize=16,
                color=color, fontweight="bold", transform=ax.transAxes)

    plot_color = "#1F1F1F"
    line_colors = ["#8AB4F8", "#F28B82", "#81C995", "#FFD666"]

    def styled_ax(pos):
        ax = fig.add_axes(pos)
        ax.set_facecolor("#2D2D2D")
        for spine in ax.spines.values():
            spine.set_edgecolor("#444")
        ax.tick_params(colors="#AAAAAA", labelsize=7)
        ax.xaxis.label.set_color("#AAAAAA")
        ax.yaxis.label.set_color("#AAAAAA")
        return ax

    # Latency percentiles
    ax1 = styled_ax([0.04, 0.50, 0.44, 0.28])
    ax1.plot(t, p50, color=line_colors[0], linewidth=1.2, label="P50")
    ax1.plot(t, p99, color=line_colors[1], linewidth=1.2, label="P99")
    ax1.axhline(3.0, color="#FF7F0E", linestyle="--", linewidth=0.8, label="SLA 3.0s")
    ax1.set_title("Request Latency Percentiles (s)", color="white", fontsize=9)
    ax1.legend(fontsize=7, facecolor="#333", labelcolor="white")
    ax1.grid(True, alpha=0.15)

    # TTFT
    ax2 = styled_ax([0.52, 0.50, 0.44, 0.28])
    ax2.plot(t, ttft_p95, color=line_colors[2], linewidth=1.2, label="TTFT P95")
    ax2.set_title("Time to First Token P95 (s)", color="white", fontsize=9)
    ax2.legend(fontsize=7, facecolor="#333", labelcolor="white")
    ax2.grid(True, alpha=0.15)

    # Token throughput
    ax3 = styled_ax([0.04, 0.16, 0.44, 0.28])
    ax3.plot(t, token_throughput, color=line_colors[3], linewidth=1.2, label="Tokens/s")
    ax3.set_title("Token Throughput (completion tokens/s)", color="white", fontsize=9)
    ax3.legend(fontsize=7, facecolor="#333", labelcolor="white")
    ax3.grid(True, alpha=0.15)

    # Cache hit ratio
    ax4 = styled_ax([0.52, 0.16, 0.44, 0.28])
    ax4.plot(t, cache_hit_ratio * 100, color=line_colors[0], linewidth=1.2,
             label="Cache Hit %")
    ax4.axhline(40, color="#FF7F0E", linestyle="--", linewidth=0.8, label="Target 40%")
    ax4.set_ylim(0, 80)
    ax4.set_title("Cache Hit Ratio (%)", color="white", fontsize=9)
    ax4.legend(fontsize=7, facecolor="#333", labelcolor="white")
    ax4.grid(True, alpha=0.15)

    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  Saved dashboard screenshot: {output_path}")


# Main

if __name__ == "__main__":
    docs_dir = Path("docs")
    screenshots_dir = Path("screenshots")
    docs_dir.mkdir(exist_ok=True)
    screenshots_dir.mkdir(exist_ok=True)

    print("\nGenerating diagrams...")
    generate_lineage_diagram(docs_dir / "lineage-diagram.png")
    generate_boundary_diagram(docs_dir / "system-boundary-diagram.png")
    generate_dashboard_screenshot(screenshots_dir / "dashboard-simulated.png")
    print("\nAll diagrams generated.\n")
