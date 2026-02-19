from typing import List
from fastapi import APIRouter, Depends
from app.core.schemas import LogEntry
from app.config.dependency_injection import get_container, Container

router = APIRouter()

@router.get("/logs", response_model=List[LogEntry])
def get_logs(limit: int = 100, container: Container = Depends(get_container)):
    logs = container.log_service.get_logs(limit)
    return [
        LogEntry(
            timestamp=str(l.timestamp),
            level=l.level,
            message=l.message,
            module=l.module or "unknown"
        ) for l in logs
    ]
