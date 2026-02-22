"""
System health API routes.
Mounted at /api/system/health by main.py.
"""
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.services.system_health_service import get_health_service
from app.config.version import get_system_versions
from app.config.dependency_injection import get_container

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", tags=["System"])
def system_health():
    """
    Probe LLM, RAG, and vector store connectivity.
    Returns status='healthy' when all subsystems are reachable,
    status='degraded' when any component is unavailable.
    """
    svc = get_health_service()
    result = svc.full_status()
    logger.info(
        "Health probe: status=%s llm=%s rag=%s vs=%s",
        result["status"], result["llm_connected"],
        result["rag_connected"], result["vector_store_connected"]
    )
    return result

@router.get("/version", tags=["System"])
def system_version():
    """
    Expose immutable release version mappings for CI/CD tracking.
    """
    return get_system_versions()

class AIConfigPayload(BaseModel):
    primary_provider: str
    secondary_provider: Optional[str] = None
    timeout_ms: int = 8000
    max_tokens: int = 2000
    speculative_fallback: bool = True
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

@router.get("/config", tags=["System"])
def get_system_config() -> Dict[str, Any]:
    gateway = get_container().ai_gateway
    policy = gateway.policy
    
    openai_prov = gateway.providers.get("openai")
    gemini_prov = gateway.providers.get("gemini")
    
    return {
        "primary_provider": policy.primary,
        "secondary_provider": policy.secondary,
        "timeout_ms": policy.timeout_ms,
        "speculative_fallback": gateway.enable_speculative_fallback,
        "providers": {
            "local_ollama": {"enabled": True},
            "openai": {"enabled": bool(openai_prov and openai_prov.api_key)},
            "gemini": {"enabled": bool(gemini_prov and gemini_prov.api_key)},
        }
    }

@router.post("/config", tags=["System"])
def update_system_config(payload: AIConfigPayload):
    gateway = get_container().ai_gateway
    
    gateway.policy.primary = payload.primary_provider
    if payload.secondary_provider and payload.secondary_provider.lower() != "none":
        gateway.policy.secondary = payload.secondary_provider
    else:
        gateway.policy.secondary = None
        
    gateway.policy.timeout_ms = payload.timeout_ms
    gateway.enable_speculative_fallback = payload.speculative_fallback
    
    if payload.openai_api_key and payload.openai_api_key.strip('* '):
        openai_prov = gateway.providers.get("openai")
        if openai_prov:
            openai_prov.api_key = payload.openai_api_key
            
    if payload.gemini_api_key and payload.gemini_api_key.strip('* '):
        gemini_prov = gateway.providers.get("gemini")
        if gemini_prov:
            gemini_prov.api_key = payload.gemini_api_key
            
    return {"status": "success", "message": "Configuration updated successfully."}
