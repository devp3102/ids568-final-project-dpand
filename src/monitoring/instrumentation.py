
import time
import random
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    make_asgi_app,
    REGISTRY,
)

# Metric definitions

REQUEST_COUNT = Counter(
    "rag_requests_total",
    "Total RAG inference requests",
    ["status"],  # success | error
)

REQUEST_LATENCY = Histogram(
    "rag_request_latency_seconds",
    "End-to-end request latency",
    ["endpoint"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0],
)

LLM_TTFT = Histogram(
    "llm_time_to_first_token_seconds",
    "Time from request receipt to first token (proxy: total generation latency for non-streaming)",
    ["model_version"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

LLM_TOKENS = Counter(
    "llm_tokens_total",
    "Total tokens processed",
    ["direction"],  # prompt | completion
)

LLM_CACHE_HITS = Counter(
    "llm_cache_hits_total",
    "Cache hit / miss counts",
    ["result"],  # hit | miss
)

RAG_RETRIEVAL_LATENCY = Histogram(
    "rag_retrieval_latency_seconds",
    "Vector search latency",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
)

RAG_RETRIEVAL_RESULT_COUNT = Histogram(
    "rag_retrieval_result_count",
    "Number of documents returned per query",
    buckets=[0, 1, 2, 3, 5, 10],
)

RAG_RETRIEVAL_SCORE = Histogram(
    "rag_retrieval_similarity_score",
    "Cosine similarity score of top-1 retrieved document",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

ERROR_RATE = Gauge(
    "rag_error_rate_5m",
    "Rolling 5-minute error rate (computed externally for alerting reference)",
)

ACTIVE_REQUESTS = Gauge(
    "rag_active_requests",
    "Currently in-flight requests",
)

MODEL_VERSION = Gauge(
    "rag_model_version_info",
    "Currently deployed model version (label only)",
    ["version", "retriever"],
)

# Record which model is deployed
MODEL_VERSION.labels(version="v1.0.0", retriever="faiss-sentence-transformers").set(1)


# Request / Response schemas

class QueryRequest(BaseModel):
    query: str
    top_k: int = 3
    use_cache: bool = True


class QueryResponse(BaseModel):
    answer: str
    retrieved_docs: int
    retrieval_score: float
    generation_latency_s: float
    cache_hit: bool
    prompt_tokens: int
    completion_tokens: int



# Simulated RAG inference (stands in for the real M6 pipeline)


async def _simulate_retrieval(query: str, top_k: int) -> tuple[int, float, float]:
    """Returns (num_docs, top_score, latency_s)."""
    await asyncio.sleep(random.uniform(0.01, 0.08))
    latency = random.uniform(0.01, 0.08)
    num_docs = random.choices([0, top_k - 1, top_k], weights=[0.05, 0.15, 0.80])[0]
    # Retrieval scores drawn from a realistic distribution
    score = max(0.0, min(1.0, random.gauss(0.72, 0.12))) if num_docs > 0 else 0.0
    return num_docs, score, latency


async def _simulate_generation(
    query: str, num_docs: int, use_cache: bool
) -> tuple[str, float, bool, int, int]:
    """Returns (answer, ttft_s, cache_hit, prompt_tokens, completion_tokens)."""
    # Cache hit probability: ~40% when use_cache is True
    cache_hit = use_cache and random.random() < 0.40
    if cache_hit:
        await asyncio.sleep(random.uniform(0.005, 0.02))
        ttft = random.uniform(0.005, 0.02)
        prompt_tokens = random.randint(80, 200)
        completion_tokens = 0  # served from cache
    else:
        # Generation latency scales with context size
        base = 0.8 + num_docs * 0.15
        ttft = max(0.1, random.gauss(base, 0.2))
        await asyncio.sleep(ttft)
        prompt_tokens = random.randint(150, 400)
        completion_tokens = random.randint(50, 300)

    answer = f"Simulated answer for: {query[:40]}..."
    return answer, ttft, cache_hit, prompt_tokens, completion_tokens



# FastAPI application


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("RAG-LLM Monitoring Service started. Metrics at /metrics")
    yield
    print("Service shutting down.")


app = FastAPI(
    title="RAG-LLM Query Assistant — Monitored Service",
    description="Production inference API with Prometheus metrics instrumentation.",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount the Prometheus ASGI exporter at /metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.middleware("http")
async def track_active_requests(request: Request, call_next):
    ACTIVE_REQUESTS.inc()
    try:
        response = await call_next(request)
        return response
    finally:
        ACTIVE_REQUESTS.dec()


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    """Main inference endpoint: retrieval + generation with full metric emission."""
    start = time.perf_counter()

    try:
        # --- Retrieval ---
        retr_start = time.perf_counter()
        num_docs, top_score, retr_lat = await _simulate_retrieval(req.query, req.top_k)
        retr_elapsed = time.perf_counter() - retr_start

        RAG_RETRIEVAL_LATENCY.observe(retr_elapsed)
        RAG_RETRIEVAL_RESULT_COUNT.observe(num_docs)
        if num_docs > 0:
            RAG_RETRIEVAL_SCORE.observe(top_score)

        # --- Generation ---
        answer, ttft, cache_hit, prompt_tok, comp_tok = await _simulate_generation(
            req.query, num_docs, req.use_cache
        )

        LLM_TTFT.labels(model_version="v1.0.0").observe(ttft)
        LLM_TOKENS.labels(direction="prompt").inc(prompt_tok)
        LLM_TOKENS.labels(direction="completion").inc(comp_tok)
        LLM_CACHE_HITS.labels(result="hit" if cache_hit else "miss").inc()

        total_elapsed = time.perf_counter() - start
        REQUEST_LATENCY.labels(endpoint="/query").observe(total_elapsed)
        REQUEST_COUNT.labels(status="success").inc()

        return QueryResponse(
            answer=answer,
            retrieved_docs=num_docs,
            retrieval_score=round(top_score, 4),
            generation_latency_s=round(ttft, 4),
            cache_hit=cache_hit,
            prompt_tokens=prompt_tok,
            completion_tokens=comp_tok,
        )

    except Exception as exc:
        REQUEST_COUNT.labels(status="error").inc()
        REQUEST_LATENCY.labels(endpoint="/query").observe(time.perf_counter() - start)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
async def health():
    return {"status": "ok", "model_version": "v1.0.0"}


@app.get("/")
async def root():
    return {
        "service": "RAG-LLM Query Assistant",
        "docs": "/docs",
        "metrics": "/metrics",
        "health": "/health",
    }
