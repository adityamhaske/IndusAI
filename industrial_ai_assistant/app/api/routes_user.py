"""
User Settings API — BYOK provider configuration.
Mounted at /api/user by main.py

Endpoints:
    GET  /api/user/settings         → masked provider config
    POST /api/user/settings         → save provider config + encrypted keys
    POST /api/user/test-connection  → test LLM connectivity with user's key
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.auth.firebase_auth import AuthenticatedUser, get_current_user
from app.services.user_settings_service import UserSettingsService
from app.models.ai_models import AIRequest

logger = logging.getLogger(__name__)
router = APIRouter()


class SaveSettingsRequest(BaseModel):
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_api_key: Optional[str] = None
    ollama_url: Optional[str] = None


# ── GET /settings ──────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(user: AuthenticatedUser = Depends(get_current_user)):
    """Return user's provider settings with masked API keys."""
    svc = UserSettingsService()
    return svc.get_settings(user.uid)


# ── POST /settings ─────────────────────────────────────────────────────────

@router.post("/settings")
async def save_settings(
    body: SaveSettingsRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Save provider settings. API keys are encrypted at rest."""
    svc = UserSettingsService()
    try:
        return svc.save_settings(
            uid=user.uid,
            llm_provider=body.llm_provider,
            llm_model=body.llm_model,
            llm_api_key=body.llm_api_key,
            embedding_provider=body.embedding_provider,
            embedding_api_key=body.embedding_api_key,
            ollama_url=body.ollama_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── POST /test-connection ─────────────────────────────────────────────────

@router.post("/test-connection")
async def test_connection(user: AuthenticatedUser = Depends(get_current_user)):
    """Test LLM connectivity using the user's saved BYOK key."""
    try:
        from app.llm.provider_factory import get_llm_for_user
        provider = get_llm_for_user(user.uid)

        request = AIRequest(
            prompt="Reply with exactly: OK",
            response_format="text",
            max_tokens=10,
            temperature=0.0,
        )
        response = provider.generate(request)

        if response.success:
            return {
                "status": "connected",
                "provider": response.provider_name,
                "model": response.model_name,
                "latency_ms": response.latency_ms,
            }
        else:
            return {
                "status": "error",
                "provider": response.provider_name,
                "error": response.error,
            }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Test connection failed")
        raise HTTPException(status_code=500, detail=f"Connection test failed: {e}")
