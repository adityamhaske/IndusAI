"""
AI evaluation endpoint — lightweight gateway diagnostics.
"""
from fastapi import APIRouter, Depends
from datetime import datetime

from app.auth.firebase_auth import AuthenticatedUser, get_current_user
from app.config.dependency_injection import get_container

router = APIRouter()


@router.get("/evaluation", tags=["AI"])
def get_ai_evaluation_data(
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Returns basic gateway health summary for evaluation UI."""
    gateway = get_container().ai_gateway
    health = gateway.get_health()

    return {
        "status": "EVALUATION_READY" if health.get("status") == "OPERATIONAL" else "NO_DATA",
        "timestamp": datetime.utcnow().isoformat(),
        "primary_provider": health.get("primary_provider"),
        "secondary_provider": health.get("secondary_provider"),
        "registered_providers": health.get("registered_providers", []),
    }
