"""
HistoryService — Persistent Intelligence Layer for the Industrial AI Assistant.

Rewritten for Firestore. All data scoped to /users/{uid}/sessions and /users/{uid}/plc_snapshots.

Provides:
 - Session lifecycle management (create, append, complete, delete)
 - Multi-dimensional listing and filtering
 - Resume payload with token trimming
 - PLC analysis snapshot tracking
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.storage.firestore_client import FirestoreClient

logger = logging.getLogger(__name__)

# How many characters we allow in the resume history before trimming
# (roughly 3000 tokens * 4 chars/token = 12 000 chars)
_RESUME_CHAR_BUDGET = 12_000


class HistoryService:
    def __init__(self, db: FirestoreClient):
        self.db = db

    # ── Session lifecycle ───────────────────────────────────────────────────────

    def create_session(
        self,
        uid: str,
        session_type: str = "chat",
        title: Optional[str] = None,
        provider: Optional[str] = None,
        project_id: Optional[str] = None,
        index_version: Optional[str] = None,
        model_name: Optional[str] = None,
        compliance_mode: bool = False,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        session_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        doc = {
            "session_type": session_type,
            "title": title,
            "provider": provider,
            "project_id": project_id,
            "index_version": index_version,
            "model_name": model_name,
            "compliance_mode": compliance_mode,
            "metadata_json": json.dumps(extra_metadata) if extra_metadata else None,
            "started_at": now,
            "completed_at": None,
            "total_tokens": 0,
            "latency_ms": 0,
            "confidence_score": None,
            "integrity_status": None,
            "messages": [],  # Embedded sub-documents for simplicity
        }
        self.db.set_doc(uid, "sessions", session_id, doc, merge=False)
        doc["id"] = session_id
        logger.info("Created session %s [%s] for user %s", session_id, session_type, uid)
        return doc

    def update_session_title(self, uid: str, session_id: str, title: str) -> None:
        self.db.set_doc(uid, "sessions", session_id, {"title": title}, merge=True)

    def append_message(
        self,
        uid: str,
        session_id: str,
        role: str,
        content: str,
        token_count: int = 0,
    ) -> Dict[str, Any]:
        from google.cloud.firestore_v1 import ArrayUnion

        msg = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "token_count": token_count,
            "created_at": datetime.utcnow().isoformat(),
        }
        col = self.db._user_col(uid, "sessions")
        col.document(session_id).update({"messages": ArrayUnion([msg])})
        return msg

    def complete_session(
        self,
        uid: str,
        session_id: str,
        total_tokens: int = 0,
        latency_ms: int = 0,
        confidence_score: Optional[float] = None,
        integrity_status: Optional[str] = None,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        update: Dict[str, Any] = {
            "completed_at": datetime.utcnow().isoformat(),
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
            "confidence_score": confidence_score,
            "integrity_status": integrity_status or "OK",
        }
        if provider:
            update["provider"] = provider
        if model_name:
            update["model_name"] = model_name
        self.db.set_doc(uid, "sessions", session_id, update, merge=True)

    def delete_session(self, uid: str, session_id: str) -> bool:
        return self.db.delete_doc(uid, "sessions", session_id)

    # ── Session querying ────────────────────────────────────────────────────────

    def list_sessions(
        self,
        uid: str,
        session_type: Optional[str] = None,
        provider: Optional[str] = None,
        project_id: Optional[str] = None,
        sort_by: str = "recent",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        filters = {}
        if session_type:
            filters["session_type"] = session_type
        if provider:
            filters["provider"] = provider
        if project_id:
            filters["project_id"] = project_id

        order_field = "started_at"
        descending = True
        if sort_by == "oldest":
            descending = False

        docs = self.db.list_docs(
            uid, "sessions",
            order_by=order_field,
            descending=descending,
            limit=limit,
            filters=filters if filters else None,
        )
        # Strip embedded messages from list view for performance
        for d in docs:
            d.pop("messages", None)
        return docs

    def get_session_with_messages(self, uid: str, session_id: str) -> Optional[Dict[str, Any]]:
        """Full session payload including all messages, for the detail view."""
        doc = self.db.get_doc(uid, "sessions", session_id)
        if not doc:
            return None
        return doc

    def get_resume_payload(self, uid: str, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Returns session metadata + token-trimmed message history safe for LLM context.
        Trims from the oldest messages first, keeping the most recent context.
        """
        full = self.get_session_with_messages(uid, session_id)
        if not full:
            return None

        messages = full.get("messages", [])
        trimmed = self._trim_to_budget(messages, _RESUME_CHAR_BUDGET)
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
        total = sum(len(m.get("content", "")) for m in messages)
        if total <= char_budget:
            return messages
        result = []
        remaining = char_budget
        for m in reversed(messages):
            remaining -= len(m.get("content", ""))
            if remaining < 0:
                break
            result.insert(0, m)
        return result

    # ── PLC Analysis Snapshots ─────────────────────────────────────────────────

    def create_plc_snapshot(
        self,
        uid: str,
        session_id: str,
        fault_id: str,
        anomaly_score: float = 0.0,
        burst_rate: float = 0.0,
        integrity_passed: bool = True,
        ai_confidence: Optional[float] = None,
        provider: Optional[str] = None,
        telemetry: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        snap_id = str(uuid.uuid4())
        doc = {
            "session_id": session_id,
            "fault_id": fault_id,
            "anomaly_score": anomaly_score,
            "burst_rate": burst_rate,
            "integrity_passed": integrity_passed,
            "ai_confidence": ai_confidence,
            "provider": provider,
            "telemetry_json": json.dumps(telemetry) if telemetry else None,
            "created_at": datetime.utcnow().isoformat(),
        }
        self.db.set_doc(uid, "plc_snapshots", snap_id, doc, merge=False)
        doc["id"] = snap_id
        return doc

    def list_plc_snapshots(
        self,
        uid: str,
        sort_by: str = "recent",
        integrity_failed_only: bool = False,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        filters = {}
        if integrity_failed_only:
            filters["integrity_passed"] = False

        return self.db.list_docs(
            uid, "plc_snapshots",
            order_by="created_at",
            descending=True,
            limit=limit,
            filters=filters if filters else None,
        )

    # ── Legacy compat ──────────────────────────────────────────────────────────

    def get_history_service(self) -> "HistoryService":
        """Self-reference for DI compatibility."""
        return self

    def get_session_history(self, uid: str, session_id: str) -> List[Dict[str, Any]]:
        """Returns messages for a session."""
        doc = self.get_session_with_messages(uid, session_id)
        if not doc:
            return []
        return doc.get("messages", [])
