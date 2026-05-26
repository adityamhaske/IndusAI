"""
FaultMemory — Persistent statistical memory for fault patterns.

Rewritten for Firestore. All data scoped to /users/{uid}/fault_history.

Records fault occurrences and computes historical pattern summaries
for LLM context injection. Self-updating on every PLC analysis.
"""
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from app.storage.firestore_client import FirestoreClient

logger = logging.getLogger(__name__)


class FaultMemoryService:
    """Manages persistent fault statistical memory in Firestore."""

    def __init__(self, db: FirestoreClient):
        self._db = db

    def _doc_id(self, machine_id: str, fault_code: str) -> str:
        return f"{machine_id}__{fault_code}"

    def record_fault(
        self,
        uid: str,
        machine_id: str,
        fault_code: str,
        timestamp: datetime,
        co_occurring_fault: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        """Upsert fault occurrence into the history."""
        doc_id = self._doc_id(machine_id, fault_code)
        existing = self._db.get_doc(uid, "fault_history", doc_id)

        if existing is None:
            existing = {
                "machine_id": machine_id,
                "fault_code": fault_code,
                "project_id": project_id,
                "total_occurrences": 0,
                "time_cluster_json": "{}",
                "co_occurrence_json": "{}",
            }

        existing["total_occurrences"] = existing.get("total_occurrences", 0) + 1
        existing["last_seen"] = timestamp.isoformat()
        existing["updated_at"] = datetime.utcnow().isoformat()
        if project_id:
            existing["project_id"] = project_id

        # Update time cluster (hour-of-day histogram)
        try:
            clusters = json.loads(existing.get("time_cluster_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            clusters = {}
        hour_key = str(timestamp.hour).zfill(2)
        clusters[hour_key] = clusters.get(hour_key, 0) + 1
        existing["time_cluster_json"] = json.dumps(clusters)

        # Update co-occurrence matrix
        if co_occurring_fault:
            try:
                co_map = json.loads(existing.get("co_occurrence_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                co_map = {}
            co_map[co_occurring_fault] = co_map.get(co_occurring_fault, 0) + 1
            existing["co_occurrence_json"] = json.dumps(co_map)

        self._db.set_doc(uid, "fault_history", doc_id, existing, merge=False)
        logger.debug("FaultMemory: recorded %s/%s (total=%d)", machine_id, fault_code, existing["total_occurrences"])

    def get_pattern_summary(self, uid: str, fault_code: str, machine_id: Optional[str] = None) -> Optional[str]:
        """
        Build a human-readable historical pattern summary for LLM injection.
        Returns None if no history exists.
        """
        # Query all fault_history docs with matching fault_code
        col = self._db._user_col(uid, "fault_history")
        q = col.where("fault_code", "==", fault_code)
        if machine_id:
            q = q.where("machine_id", "==", machine_id)

        records = [snap.to_dict() for snap in q.stream()]
        if not records:
            return None

        lines = [f"Historical Pattern for Fault {fault_code}:"]
        total = sum(r.get("total_occurrences", 0) for r in records)
        lines.append(f"- Total occurrences recorded: {total}")

        # Aggregate time clusters
        agg_clusters: Dict[str, int] = {}
        agg_co: Dict[str, int] = {}
        machines = set()

        for r in records:
            machines.add(r.get("machine_id", ""))
            try:
                clusters = json.loads(r.get("time_cluster_json", "{}"))
                for h, c in clusters.items():
                    agg_clusters[h] = agg_clusters.get(h, 0) + c
            except (json.JSONDecodeError, TypeError):
                pass
            try:
                co_map = json.loads(r.get("co_occurrence_json", "{}"))
                for f, c in co_map.items():
                    agg_co[f] = agg_co.get(f, 0) + c
            except (json.JSONDecodeError, TypeError):
                pass

        if len(machines) > 1:
            lines.append(f"- Affected machines: {', '.join(sorted(machines))}")

        # Peak hours
        if agg_clusters:
            sorted_hours = sorted(agg_clusters.items(), key=lambda x: x[1], reverse=True)
            peak = sorted_hours[:3]
            peak_str = ", ".join(f"{h}:00 ({c} times)" for h, c in peak)
            top_count = peak[0][1]
            pct = round(top_count / total * 100) if total > 0 else 0
            lines.append(f"- Peak occurrence hours: {peak_str}")
            lines.append(f"- {pct}% of occurrences between {peak[0][0]}:00–{int(peak[0][0])+1}:00")

        # Co-occurring faults
        if agg_co:
            top_co = sorted(agg_co.items(), key=lambda x: x[1], reverse=True)[:3]
            co_str = ", ".join(f"{f} ({c} times)" for f, c in top_co)
            lines.append(f"- Frequently co-occurring faults: {co_str}")

        # Last seen
        last_seen_list = [r.get("last_seen") for r in records if r.get("last_seen")]
        if last_seen_list:
            latest = max(last_seen_list)
            lines.append(f"- Last observed: {latest}")

        return "\n".join(lines)

    def get_all_histories(self, uid: str, project_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Return all fault history records for observability."""
        filters = {}
        if project_id:
            filters["project_id"] = project_id
        return self._db.list_docs(
            uid, "fault_history",
            order_by="updated_at",
            descending=True,
            limit=limit,
            filters=filters if filters else None,
        )
