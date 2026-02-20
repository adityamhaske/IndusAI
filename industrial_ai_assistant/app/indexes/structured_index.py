"""
StructuredIndex — In-memory exact-lookup store for PLC project artifacts.

Design:
  - O(1) lookup for tags, routines, AOIs, IO records
  - No vector search — structured data only
  - Memory footprint tracking via sys.getsizeof
  - MAX_TAGS guard (warning at 80%, error log at 100%)
  - Thread-safe reads (writes assumed to happen only during ingestion)
"""
import logging
import sys
from typing import Dict, List, Optional

from app.models.project_models import AOIRecord, IORecord, RoutineRecord, TagRecord

logger = logging.getLogger(__name__)

MAX_TAGS = 50_000
_WARN_AT = int(MAX_TAGS * 0.80)


def _deep_sizeof(obj) -> int:
    """Rough recursive size estimate in bytes."""
    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        size += sum(_deep_sizeof(k) + _deep_sizeof(v) for k, v in obj.items())
    elif isinstance(obj, (list, tuple, set, frozenset)):
        size += sum(_deep_sizeof(i) for i in obj)
    elif hasattr(obj, "__dict__"):
        size += _deep_sizeof(vars(obj))
    return size


class StructuredIndex:
    """
    Per-project in-memory structured index.
    Contains four sub-indexes, each providing O(1) keyed lookup.
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self._tags: Dict[str, TagRecord] = {}          # name → TagRecord
        self._routines: Dict[str, RoutineRecord] = {}  # name → RoutineRecord
        self._aois: Dict[str, AOIRecord] = {}          # name → AOIRecord
        self._ios: Dict[str, IORecord] = {}            # "rack/slot" → IORecord
        self._warnings: List[str] = []

    # ── Bulk load (called by ingestion pipeline) ──────────────────────────────

    def load_tags(self, records: List[TagRecord]) -> None:
        for r in records:
            key = r.name.upper()
            self._tags[key] = r
        n = len(self._tags)
        if n >= MAX_TAGS:
            msg = f"[{self.project_id}] Tag count {n} reached MAX_TAGS={MAX_TAGS}. Index may be incomplete."
            logger.error(msg)
            self._warnings.append(msg)
        elif n >= _WARN_AT:
            msg = f"[{self.project_id}] Tag count {n} ≥ 80% of MAX_TAGS={MAX_TAGS}. Monitor memory."
            logger.warning(msg)
            self._warnings.append(msg)

    def load_routines(self, records: List[RoutineRecord]) -> None:
        for r in records:
            self._routines[r.name.upper()] = r

    def load_aois(self, records: List[AOIRecord]) -> None:
        for r in records:
            self._aois[r.name.upper()] = r

    def load_io(self, records: List[IORecord]) -> None:
        for r in records:
            k = r.key.upper() if r.key else r.slot.upper()
            if k:
                self._ios[k] = r

    # ── Lookup methods ────────────────────────────────────────────────────────

    def get_tag(self, name: str) -> Optional[TagRecord]:
        """Exact tag lookup (case-insensitive)."""
        return self._tags.get(name.upper())

    def get_routine(self, name: str) -> Optional[RoutineRecord]:
        """Exact routine lookup (case-insensitive)."""
        return self._routines.get(name.upper())

    def get_aoi(self, name: str) -> Optional[AOIRecord]:
        """Exact AOI lookup (case-insensitive)."""
        return self._aois.get(name.upper())

    def get_io(self, slot: str, rack: str = "") -> Optional[IORecord]:
        """Lookup by slot or rack/slot key (case-insensitive)."""
        key = f"{rack}/{slot}".strip("/").upper() if rack else slot.upper()
        return self._ios.get(key)

    def search_tags_prefix(self, prefix: str, limit: int = 20) -> List[TagRecord]:
        """Return tags whose name starts with prefix (case-insensitive)."""
        p = prefix.upper()
        return [v for k, v in self._tags.items() if k.startswith(p)][:limit]

    def all_tag_names(self) -> frozenset:
        """Return all tag names as a frozenset (case-normalized to upper)."""
        return frozenset(self._tags.keys())

    def all_routine_names(self) -> frozenset:
        return frozenset(self._routines.keys())

    # ── Observability ─────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """
        Return memory footprint and count metrics.
        memory_mb is an approximation via sys.getsizeof.
        """
        tag_mem = _deep_sizeof(self._tags)
        rtn_mem = _deep_sizeof(self._routines)
        aoi_mem = _deep_sizeof(self._aois)
        io_mem = _deep_sizeof(self._ios)
        total_mb = (tag_mem + rtn_mem + aoi_mem + io_mem) / (1024 ** 2)

        result = {
            "project_id": self.project_id,
            "tags": len(self._tags),
            "routines": len(self._routines),
            "aois": len(self._aois),
            "ios": len(self._ios),
            "memory_mb": round(total_mb, 3),
            "warnings": list(self._warnings),
        }

        if total_mb > 500:
            result["warnings"].append(
                f"StructuredIndex memory {total_mb:.1f}MB exceeds 500MB. Consider reducing project scope."
            )
        return result

    def clear(self) -> None:
        """Purge all data (called on project reset/reindex)."""
        self._tags.clear()
        self._routines.clear()
        self._aois.clear()
        self._ios.clear()
        self._warnings.clear()


# ── Global registry ───────────────────────────────────────────────────────────
# One StructuredIndex per project_id, shared across request handlers.
_registry: Dict[str, StructuredIndex] = {}


def get_structured_index(project_id: str) -> StructuredIndex:
    if project_id not in _registry:
        _registry[project_id] = StructuredIndex(project_id)
    return _registry[project_id]


def delete_structured_index(project_id: str) -> None:
    if project_id in _registry:
        _registry[project_id].clear()
        del _registry[project_id]
