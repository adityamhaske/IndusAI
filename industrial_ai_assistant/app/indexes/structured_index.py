"""
StructuredIndex — deterministic, in-memory, per-project PLC entity index.

Design principles:
  - O(1) lookup via dict — no vector search
  - Case-insensitive, strip-normalised keys
  - Per-project isolation: StructuredIndexStore holds one index per project_id
  - Raises KeyError (not None) on miss so callers can handle explicitly
  - Thread-safe reads (writes happen only during ingestion, single-threaded)
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.models.project_models import AOIRecord, IORecord, RoutineRecord, TagRecord

logger = logging.getLogger(__name__)


def _key(name: str) -> str:
    """Normalise lookup key: uppercase + strip whitespace."""
    return name.strip().upper()


# ── Sub-indexes ───────────────────────────────────────────────────────────────

class TagIndex:
    """Fast O(1) tag lookup by name (case-insensitive)."""

    def __init__(self):
        self._store: Dict[str, TagRecord] = {}

    def add(self, record: TagRecord) -> None:
        self._store[_key(record.name)] = record

    def add_batch(self, records: List[TagRecord]) -> None:
        for r in records:
            self.add(r)

    def get(self, name: str) -> TagRecord:
        k = _key(name)
        if k not in self._store:
            raise KeyError(f"Tag not found in structured index: '{name}'")
        return self._store[k]

    def has(self, name: str) -> bool:
        return _key(name) in self._store

    def all_names(self) -> List[str]:
        return list(self._store.keys())

    def count(self) -> int:
        return len(self._store)

    def search(self, partial: str, limit: int = 10) -> List[TagRecord]:
        """Partial substring match (case-insensitive)."""
        needle = partial.upper()
        return [v for k, v in self._store.items() if needle in k][:limit]


class RoutineIndex:
    """Fast O(1) routine lookup by name."""

    def __init__(self):
        self._store: Dict[str, RoutineRecord] = {}

    def add(self, record: RoutineRecord) -> None:
        # Key: PROGRAM.ROUTINE or just ROUTINE if unique
        k = _key(f"{record.program_name}.{record.name}")
        self._store[k] = record
        # Also index by routine name alone (for simple queries)
        self._store.setdefault(_key(record.name), record)

    def add_batch(self, records: List[RoutineRecord]) -> None:
        for r in records:
            self.add(r)

    def get(self, name: str) -> RoutineRecord:
        k = _key(name)
        if k not in self._store:
            raise KeyError(f"Routine not found: '{name}'")
        return self._store[k]

    def has(self, name: str) -> bool:
        return _key(name) in self._store

    def all_names(self) -> List[str]:
        return list(self._store.keys())

    def count(self) -> int:
        return len({v.name for v in self._store.values()})


class AOIIndex:
    """Fast O(1) Add-On Instruction lookup."""

    def __init__(self):
        self._store: Dict[str, AOIRecord] = {}

    def add(self, record: AOIRecord) -> None:
        self._store[_key(record.name)] = record

    def add_batch(self, records: List[AOIRecord]) -> None:
        for r in records:
            self.add(r)

    def get(self, name: str) -> AOIRecord:
        k = _key(name)
        if k not in self._store:
            raise KeyError(f"AOI not found: '{name}'")
        return self._store[k]

    def has(self, name: str) -> bool:
        return _key(name) in self._store

    def count(self) -> int:
        return len(self._store)


class IOIndex:
    """Fast O(1) IO record lookup by slot key."""

    def __init__(self):
        self._by_slot: Dict[str, IORecord] = {}
        self._by_tag: Dict[str, IORecord] = {}

    def add(self, record: IORecord) -> None:
        slot_k = _key(record.slot)
        self._by_slot[slot_k] = record
        if record.tag_name:
            self._by_tag[_key(record.tag_name)] = record

    def add_batch(self, records: List[IORecord]) -> None:
        for r in records:
            self.add(r)

    def get_by_slot(self, slot: str) -> IORecord:
        k = _key(slot)
        if k not in self._by_slot:
            raise KeyError(f"IO slot not found: '{slot}'")
        return self._by_slot[k]

    def get_by_tag(self, tag_name: str) -> IORecord:
        k = _key(tag_name)
        if k not in self._by_tag:
            raise KeyError(f"IO tag not found: '{tag_name}'")
        return self._by_tag[k]

    def has_slot(self, slot: str) -> bool:
        return _key(slot) in self._by_slot

    def has_tag(self, tag_name: str) -> bool:
        return _key(tag_name) in self._by_tag

    def count(self) -> int:
        return len(self._by_slot)


# ── Per-project composite index ───────────────────────────────────────────────

class ProjectStructuredIndex:
    """
    Aggregates TagIndex, RoutineIndex, AOIIndex, IOIndex for a single project.
    All public lookup methods are the canonical API used by query_orchestrator.
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.tags = TagIndex()
        self.routines = RoutineIndex()
        self.aois = AOIIndex()
        self.io = IOIndex()

    # ── Convenience wrappers used by orchestrator ─────────────────────────────

    def get_tag(self, tag_name: str) -> Optional[TagRecord]:
        """Return TagRecord or None."""
        try:
            return self.tags.get(tag_name)
        except KeyError:
            return None

    def get_routine(self, routine_name: str) -> Optional[RoutineRecord]:
        try:
            return self.routines.get(routine_name)
        except KeyError:
            return None

    def get_io(self, slot: str) -> Optional[IORecord]:
        try:
            return self.io.get_by_slot(slot)
        except KeyError:
            return None

    def has_tag(self, tag_name: str) -> bool:
        return self.tags.has(tag_name)

    def all_tag_names(self) -> List[str]:
        return self.tags.all_names()

    def search_tags(self, partial: str, limit: int = 10) -> List[TagRecord]:
        return self.tags.search(partial, limit)

    def stats(self) -> dict:
        return {
            "tags": self.tags.count(),
            "routines": self.routines.count(),
            "aois": self.aois.count(),
            "io_rows": self.io.count(),
        }


# ── Global store (module-level singleton) ─────────────────────────────────────

class StructuredIndexStore:
    """Thread-safe store holding one ProjectStructuredIndex per project_id."""

    def __init__(self):
        self._indexes: Dict[str, ProjectStructuredIndex] = {}

    def get_or_create(self, project_id: str) -> ProjectStructuredIndex:
        if project_id not in self._indexes:
            self._indexes[project_id] = ProjectStructuredIndex(project_id)
        return self._indexes[project_id]

    def get(self, project_id: str) -> Optional[ProjectStructuredIndex]:
        return self._indexes.get(project_id)

    def reset(self, project_id: str) -> None:
        self._indexes.pop(project_id, None)

    def reset_all(self) -> None:
        self._indexes.clear()


_store = StructuredIndexStore()


def get_structured_store() -> StructuredIndexStore:
    return _store
