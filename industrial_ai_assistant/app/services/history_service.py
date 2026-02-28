"""
HistoryService — Persistent Intelligence Layer for the Industrial AI Assistant.

Provides:
 - Session lifecycle management (create, append, complete, delete)
 - Multi-dimensional listing and filtering
 - Resume payload with token trimming
 - PLC analysis snapshot tracking
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.storage.sqlite_client import SQLiteClient
from app.storage.models import ChatSession, ChatMessage, PLCAnalysisSnapshot

logger = logging.getLogger(__name__)

# How many characters we allow in the resume history before trimming
# (roughly 3000 tokens * 4 chars/token = 12 000 chars)
_RESUME_CHAR_BUDGET = 12_000


class HistoryService:
    def __init__(self, db_client: SQLiteClient):
        self.db_client = db_client

    # ── Session lifecycle ───────────────────────────────────────────────────────

    def create_session(
        self,
        session_type: str = "chat",
        title: Optional[str] = None,
        provider: Optional[str] = None,
        project_id: Optional[str] = None,
        index_version: Optional[str] = None,
        model_name: Optional[str] = None,
        compliance_mode: bool = False,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> ChatSession:
        session = self.db_client.get_session()
        try:
            obj = ChatSession(
                session_type=session_type,
                title=title,
                provider=provider,
                project_id=project_id,
                index_version=index_version,
                model_name=model_name,
                compliance_mode=compliance_mode,
                metadata_json=json.dumps(extra_metadata) if extra_metadata else None,
                started_at=datetime.utcnow(),
            )
            session.add(obj)
            session.commit()
            session.refresh(obj)
            logger.info("Created session %s [%s]", obj.id, session_type)
            return obj
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_session_title(self, session_id: str, title: str) -> None:
        session = self.db_client.get_session()
        try:
            obj = session.query(ChatSession).filter_by(id=session_id).first()
            if obj:
                obj.title = title
                session.commit()
        finally:
            session.close()

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        token_count: int = 0,
    ) -> ChatMessage:
        session = self.db_client.get_session()
        try:
            msg = ChatMessage(
                session_id=session_id,
                role=role,
                content=content,
                token_count=token_count,
                created_at=datetime.utcnow(),
            )
            session.add(msg)
            session.commit()
            session.refresh(msg)
            return msg
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def complete_session(
        self,
        session_id: str,
        total_tokens: int = 0,
        latency_ms: int = 0,
        confidence_score: Optional[float] = None,
        integrity_status: Optional[str] = None,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        session = self.db_client.get_session()
        try:
            obj = session.query(ChatSession).filter_by(id=session_id).first()
            if obj:
                obj.completed_at    = datetime.utcnow()
                obj.total_tokens    = total_tokens
                obj.latency_ms      = latency_ms
                obj.confidence_score = confidence_score
                obj.integrity_status = integrity_status or "OK"
                if provider:
                    obj.provider = provider
                if model_name:
                    obj.model_name = model_name
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_session(self, session_id: str) -> bool:
        session = self.db_client.get_session()
        try:
            obj = session.query(ChatSession).filter_by(id=session_id).first()
            if not obj:
                return False
            session.delete(obj)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── Session querying ────────────────────────────────────────────────────────

    _SORT_MAP = {
        "recent":     (ChatSession.started_at,       True),
        "oldest":     (ChatSession.started_at,       False),
        "provider":   (ChatSession.provider,         False),
        "confidence": (ChatSession.confidence_score, True),
        "tokens":     (ChatSession.total_tokens,     True),
        "integrity":  (ChatSession.integrity_status, False),
    }

    def list_sessions(
        self,
        session_type: Optional[str] = None,
        provider: Optional[str] = None,
        project_id: Optional[str] = None,
        sort_by: str = "recent",
        limit: int = 100,
    ) -> List[ChatSession]:
        session = self.db_client.get_session()
        try:
            q = session.query(ChatSession)
            if session_type:
                q = q.filter(ChatSession.session_type == session_type)
            if provider:
                q = q.filter(ChatSession.provider == provider)
            if project_id:
                q = q.filter(ChatSession.project_id == project_id)

            col, descending = self._SORT_MAP.get(sort_by, (ChatSession.started_at, True))
            q = q.order_by(col.desc() if descending else col.asc())

            rows = q.limit(limit).all()
            # Detach from session — expunge to allow returning outside context
            result = []
            for r in rows:
                session.expunge(r)
                result.append(r)
            return result
        finally:
            session.close()

    def get_session_with_messages(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Full session payload including all messages, for the detail view."""
        db = self.db_client.get_session()
        try:
            obj = db.query(ChatSession).filter_by(id=session_id).first()
            if not obj:
                return None
            msgs = (
                db.query(ChatMessage)
                .filter_by(session_id=session_id)
                .order_by(ChatMessage.created_at)
                .all()
            )
            return {
                "id": obj.id,
                "session_type": obj.session_type,
                "title": obj.title,
                "provider": obj.provider,
                "project_id": obj.project_id,
                "index_version": obj.index_version,
                "model_name": obj.model_name,
                "started_at": obj.started_at.isoformat() if obj.started_at else None,
                "completed_at": obj.completed_at.isoformat() if obj.completed_at else None,
                "total_tokens": obj.total_tokens,
                "latency_ms": obj.latency_ms,
                "confidence_score": obj.confidence_score,
                "integrity_status": obj.integrity_status,
                "compliance_mode": obj.compliance_mode,
                "messages": [
                    {
                        "id": m.id,
                        "role": m.role,
                        "content": m.content,
                        "token_count": m.token_count,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in msgs
                ],
            }
        finally:
            db.close()

    def get_resume_payload(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Returns session metadata + token-trimmed message history safe for LLM context.
        Trims from the oldest messages first, keeping the most recent context.
        """
        full = self.get_session_with_messages(session_id)
        if not full:
            return None

        messages = full.get("messages", [])
        trimmed  = self._trim_to_budget(messages, _RESUME_CHAR_BUDGET)
        was_trimmed = len(trimmed) < len(messages)

        return {
            **full,
            "messages": trimmed,
            "resume_trimmed": was_trimmed,
            "original_message_count": len(messages),
        }

    @staticmethod
    def _trim_to_budget(messages: List[Dict], char_budget: int) -> List[Dict]:
        """Keep the tail of messages that fits within char_budget."""
        total = sum(len(m["content"]) for m in messages)
        if total <= char_budget:
            return messages
        result = []
        remaining = char_budget
        for m in reversed(messages):
            remaining -= len(m["content"])
            if remaining < 0:
                break
            result.insert(0, m)
        return result

    # ── PLC Analysis Snapshots ─────────────────────────────────────────────────

    def create_plc_snapshot(
        self,
        session_id: str,
        fault_id: str,
        anomaly_score: float = 0.0,
        burst_rate: float = 0.0,
        integrity_passed: bool = True,
        ai_confidence: Optional[float] = None,
        provider: Optional[str] = None,
        telemetry: Optional[Dict[str, Any]] = None,
    ) -> PLCAnalysisSnapshot:
        session = self.db_client.get_session()
        try:
            snap = PLCAnalysisSnapshot(
                session_id=session_id,
                fault_id=fault_id,
                anomaly_score=anomaly_score,
                burst_rate=burst_rate,
                integrity_passed=integrity_passed,
                ai_confidence=ai_confidence,
                provider=provider,
                telemetry_json=json.dumps(telemetry) if telemetry else None,
                created_at=datetime.utcnow(),
            )
            session.add(snap)
            session.commit()
            session.refresh(snap)
            return snap
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    _PLC_SORT_MAP = {
        "recent":    (PLCAnalysisSnapshot.created_at,    True),
        "anomaly":   (PLCAnalysisSnapshot.anomaly_score, True),
        "fault":     (PLCAnalysisSnapshot.fault_id,      False),
        "integrity": (PLCAnalysisSnapshot.integrity_passed, False),
        "provider":  (PLCAnalysisSnapshot.provider,      False),
    }

    def list_plc_snapshots(
        self,
        sort_by: str = "recent",
        integrity_failed_only: bool = False,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        session = self.db_client.get_session()
        try:
            q = session.query(PLCAnalysisSnapshot)
            if integrity_failed_only:
                q = q.filter(PLCAnalysisSnapshot.integrity_passed == False)  # noqa: E712

            col, descending = self._PLC_SORT_MAP.get(sort_by, (PLCAnalysisSnapshot.created_at, True))
            q = q.order_by(col.desc() if descending else col.asc())

            rows = q.limit(limit).all()
            result = []
            for r in rows:
                result.append({
                    "id": r.id,
                    "session_id": r.session_id,
                    "fault_id": r.fault_id,
                    "anomaly_score": r.anomaly_score,
                    "burst_rate": r.burst_rate,
                    "integrity_passed": r.integrity_passed,
                    "ai_confidence": r.ai_confidence,
                    "provider": r.provider,
                    "analysis_version": r.analysis_version,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                })
            return result
        finally:
            session.close()

    # ── Unified activity feed ──────────────────────────────────────────────────

    def get_history_service(self) -> "HistoryService":
        """Self-reference for DI compatibility."""
        return self

    def get_session_history(self, session_id: str) -> List[ChatMessage]:
        """Legacy compatibility — returns ChatMessage ORM rows."""
        db = self.db_client.get_session()
        try:
            msgs = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at)
                .all()
            )
            result = []
            for m in msgs:
                db.expunge(m)
                result.append(m)
            return result
        finally:
            db.close()
