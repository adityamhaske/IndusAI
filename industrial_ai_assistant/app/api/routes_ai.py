"""
API routes for AI Gateway health and provider validation.
Mounted at /api/ai by main.py.
"""
from __future__ import annotations

import logging
import os
import time

import httpx
from fastapi import APIRouter, Depends, Query as FQuery
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.firebase_auth import AuthenticatedUser, get_current_user
from app.config.dependency_injection import get_container

logger = logging.getLogger(__name__)
router = APIRouter()

_VALIDATE_TIMEOUT = 5.0  # seconds


# ── GET /api/ai/health ─────────────────────────────────────────────────────────

@router.get("/health", tags=["AI"])
def get_ai_gateway_health(
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Returns gateway health status."""
    gateway = get_container().ai_gateway
    return gateway.get_health()


# ── POST /api/ai/test-connection ───────────────────────────────────────────────

class TestConnectionRequest(BaseModel):
    provider: str = "gemini"

@router.post("/test-connection", tags=["AI"])
def test_ai_connection(
    body: TestConnectionRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Live 1-token generation test against a specific provider."""
    from app.models.ai_models import AIRequest
    gateway = get_container().ai_gateway

    provider_id = body.provider
    provider = gateway.providers.get(provider_id)
    if not provider:
        return JSONResponse(content={
            "status": "failed",
            "provider": provider_id,
            "latency_ms": 0,
            "model": None,
            "error": f"Provider '{provider_id}' not in registry. Active: {list(gateway.providers.keys())}",
        })

    t0 = time.perf_counter()
    try:
        req = AIRequest(prompt="Reply with exactly: OK", max_tokens=5, response_format="text")
        res = provider.generate(req)
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)

        if res.success:
            return JSONResponse(content={
                "status": "connected",
                "provider": provider_id,
                "latency_ms": latency_ms,
                "model": res.model_name,
                "error": None,
            })
        else:
            return JSONResponse(content={
                "status": "failed",
                "provider": provider_id,
                "latency_ms": latency_ms,
                "model": res.model_name,
                "error": res.error,
            })
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        logger.exception("test-connection failed for '%s'", provider_id)
        return JSONResponse(content={
            "status": "failed",
            "provider": provider_id,
            "latency_ms": latency_ms,
            "model": None,
            "error": str(exc),
        })


# ── GET /api/ai/providers ─────────────────────────────────────────────────────

@router.get("/providers", tags=["AI"])
def get_providers(
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Returns current provider registry state."""
    gateway = get_container().ai_gateway
    providers_info = {}
    for key, prov in gateway.providers.items():
        providers_info[key] = {
            "provider_name": getattr(prov, "provider_name", key),
            "provider_type": getattr(prov, "provider_type", "unknown"),
            "model": getattr(prov, "model", "unknown"),
            "has_api_key": bool(getattr(prov, "api_key", None)),
        }
    return {
        "primary": gateway.policy.primary,
        "secondary": gateway.policy.secondary,
        "registered_providers": providers_info,
    }


# ── POST /api/ai/validate-provider ─────────────────────────────────────────────

class ProviderValidationRequest(BaseModel):
    provider: str  # "openai" | "gemini" | "deepseek"
    api_key: str | None = None

@router.post("/validate-provider", tags=["AI"])
async def validate_provider(
    body: ProviderValidationRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
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
        else:
            return JSONResponse(status_code=400, content={
                "success": False,
                "error": "UNKNOWN_PROVIDER",
                "details": f"Provider '{provider}' not recognized. Use: openai, gemini",
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
    if not api_key or api_key == "********":
        return {"success": False, "latency_ms": 0.0, "model": None,
                "error": "API_KEY_MISSING", "details": "OpenAI API key is not set."}
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
    if not api_key or api_key == "********":
        return {"success": False, "latency_ms": 0.0, "model": None,
                "error": "API_KEY_MISSING", "details": "Gemini API key is not set."}
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


# ── GET /api/ai/rag-health ─────────────────────────────────────────────────────

@router.get("/rag-health", tags=["AI"])
def get_rag_health(
    project_id: str = FQuery(default="default"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Returns RAG pipeline health for a project."""
    from app.indexes.semantic_index import get_semantic_index

    sem = get_semantic_index()

    collection_exists = False
    try:
        client = sem._get_client()
        collections = [c.name for c in client.get_collections().collections]
        collection_exists = "project_knowledge" in collections
    except Exception:
        pass

    chunk_count = sem.collection_size(project_id)

    return {
        "project_id": project_id,
        "collection_exists": collection_exists,
        "chunk_count": chunk_count,
        "embedding_model": "gemini",
        "index_state": "READY" if chunk_count > 0 else "UNLOADED",
    }
