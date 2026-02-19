from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from app.config.dependency_injection import get_container, Container

router = APIRouter()

@router.get("/history/{session_id}")
def get_history(session_id: str, container: Container = Depends(get_container)):
    msgs = container.history_service.get_session_history(session_id)
    return [
        {
            "role": m.role,
            "content": m.content,
            "timestamp": m.timestamp
        }
        for m in msgs
    ]
