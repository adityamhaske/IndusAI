"""
StructuredIndex — deterministic, in-memory lookup store.

Holds: TagIndex, RoutineIndex, AOIIndex, IOIndex.
NO vector search here — exact lookup only.

Design:
  - Thread-safe writes via threading.Lock
  - Hard caps protect against runaway memory
  - stats() returns actual memory footprint estimate
  - all_tag_names() returns frozen set for O(1) membership test
"""
from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass, field

from app.models.project_models import AOIRecord, IORecord, RoutineRecord, TagRecord

logger = logging.getLogger(__name__)

# Hard limits
MAX_TAGS     = 50_000
MAX_ROUTINES = 5_000
MAX_IO_ROWS  = 20_000

# Warning thresholds
WARN_TAGS = 25_000


@dataclass
class StructuredIndexStats:
    tags: int = 0
    routines: int = 0
    aois: int = 0
    io_rows: int = 0
    memory_footprint_mb: float = 0.0
    at_capacity: bool = False
    warnings: list[str] = field(default_factory=list)


class StructuredIndex:
    """In-memory index with exact-match lookup for PLC structured data."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self._lock = threading.Lock()

        # Primary stores — lowercase key → record
        self._tags: dict[str, TagRecord] = {}
        self._routines: dict[str, RoutineRecord] = {}
        self._aois: dict[str, AOIRecord] = {}
        self._io: dict[str, IORecord] = {}

        # Cached frozen set of tag names (rebuilt on write)
        self._tag_name_cache: frozenset[str] | None = None

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_tag(self, record: TagRecord) -> bool:
        """Add a tag. Returns False (+ logs warning) if at capacity."""
        with self._lock:
            if len(self._tags) >= MAX_TAGS:
                logger.warning(
                    "[%s] StructuredIndex: MAX_TAGS (%d) reached — '%s' skipped.",
                    self.project_id, MAX_TAGS, record.name,
                )
                return False
            key = record.name.lower()
            self._tags[key] = record
            self._tag_name_cache = None   # invalidate
            return True

    def add_routine(self, record: RoutineRecord) -> bool:
        with self._lock:
            if len(self._routines) >= MAX_ROUTINES:
                logger.warning("[%s] MAX_ROUTINES reached.", self.project_id)
                return False
            self._routines[record.name.lower()] = record
            return True

    def add_aoi(self, record: AOIRecord) -> bool:
        with self._lock:
            self._aois[record.name.lower()] = record
            return True

    def add_io(self, record: IORecord) -> bool:
        with self._lock:
            if len(self._io) >= MAX_IO_ROWS:
                return False
            # Key: "rack:slot" or just slot
            key = f"{record.rack}:{record.slot}".lower() if record.rack else record.slot.lower()
            self._io[key] = record
            return True

    # ── Exact lookup ──────────────────────────────────────────────────────────

    def get_tag(self, name: str) -> TagRecord | None:
        """O(1) lookup. Case-insensitive."""
        return self._tags.get(name.lower())

    def get_routine(self, name: str) -> RoutineRecord | None:
        return self._routines.get(name.lower())

    def get_aoi(self, name: str) -> AOIRecord | None:
        return self._aois.get(name.lower())

    def get_io(self, slot: str, rack: str = "") -> IORecord | None:
        if rack:
            record = self._io.get(f"{rack}:{slot}".lower())
            if record:
                return record
        # Try slot as-is (may already contain rack prefix like "1:0")
        record = self._io.get(slot.lower())
        if record:
            return record
        # Try any IO record matching the slot suffix
        slot_lower = slot.lower()
        for key, rec in self._io.items():
            if key == slot_lower or key.endswith(f":{slot_lower}"):
                return rec
        return None

    # ── Prefix search ─────────────────────────────────────────────────────────

    def search_tags_prefix(self, prefix: str, limit: int = 10) -> list[TagRecord]:
        """Return up to `limit` tags whose name starts with `prefix` (case-insensitive)."""
        p = prefix.lower()
        return [v for k, v in self._tags.items() if k.startswith(p)][:limit]

    def search_io_description(self, keyword: str, limit: int = 10) -> list[IORecord]:
        kw = keyword.lower()
        return [
            v for v in self._io.values()
            if kw in v.description.lower() or kw in v.tag_name.lower()
        ][:limit]

    # ── Membership (hallucination guard) ──────────────────────────────────────

    def all_tag_names(self) -> frozenset[str]:
        """
        Cached frozenset of all tag names (original case).
        Used by HallucinationGuard for O(1) membership.
        """
        if self._tag_name_cache is None:
            with self._lock:
                self._tag_name_cache = frozenset(r.name for r in self._tags.values())
        return self._tag_name_cache

    def all_tag_names_lower(self) -> frozenset[str]:
        names = self.all_tag_names()
        return frozenset(n.lower() for n in names)

    def all_source_files(self) -> set[str]:
        """Aggregate all unique source_file paths from all indexed records."""
        with self._lock:
            files = set()
            for r in self._tags.values():
                if r.source_file: files.add(r.source_file)
            for r in self._routines.values():
                if r.source_file: files.add(r.source_file)
            for r in self._aois.values():
                if r.source_file: files.add(r.source_file)
            for r in self._io.values():
                if r.source_file: files.add(r.source_file)
            return files

    # ── Stats & memory ────────────────────────────────────────────────────────

    def stats(self) -> StructuredIndexStats:
        with self._lock:
            tag_count = len(self._tags)
            rtn_count = len(self._routines)
            mb = (
                _size_mb(self._tags)
                + _size_mb(self._routines)
                + _size_mb(self._aois)
                + _size_mb(self._io)
            )
            warnings = []
            if tag_count >= WARN_TAGS:
                warnings.append(
                    f"Tag count ({tag_count:,}) exceeds recommended threshold "
                    f"({WARN_TAGS:,}). Consider splitting into sub-projects."
                )
            return StructuredIndexStats(
                tags=tag_count,
                routines=rtn_count,
                aois=len(self._aois),
                io_rows=len(self._io),
                memory_footprint_mb=round(mb, 2),
                at_capacity=(tag_count >= MAX_TAGS or rtn_count >= MAX_ROUTINES),
                warnings=warnings,
            )

    def clear(self) -> None:
        with self._lock:
            self._tags.clear()
            self._routines.clear()
            self._aois.clear()
            self._io.clear()
            self._tag_name_cache = None
        logger.info("[%s] StructuredIndex cleared.", self.project_id)

    def remove_file(self, source_file: str) -> None:
        """Removes all records associated with a specific source file."""
        with self._lock:
            self._tags = {k: v for k, v in self._tags.items() if v.source_file != source_file}
            self._routines = {k: v for k, v in self._routines.items() if v.source_file != source_file}
            self._aois = {k: v for k, v in self._aois.items() if v.source_file != source_file}
            self._io = {k: v for k, v in self._io.items() if v.source_file != source_file}
            self._tag_name_cache = None
        logger.info("[%s] Removed records for file '%s'.", self.project_id, source_file)

    # ── Persistence ───────────────────────────────────────────────────────────

    def save_to_disk(self, folder_path: str) -> None:
        import json
        from pathlib import Path
        db = Path(folder_path) / ".indusai_structured.json"
        with self._lock:
            dump = {
                "tags": {k: v.model_dump() for k, v in self._tags.items()},
                "routines": {k: v.model_dump() for k, v in self._routines.items()},
                "aois": {k: v.model_dump() for k, v in self._aois.items()},
                "io": {k: v.model_dump() for k, v in self._io.items()},
            }
        try:
            with open(db, "w", encoding="utf-8") as f:
                json.dump(dump, f, indent=2)
            logger.info("[%s] Saved StructuredIndex to disk.", self.project_id)
        except Exception as e:
            logger.error("[%s] Failed to save StructuredIndex: %s", self.project_id, e)

    def load_from_disk(self, folder_path: str) -> bool:
        import json
        from pathlib import Path
        from app.models.project_models import TagRecord, RoutineRecord, AOIRecord, IORecord
        
        db = Path(folder_path) / ".indusai_structured.json"
        if not db.exists():
            return False
            
        try:
            with open(db, "r", encoding="utf-8") as f:
                dump = json.load(f)
            with self._lock:
                self._tags = {k: TagRecord.model_validate(v) for k, v in dump.get("tags", {}).items()}
                self._routines = {k: RoutineRecord.model_validate(v) for k, v in dump.get("routines", {}).items()}
                self._aois = {k: AOIRecord.model_validate(v) for k, v in dump.get("aois", {}).items()}
                self._io = {k: IORecord.model_validate(v) for k, v in dump.get("io", {}).items()}
                self._tag_name_cache = None
            logger.info("[%s] Loaded StructuredIndex from disk.", self.project_id)
            return True
        except Exception as e:
            logger.warning("[%s] Failed to load StructuredIndex: %s", self.project_id, e)
            return False

# ── Helpers ───────────────────────────────────────────────────────────────────

def _size_mb(obj: object) -> float:
    """Rough memory estimate in MB using sys.getsizeof (shallow)."""
    try:
        return sys.getsizeof(obj) / (1024 * 1024)
    except Exception:
        return 0.0


# ── Registry ──────────────────────────────────────────────────────────────────

_registry: dict[str, StructuredIndex] = {}
_registry_lock = threading.Lock()


def get_structured_index(project_id: str) -> StructuredIndex:
    """Return (or create) the StructuredIndex for a project."""
    with _registry_lock:
        if project_id not in _registry:
            _registry[project_id] = StructuredIndex(project_id)
        return _registry[project_id]


def clear_structured_index(project_id: str) -> None:
    with _registry_lock:
        if project_id in _registry:
            _registry[project_id].clear()
