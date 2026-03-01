"""
FaultMemory — Persistent statistical memory for fault patterns (Phase 21).

Records fault occurrences and computes historical pattern summaries
for LLM context injection. Self-updating on every PLC analysis.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from app.storage.models import FaultHistory

logger = logging.getLogger(__name__)


class FaultMemoryService:
    """Manages persistent fault statistical memory in SQLite."""

    def __init__(self, db_client):
        self._db = db_client

    def record_fault(
        self,
        machine_id: str,
        fault_code: str,
        timestamp: datetime,
        co_occurring_fault: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        """Upsert fault occurrence into the history table."""
        session = self._db.get_session()
        try:
            record = (
                session.query(FaultHistory)
                .filter_by(machine_id=machine_id, fault_code=fault_code)
                .first()
            )
            if record is None:
                record = FaultHistory(
                    machine_id=machine_id,
                    fault_code=fault_code,
                    project_id=project_id,
                    total_occurrences=0,
                    last_7d_count=0,
                    last_30d_count=0,
                    time_cluster_json="{}",
                    co_occurrence_json="{}",
                )
                session.add(record)

            # Update counters
            record.total_occurrences += 1
            record.last_seen = timestamp
            record.updated_at = datetime.utcnow()
            record.project_id = project_id or record.project_id

            # Update time cluster (hour-of-day histogram)
            try:
                clusters = json.loads(record.time_cluster_json or "{}")
            except (json.JSONDecodeError, TypeError):
                clusters = {}
            hour_key = str(timestamp.hour).zfill(2)
            clusters[hour_key] = clusters.get(hour_key, 0) + 1
            record.time_cluster_json = json.dumps(clusters)

            # Update co-occurrence matrix
            if co_occurring_fault:
                try:
                    co_map = json.loads(record.co_occurrence_json or "{}")
                except (json.JSONDecodeError, TypeError):
                    co_map = {}
                co_map[co_occurring_fault] = co_map.get(co_occurring_fault, 0) + 1
                record.co_occurrence_json = json.dumps(co_map)

            session.commit()
            logger.debug("FaultMemory: recorded %s/%s (total=%d)", machine_id, fault_code, record.total_occurrences)
        except Exception as exc:
            session.rollback()
            logger.warning("FaultMemory record failed: %s", exc)
        finally:
            session.close()

    def get_pattern_summary(self, fault_code: str, machine_id: Optional[str] = None) -> Optional[str]:
        """
        Build a human-readable historical pattern summary for LLM injection.
        Returns None if no history exists.
        """
        session = self._db.get_session()
        try:
            q = session.query(FaultHistory).filter_by(fault_code=fault_code)
            if machine_id:
                q = q.filter_by(machine_id=machine_id)
            records = q.all()

            if not records:
                return None

            lines = [f"Historical Pattern for Fault {fault_code}:"]
            total = sum(r.total_occurrences for r in records)
            lines.append(f"- Total occurrences recorded: {total}")

            # Aggregate time clusters
            agg_clusters: dict[str, int] = {}
            agg_co: dict[str, int] = {}
            machines = set()

            for r in records:
                machines.add(r.machine_id)
                try:
                    clusters = json.loads(r.time_cluster_json or "{}")
                    for h, c in clusters.items():
                        agg_clusters[h] = agg_clusters.get(h, 0) + c
                except (json.JSONDecodeError, TypeError):
                    pass
                try:
                    co_map = json.loads(r.co_occurrence_json or "{}")
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
                # Calculate percentage of top hour
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
            last_seen_list = [r.last_seen for r in records if r.last_seen]
            if last_seen_list:
                latest = max(last_seen_list)
                lines.append(f"- Last observed: {latest.strftime('%Y-%m-%d %H:%M')}")

            return "\n".join(lines)

        except Exception as exc:
            logger.warning("FaultMemory pattern summary failed: %s", exc)
            return None
        finally:
            session.close()

    def get_all_histories(self, project_id: Optional[str] = None, limit: int = 100):
        """Return all fault history records for observability."""
        session = self._db.get_session()
        try:
            q = session.query(FaultHistory)
            if project_id:
                q = q.filter_by(project_id=project_id)
            return q.order_by(FaultHistory.updated_at.desc()).limit(limit).all()
        finally:
            session.close()
