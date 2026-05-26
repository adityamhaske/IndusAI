"""
FaultExperienceIndex — Self-improving explanation store.

Rewritten for Firestore. All data scoped to /users/{uid}/fault_experiences.

Stores past AI-generated explanations per fault_code+machine, and retrieves
the best historical explanation for injection into new LLM calls.
This creates system learning without model fine-tuning.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from app.storage.firestore_client import FirestoreClient

logger = logging.getLogger(__name__)

MAX_EXPERIENCES_PER_FAULT = 5  # Keep top 5, prune rest


class FaultExperienceIndex:
    """Manages the self-improving fault explanation store."""

    def __init__(self, db: FirestoreClient):
        self._db = db

    def store_experience(
        self,
        uid: str,
        fault_code: str,
        explanation_text: str,
        confidence: float,
        machine_id: Optional[str] = None,
        project_id: Optional[str] = None,
        retrieval_score_avg: Optional[float] = None,
    ) -> None:
        """Save a new AI explanation. Prune old/low-confidence entries."""
        if not explanation_text or len(explanation_text.strip()) < 20:
            return  # Don't store trivially short explanations

        exp_id = str(uuid.uuid4())
        doc = {
            "fault_code": fault_code,
            "machine_id": machine_id or "",
            "project_id": project_id,
            "explanation_text": explanation_text,
            "confidence": confidence,
            "retrieval_score_avg": retrieval_score_avg,
            "created_at": datetime.utcnow().isoformat(),
        }
        self._db.set_doc(uid, "fault_experiences", exp_id, doc, merge=False)

        # Prune: keep only top N by confidence per fault_code
        col = self._db._user_col(uid, "fault_experiences")
        from google.cloud.firestore_v1 import Query
        all_for_fault = list(
            col.where("fault_code", "==", fault_code)
            .order_by("confidence", direction=Query.DESCENDING)
            .stream()
        )
        if len(all_for_fault) > MAX_EXPERIENCES_PER_FAULT:
            to_delete = all_for_fault[MAX_EXPERIENCES_PER_FAULT:]
            batch = self._db.db.batch()
            for old_snap in to_delete:
                batch.delete(old_snap.reference)
            batch.commit()
            logger.debug("FaultExperience: pruned %d old entries for %s", len(to_delete), fault_code)

        logger.debug("FaultExperience: stored explanation for %s (confidence=%.2f)", fault_code, confidence)

    def get_best_experience(self, uid: str, fault_code: str, machine_id: Optional[str] = None) -> Optional[str]:
        """
        Retrieve the highest-confidence past explanation for this fault.
        Returns formatted string for LLM injection, or None if no history.
        """
        col = self._db._user_col(uid, "fault_experiences")
        from google.cloud.firestore_v1 import Query
        q = col.where("fault_code", "==", fault_code)
        if machine_id:
            q = q.where("machine_id", "==", machine_id)

        best_snap = list(q.order_by("confidence", direction=Query.DESCENDING).limit(1).stream())
        if not best_snap:
            return None

        best = best_snap[0].to_dict()
        return (
            f"Prior Analysis (confidence {best['confidence']:.0%}):\n"
            f"{best['explanation_text']}\n"
            f"(Recorded: {best.get('created_at', 'unknown')})"
        )

    def get_experience_count(self, uid: str, fault_code: Optional[str] = None) -> int:
        """Count stored experiences, optionally filtered by fault_code."""
        col = self._db._user_col(uid, "fault_experiences")
        if fault_code:
            q = col.where("fault_code", "==", fault_code)
        else:
            q = col
        return len(list(q.stream()))
