"""
FirestoreClient — Replaces SQLiteClient for all persistent storage.

All data is stored under /users/{uid}/... for multi-tenant isolation.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from google.cloud.firestore_v1 import Client as FirestoreNativeClient

from app.core.firebase import get_firestore_client

logger = logging.getLogger(__name__)


class FirestoreClient:
    """Thin wrapper around the Firestore Admin SDK."""

    def __init__(self):
        self._db: FirestoreNativeClient = get_firestore_client()

    # ── helpers ────────────────────────────────────────────────────────────────

    def _user_col(self, uid: str, subcollection: str):
        """Return a CollectionReference at /users/{uid}/{subcollection}."""
        return self._db.collection("users").document(uid).collection(subcollection)

    # ── generic CRUD ───────────────────────────────────────────────────────────

    def set_doc(
        self, uid: str, subcollection: str, doc_id: str, data: Dict[str, Any], merge: bool = True,
    ) -> None:
        """Create or merge-update a document."""
        self._user_col(uid, subcollection).document(doc_id).set(data, merge=merge)

    def get_doc(self, uid: str, subcollection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        snap = self._user_col(uid, subcollection).document(doc_id).get()
        if snap.exists:
            d = snap.to_dict()
            d["id"] = snap.id
            return d
        return None

    def delete_doc(self, uid: str, subcollection: str, doc_id: str) -> bool:
        ref = self._user_col(uid, subcollection).document(doc_id)
        if ref.get().exists:
            ref.delete()
            return True
        return False

    def list_docs(
        self,
        uid: str,
        subcollection: str,
        order_by: Optional[str] = None,
        descending: bool = True,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        List documents with optional ordering, limit, and equality filters.
        """
        q = self._user_col(uid, subcollection)
        if filters:
            for field, value in filters.items():
                q = q.where(field, "==", value)
        if order_by:
            from google.cloud.firestore_v1 import Query
            direction = Query.DESCENDING if descending else Query.ASCENDING
            q = q.order_by(order_by, direction=direction)
        q = q.limit(limit)

        results = []
        for snap in q.stream():
            d = snap.to_dict()
            d["id"] = snap.id
            results.append(d)
        return results

    def delete_subcollection(self, uid: str, subcollection: str, batch_size: int = 100) -> int:
        """Delete all documents in a user's subcollection. Returns count deleted."""
        col = self._user_col(uid, subcollection)
        deleted = 0
        while True:
            docs = list(col.limit(batch_size).stream())
            if not docs:
                break
            batch = self._db.batch()
            for doc in docs:
                batch.delete(doc.reference)
            batch.commit()
            deleted += len(docs)
        return deleted

    @property
    def db(self) -> FirestoreNativeClient:
        """Expose raw Firestore client for advanced queries."""
        return self._db


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[FirestoreClient] = None


def get_firestore() -> FirestoreClient:
    global _instance
    if _instance is None:
        _instance = FirestoreClient()
    return _instance
