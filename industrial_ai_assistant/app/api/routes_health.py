"""
Health check route — Public endpoint for monitoring.
"""
from fastapi import APIRouter
from app.services.system_health_service import get_health_service

router = APIRouter(tags=["Health"])

@router.get("/health")
def check_health():
    """
    Public health check endpoint returning system status.
    """
    health_svc = get_health_service()
    full_status = health_svc.full_status()
    
    status = full_status.get("status", "degraded")
    
    qdrant_connected = full_status.get("vector_store_connected", False)
    firestore_connected = full_status.get("firestore_connected", False)
    
    return {
        "status": "ok" if (qdrant_connected and firestore_connected) else "degraded",
        "services": {
            "qdrant": "connected" if qdrant_connected else "unreachable",
            "firestore": "connected" if firestore_connected else "unreachable"
        },
        "version": "2.0.0"
    }
