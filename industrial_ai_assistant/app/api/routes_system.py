"""
System health API routes.
Mounted at /api/system by main.py.
"""
import logging
from fastapi import APIRouter
from typing import Dict, Any
from app.services.system_health_service import get_health_service
from app.config.version import get_system_versions

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", tags=["System"])
def system_health():
    """
    Probe Qdrant Cloud and Firestore connectivity.
    Returns status='healthy' when all subsystems are reachable,
    status='degraded' when any component is unavailable.
    """
    svc = get_health_service()
    result = svc.full_status()
    logger.info(
        "Health probe: status=%s vs=%s firestore=%s",
        result["status"],
        result["vector_store_connected"],
        result["firestore_connected"],
    )
    return result


@router.get("/version", tags=["System"])
def system_version():
    """
    Expose immutable release version mappings for CI/CD tracking.
    """
    return get_system_versions()


@router.get("/config", tags=["System"])
def get_system_config() -> Dict[str, Any]:
    """
    Returns system-level configuration (non-sensitive).
    User-specific provider config is in /api/user/settings (Phase 3).
    """
    from app.config.settings import settings

    return {
        "architecture": "cloud-native",
        "database": "firestore",
        "vector_store": "qdrant_cloud",
        "qdrant_configured": bool(settings.QDRANT_URL),
        "firebase_storage_configured": bool(settings.FIREBASE_STORAGE_BUCKET),
        "auth": "firebase",
        "byok": True,
    }
