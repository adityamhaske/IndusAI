"""
API routes for AI Gateway metrics, observability, provider validation, and RAG health.
Mounted at /api/ai by main.py.
"""
from __future__ import annotations

import logging
import os
import time

import httpx
from fastapi import APIRouter, Query as FQuery, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config.dependency_injection import get_container

logger = logging.getLogger(__name__)
router = APIRouter()

_VALIDATE_TIMEOUT = 5.0  # seconds


# ── GET /api/ai/health ─────────────────────────────────────────────────────────

@router.get("/health", tags=["AI"])
def get_ai_gateway_health():
    """Returns full diagnostic telemetry and circuit breaker status."""
    gateway = get_container().ai_gateway
    return gateway.get_health()


# ── GET /api/ai/metrics ────────────────────────────────────────────────────────

@router.get("/metrics", tags=["AI"])
def get_ai_gateway_metrics():
    """Returns high-level SLA Observability Metrics in Prometheus plain text format."""
    gateway = get_container().ai_gateway
    m = gateway.get_metrics()

    lines = [
        "# HELP ai_gateway_status Global system status (0=NORMAL, higher=DEGRADED)",
        "# TYPE ai_gateway_status gauge",
        f"ai_gateway_status {1 if m.get('status') != 'NORMAL' else 0}",
        "# HELP ai_gateway_local_p50_latency_ms P50 latency of successful local AI requests",
        "# TYPE ai_gateway_local_p50_latency_ms gauge",
        f"ai_gateway_local_p50_latency_ms {m.get('local_p50_latency_ms', 0)}",
        "# HELP ai_gateway_local_p95_latency_ms P95 latency of successful local AI requests",
        "# TYPE ai_gateway_local_p95_latency_ms gauge",
        f"ai_gateway_local_p95_latency_ms {m.get('local_p95_latency_ms', 0)}",
        "# HELP ai_gateway_cloud_p50_latency_ms P50 latency of successful cloud AI requests",
        "# TYPE ai_gateway_cloud_p50_latency_ms gauge",
        f"ai_gateway_cloud_p50_latency_ms {m.get('cloud_p50_latency_ms', 0)}",
        "# HELP ai_gateway_cloud_p95_latency_ms P95 latency of successful cloud AI requests",
        "# TYPE ai_gateway_cloud_p95_latency_ms gauge",
        f"ai_gateway_cloud_p95_latency_ms {m.get('cloud_p95_latency_ms', 0)}",
        "# HELP ai_gateway_failure_rate_last_60s Sliding window failure rate",
        "# TYPE ai_gateway_failure_rate_last_60s gauge",
        f"ai_gateway_failure_rate_last_60s {m.get('failure_rate_last_60s', 0)}",
        "# HELP ai_gateway_fallback_ratio Ratio of cloud fallbacks triggered",
        "# TYPE ai_gateway_fallback_ratio gauge",
        f"ai_gateway_fallback_ratio {m.get('fallback_ratio', 0)}",
        "# HELP ai_gateway_schema_failure_rate Rate of JSON Pydantic parsing failures",
        "# TYPE ai_gateway_schema_failure_rate gauge",
        f"ai_gateway_schema_failure_rate {m.get('schema_failure_rate', 0)}",
        "# HELP ai_gateway_cumulative_daily_cost_usd Tracked daily usage spend",
        "# TYPE ai_gateway_cumulative_daily_cost_usd counter",
        f"ai_gateway_cumulative_daily_cost_usd {m.get('cumulative_daily_cost_usd', 0)}",
        "# HELP ai_gateway_traces_recorded Total requests tracked in cache",
        "# TYPE ai_gateway_traces_recorded gauge",
        f"ai_gateway_traces_recorded {m.get('traces_recorded', 0)}",
    ]
    return Response(content="\n".join(lines) + "\n", media_type="text/plain")


# ── POST /api/ai/validate-provider ─────────────────────────────────────────────

class ProviderValidationRequest(BaseModel):
    provider: str  # "openai" | "gemini" | "local_ollama"
    api_key: str | None = None  # Optional: validate this key directly instead of env


@router.post("/validate-provider", tags=["AI"])
async def validate_provider(body: ProviderValidationRequest):
    """
    Live lightweight probe against the specified AI provider (5s timeout).
    Returns: {success, latency_ms, model, error, details}
    """
    provider = body.provider.lower().strip()
    t0 = time.perf_counter()

    try:
        if provider == "openai":
            result = await _validate_openai(t0, body.api_key)
        elif provider == "gemini":
            result = await _validate_gemini(t0, body.api_key)
        elif provider in ("local_ollama", "local", "ollama"):
            result = await _validate_ollama(t0)
        else:
            return JSONResponse(status_code=400, content={
                "success": False,
                "error": "UNKNOWN_PROVIDER",
                "details": f"Provider '{provider}' not recognized. Use: openai, gemini, local_ollama",
            })
        return JSONResponse(content=result)
    except Exception as exc:
        logger.exception("Unexpected error during provider validation for '%s'", provider)
        return JSONResponse(content={
            "success": False,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "error": "VALIDATION_INTERNAL_ERROR",
            "details": str(exc),
        })


async def _validate_openai(t0: float, inline_key: str | None = None) -> dict:
    api_key = inline_key or os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key == '********':
        return {"success": False, "latency_ms": 0.0, "model": None,
                "error": "API_KEY_MISSING", "details": "OPENAI_API_KEY is not set."}
    try:
        async with httpx.AsyncClient(timeout=_VALIDATE_TIMEOUT) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        if resp.status_code == 200:
            models = [m["id"] for m in resp.json().get("data", [])]
            detected = next((m for m in models if "gpt" in m.lower()), models[0] if models else "unknown")
            return {"success": True, "latency_ms": latency_ms, "model": detected, "error": None, "details": None}
        if resp.status_code in (401, 403):
            return {"success": False, "latency_ms": latency_ms, "model": None,
                    "error": "INVALID_API_KEY", "details": "OpenAI rejected the API key (401/403)."}
        return {"success": False, "latency_ms": latency_ms, "model": None,
                "error": f"HTTP_{resp.status_code}", "details": resp.text[:200]}
    except httpx.TimeoutException:
        return {"success": False, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "model": None, "error": "TIMEOUT", "details": "OpenAI did not respond within 5s."}
    except Exception as exc:
        return {"success": False, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "model": None, "error": "CONNECTION_ERROR", "details": str(exc)}


async def _validate_gemini(t0: float, inline_key: str | None = None) -> dict:
    api_key = inline_key or os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == '********':
        return {"success": False, "latency_ms": 0.0, "model": None,
                "error": "API_KEY_MISSING", "details": "GEMINI_API_KEY is not set."}
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        async with httpx.AsyncClient(timeout=_VALIDATE_TIMEOUT) as client:
            resp = await client.get(url)
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        if resp.status_code == 200:
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            detected = next((m for m in models if "gemini" in m.lower()), models[0] if models else "unknown")
            return {"success": True, "latency_ms": latency_ms, "model": detected, "error": None, "details": None}
        if resp.status_code in (400, 401, 403):
            return {"success": False, "latency_ms": latency_ms, "model": None,
                    "error": "INVALID_API_KEY", "details": "Gemini rejected the API key."}
        return {"success": False, "latency_ms": latency_ms, "model": None,
                "error": f"HTTP_{resp.status_code}", "details": resp.text[:200]}
    except httpx.TimeoutException:
        return {"success": False, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "model": None, "error": "TIMEOUT", "details": "Gemini did not respond within 5s."}
    except Exception as exc:
        return {"success": False, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "model": None, "error": "CONNECTION_ERROR", "details": str(exc)}


async def _validate_ollama(t0: float) -> dict:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        async with httpx.AsyncClient(timeout=_VALIDATE_TIMEOUT) as client:
            resp = await client.get(f"{base_url}/api/tags")
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        if resp.status_code == 200:
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            detected = models[0] if models else "unknown (no models pulled)"
            return {"success": True, "latency_ms": latency_ms, "model": detected, "error": None, "details": None}
        return {"success": False, "latency_ms": latency_ms, "model": None,
                "error": f"HTTP_{resp.status_code}", "details": resp.text[:200]}
    except httpx.ConnectError:
        return {"success": False, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "model": None, "error": "OLLAMA_OFFLINE",
                "details": f"Cannot reach Ollama at {base_url}. Ensure the service is running."}
    except httpx.TimeoutException:
        return {"success": False, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "model": None, "error": "TIMEOUT", "details": "Ollama did not respond within 5s."}
    except Exception as exc:
        return {"success": False, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "model": None, "error": "CONNECTION_ERROR", "details": str(exc)}


# ── GET /api/ai/rag-health ─────────────────────────────────────────────────────

@router.get("/rag-health", tags=["AI"])
def get_rag_health(project_id: str = FQuery(default="default")):
    """
    Returns the runtime health state of the RAG pipeline.
    Reported fields: collection_exists, chunk_count, embedding_model,
                     vector_dimension, index_state, delta_detected.
    """
    from app.indexes.semantic_index import get_semantic_index
    from app.services.project_context_manager import get_project_context_manager
    from app.config.settings import settings

    sem = get_semantic_index()
    ctx = get_project_context_manager()
    status = ctx.get_status(project_id)

    collection_exists = False
    try:
        client = sem._get_client()
        collections = [c.name for c in client.get_collections().collections]
        collection_exists = "project_knowledge" in collections
    except Exception:
        pass

    chunk_count = sem.collection_size(project_id)
    index_state = status.index_state.value if status else "UNLOADED"
    delta_detected = index_state == "STALE"

    return {
        "project_id": project_id,
        "collection_exists": collection_exists,
        "chunk_count": chunk_count,
        "embedding_model": getattr(settings, "EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2"),
        "vector_dimension": 384,
        "index_state": index_state,
        "delta_detected": delta_detected,
    }
