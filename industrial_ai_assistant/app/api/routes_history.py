"""
History API — Persistent Intelligence Layer
Mounted at /api by main.py

All endpoints require Firebase Auth. Data is scoped to the authenticated user.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.firebase_auth import AuthenticatedUser, get_current_user
from app.config.dependency_injection import get_container, Container

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _serialize_session(s: dict) -> dict:
    """Sessions are now dicts from Firestore, not ORM objects."""
    return {
        "id":               s.get("id"),
        "session_type":     s.get("session_type"),
        "title":            s.get("title") or "Untitled Session",
        "provider":         s.get("provider"),
        "project_id":       s.get("project_id"),
        "index_version":    s.get("index_version"),
        "model_name":       s.get("model_name"),
        "started_at":       s.get("started_at"),
        "completed_at":     s.get("completed_at"),
        "total_tokens":     s.get("total_tokens", 0),
        "latency_ms":       s.get("latency_ms", 0),
        "confidence_score": s.get("confidence_score"),
        "integrity_status": s.get("integrity_status", "OK"),
        "compliance_mode":  s.get("compliance_mode", False),
    }


# ── GET /api/history ───────────────────────────────────────────────────────────

@router.get("/history", tags=["History"])
def list_history(
    session_type: Optional[str] = Query(None, description="chat | plc_analysis"),
    provider:     Optional[str] = Query(None),
    project_id:   Optional[str] = Query(None),
    sort_by:      str           = Query("recent", description="recent|oldest"),
    limit:        int           = Query(100, ge=1, le=500),
    user:         AuthenticatedUser = Depends(get_current_user),
    container:    Container     = Depends(get_container),
):
    """List AI sessions with optional type/provider filters."""
    sessions = container.history_service.list_sessions(
        uid=user.uid,
        session_type=session_type,
        provider=provider,
        project_id=project_id,
        sort_by=sort_by,
        limit=limit,
    )
    return [_serialize_session(s) for s in sessions]


# ── GET /api/history/session/{id} ──────────────────────────────────────────────

@router.get("/history/session/{session_id}", tags=["History"])
def get_session(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    container: Container = Depends(get_container),
):
    """Full session detail including all messages."""
    data = container.history_service.get_session_with_messages(user.uid, session_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return data


# ── DELETE /api/history/session/{id} ──────────────────────────────────────────

@router.delete("/history/session/{session_id}", tags=["History"])
def delete_session(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    container: Container = Depends(get_container),
):
    """Delete a session and all its messages."""
    deleted = container.history_service.delete_session(user.uid, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"deleted": True, "session_id": session_id}


# ── POST /api/history/session/{id}/resume ─────────────────────────────────────

@router.post("/history/session/{session_id}/resume", tags=["History"])
def resume_session(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    container: Container = Depends(get_container),
):
    """
    Returns token-trimmed message history and session metadata
    so the frontend can restore a previous conversation.
    """
    data = container.history_service.get_resume_payload(user.uid, session_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return data


# ── GET /api/history/plc ──────────────────────────────────────────────────────

@router.get("/history/plc", tags=["History"])
def list_plc_analyses(
    sort_by:               str  = Query("recent"),
    integrity_failed_only: bool = Query(False),
    limit:                 int  = Query(200, ge=1, le=1000),
    user:                  AuthenticatedUser = Depends(get_current_user),
    container:             Container = Depends(get_container),
):
    """List PLC fault analysis snapshots — the industrial audit ledger."""
    return container.history_service.list_plc_snapshots(
        uid=user.uid,
        sort_by=sort_by,
        integrity_failed_only=integrity_failed_only,
        limit=limit,
    )


# ── Legacy: GET /api/history/{session_id} ─────────────────────────────────────

@router.get("/history/{session_id}", tags=["History"])
def get_history_legacy(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    container: Container = Depends(get_container),
):
    """Backward-compatible legacy endpoint: returns message list for a session."""
    msgs = container.history_service.get_session_history(user.uid, session_id)
    return [
        {"role": m.get("role"), "content": m.get("content"), "timestamp": m.get("created_at")}
        for m in msgs
    ]
