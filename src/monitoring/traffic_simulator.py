import argparse
import asyncio
import time
import random
import httpx

SAMPLE_QUERIES = [
    "What is MLOps and why does it matter for production AI systems?",
    "How do I configure Airflow for a machine learning pipeline?",
    "Explain the difference between feature drift and concept drift.",
    "What metrics should I monitor for an LLM inference API?",
    "How does RAG improve response grounding?",
    "What is Population Stability Index and how is it interpreted?",
    "How do I calculate sample size for an A/B test?",
    "What is the purpose of a model card in AI governance?",
    "Describe NIST AI Risk Management Framework core functions.",
    "How does vector search work in a FAISS index?",
    "What causes retrieval quality degradation over time?",
    "Explain Prometheus histogram buckets for latency measurement.",
    "What is the difference between p50 and p99 latency?",
    "How should I structure an audit trail for model deployments?",
    "What are guardrail metrics in an A/B experiment?",
]


async def send_request(client: httpx.AsyncClient, base_url: str, query: str, top_k: int) -> dict:
    """Send one query to the inference API and return timing info."""
    start = time.perf_counter()
    try:
        resp = await client.post(
            f"{base_url}/query",
            json={"query": query, "top_k": top_k, "use_cache": True},
            timeout=30.0,
        )
        elapsed = time.perf_counter() - start
        status = "success" if resp.status_code == 200 else "error"
        return {"status": status, "latency_s": elapsed, "http_code": resp.status_code}
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return {"status": "error", "latency_s": elapsed, "error": str(exc)}


async def run_simulation(base_url: str, total_requests: int, concurrency: int):
    """
    Send `total_requests` to the service with up to `concurrency` in-flight at once.
    Simulates realistic traffic with a mix of top_k=3 (80%) and top_k=5 (20%)
    to represent the A/B test treatment group in practice.
    """
    results = []
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_request(client, query, top_k):
        async with semaphore:
            result = await send_request(client, base_url, query, top_k)
            results.append(result)

    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(total_requests):
            query = random.choice(SAMPLE_QUERIES)
            # 80% control (top_k=3), 20% treatment (top_k=5) — mirrors A/B split
            top_k = 3 if random.random() < 0.80 else 5
            tasks.append(asyncio.create_task(bounded_request(client, query, top_k)))
            # Small jitter between task creation to simulate natural arrival rate
            if i % 10 == 0 and i > 0:
                await asyncio.sleep(0.05)

        start_all = time.perf_counter()
        await asyncio.gather(*tasks)
        elapsed_all = time.perf_counter() - start_all

    # Summary statistics
    latencies = [r["latency_s"] for r in results]
    successes = sum(1 for r in results if r["status"] == "success")
    errors = len(results) - successes
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[int(len(latencies_sorted) * 0.50)]
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
    p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]

    print("\n" + "=" * 55)
    print("  Traffic Simulation Complete")
    print("=" * 55)
    print(f"  Total requests : {len(results)}")
    print(f"  Successes      : {successes}")
    print(f"  Errors         : {errors}")
    print(f"  Error rate     : {errors / len(results) * 100:.1f}%")
    print(f"  Wall time      : {elapsed_all:.2f}s")
    print(f"  Throughput     : {len(results) / elapsed_all:.1f} req/s")
    print(f"  Latency p50    : {p50 * 1000:.0f} ms")
    print(f"  Latency p95    : {p95 * 1000:.0f} ms")
    print(f"  Latency p99    : {p99 * 1000:.0f} ms")
    print("=" * 55)
    print("\nMetrics are now populated at http://localhost:8000/metrics")
    print("Open Grafana at http://localhost:3000 to view the dashboard.\n")


def main():
    parser = argparse.ArgumentParser(description="Simulate traffic against the RAG-LLM API.")
    parser.add_argument("--requests", type=int, default=500,
                        help="Total number of requests to send (default: 500)")
    parser.add_argument("--concurrency", type=int, default=10,
                        help="Max concurrent requests (default: 10)")
    parser.add_argument("--url", type=str, default="http://localhost:8000",
                        help="Base URL of the inference service (default: http://localhost:8000)")
    args = parser.parse_args()

    print(f"\nStarting traffic simulation: {args.requests} requests, "
          f"concurrency={args.concurrency}, target={args.url}\n")
    asyncio.run(run_simulation(args.url, args.requests, args.concurrency))


if __name__ == "__main__":
    main()
