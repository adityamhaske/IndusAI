"""
System health API routes.
Mounted at /api/system/health by main.py.
"""
import logging
from fastapi import APIRouter
from app.services.system_health_service import get_health_service

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
