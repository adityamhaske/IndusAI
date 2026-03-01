"""
FaultExperienceIndex — Self-improving explanation store (Phase 21).

Stores past AI-generated explanations per fault_code+machine, and retrieves
the best historical explanation for injection into new LLM calls.
This creates system learning without model fine-tuning.
"""
import logging
from datetime import datetime
from typing import Optional

from app.storage.models import FaultExperience

logger = logging.getLogger(__name__)

MAX_EXPERIENCES_PER_FAULT = 5  # Keep top 5, prune rest


class FaultExperienceIndex:
    """Manages the self-improving fault explanation store."""

    def __init__(self, db_client):
        self._db = db_client

    def store_experience(
        self,
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

        session = self._db.get_session()
        try:
            exp = FaultExperience(
                fault_code=fault_code,
                machine_id=machine_id or "",
                project_id=project_id,
                explanation_text=explanation_text,
                confidence=confidence,
                retrieval_score_avg=retrieval_score_avg,
                created_at=datetime.utcnow(),
            )
            session.add(exp)
            session.commit()

            # Prune: keep only top N by confidence per fault_code
            all_for_fault = (
                session.query(FaultExperience)
                .filter_by(fault_code=fault_code)
                .order_by(FaultExperience.confidence.desc())
                .all()
            )
            if len(all_for_fault) > MAX_EXPERIENCES_PER_FAULT:
                to_delete = all_for_fault[MAX_EXPERIENCES_PER_FAULT:]
                for old in to_delete:
                    session.delete(old)
                session.commit()
                logger.debug("FaultExperience: pruned %d old entries for %s", len(to_delete), fault_code)

            logger.debug("FaultExperience: stored explanation for %s (confidence=%.2f)", fault_code, confidence)
        except Exception as exc:
            session.rollback()
            logger.warning("FaultExperience store failed: %s", exc)
        finally:
            session.close()

    def get_best_experience(self, fault_code: str, machine_id: Optional[str] = None) -> Optional[str]:
        """
        Retrieve the highest-confidence past explanation for this fault.
        Returns formatted string for LLM injection, or None if no history.
        """
        session = self._db.get_session()
        try:
            q = session.query(FaultExperience).filter_by(fault_code=fault_code)
            if machine_id:
                q = q.filter_by(machine_id=machine_id)

            best = q.order_by(FaultExperience.confidence.desc()).first()
            if best is None:
                return None

            return (
                f"Prior Analysis (confidence {best.confidence:.0%}):\n"
                f"{best.explanation_text}\n"
                f"(Recorded: {best.created_at.strftime('%Y-%m-%d %H:%M')})"
            )
        except Exception as exc:
            logger.warning("FaultExperience retrieval failed: %s", exc)
            return None
        finally:
            session.close()

    def get_experience_count(self, fault_code: Optional[str] = None) -> int:
        """Count stored experiences, optionally filtered by fault_code."""
        session = self._db.get_session()
        try:
            q = session.query(FaultExperience)
            if fault_code:
                q = q.filter_by(fault_code=fault_code)
            return q.count()
        finally:
            session.close()
