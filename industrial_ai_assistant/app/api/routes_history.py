"""
History API — Phase 19 Persistent Intelligence Layer
Mounted at /api by main.py
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.config.dependency_injection import get_container, Container

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _serialize_session(s) -> dict:
    return {
        "id":                   s.id,
        "session_type":         s.session_type,
        "title":                s.title or "Untitled Session",
        "provider":             s.provider,
        "project_id":           s.project_id,
        "index_version":        s.index_version,
        "model_name":           s.model_name,
        "started_at":           s.started_at.isoformat() if s.started_at else None,
        "completed_at":         s.completed_at.isoformat() if s.completed_at else None,
        "total_tokens":         s.total_tokens or 0,
        "latency_ms":           s.latency_ms or 0,
        "confidence_score":     s.confidence_score,
        "integrity_status":     s.integrity_status or "OK",
        "compliance_mode":      s.compliance_mode or False,
        "gateway_version":      s.gateway_version,
        "prompt_schema_version":s.prompt_schema_version,
    }


# ── GET /api/history ───────────────────────────────────────────────────────────

@router.get("/history", tags=["History"])
def list_history(
    session_type: Optional[str] = Query(None, description="chat | plc_analysis"),
    provider:     Optional[str] = Query(None),
    project_id:   Optional[str] = Query(None),
    sort_by:      str           = Query("recent", description="recent|oldest|provider|confidence|tokens|integrity"),
    limit:        int           = Query(100, ge=1, le=500),
    container:    Container     = Depends(get_container),
):
    """List AI sessions with optional type/provider filters and multi-sort."""
    sessions = container.history_service.list_sessions(
        session_type=session_type,
        provider=provider,
        project_id=project_id,
        sort_by=sort_by,
        limit=limit,
    )
    return [_serialize_session(s) for s in sessions]


# ── GET /api/history/session/{id} ──────────────────────────────────────────────

@router.get("/history/session/{session_id}", tags=["History"])
def get_session(session_id: str, container: Container = Depends(get_container)):
    """Full session detail including all messages."""
    data = container.history_service.get_session_with_messages(session_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return data


# ── DELETE /api/history/session/{id} ──────────────────────────────────────────

@router.delete("/history/session/{session_id}", tags=["History"])
def delete_session(session_id: str, container: Container = Depends(get_container)):
    """Delete a session and all its messages (cascade)."""
    deleted = container.history_service.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"deleted": True, "session_id": session_id}


# ── POST /api/history/session/{id}/resume ─────────────────────────────────────

@router.post("/history/session/{session_id}/resume", tags=["History"])
def resume_session(session_id: str, container: Container = Depends(get_container)):
    """
    Returns token-trimmed message history and session metadata
    so the frontend can restore a previous conversation.
    History is trimmed from oldest messages first to stay within token budget.
    """
    data = container.history_service.get_resume_payload(session_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return data


# ── GET /api/history/plc ──────────────────────────────────────────────────────

@router.get("/history/plc", tags=["History"])
def list_plc_analyses(
    sort_by:               str  = Query("recent", description="recent|anomaly|fault|integrity|provider"),
    integrity_failed_only: bool = Query(False),
    limit:                 int  = Query(200, ge=1, le=1000),
    container:             Container = Depends(get_container),
):
    """List PLC fault analysis snapshots — the industrial audit ledger."""
    return container.history_service.list_plc_snapshots(
        sort_by=sort_by,
        integrity_failed_only=integrity_failed_only,
        limit=limit,
    )


# ── Legacy: GET /api/history/{session_id} ─────────────────────────────────────

@router.get("/history/{session_id}", tags=["History"])
def get_history_legacy(session_id: str, container: Container = Depends(get_container)):
    """Backward-compatible legacy endpoint: returns message list for a session."""
    msgs = container.history_service.get_session_history(session_id)
    return [
        {"role": m.role, "content": m.content, "timestamp": m.created_at}
        for m in msgs
    ]
