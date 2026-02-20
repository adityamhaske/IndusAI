"""
ProjectContextManager — tracks project ingestion state per project_id.

State machine:
  UNLOADED → INDEXING (lock acquired) → READY
  READY    → STALE    (hash mismatch)  → INDEXING → READY

Content-based hashing:
  SHA-256 of first 64KB of each file (sorted by path).
  Files < 1MB are fully hashed.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.core.project_exceptions import (
    ProjectNotFoundError,
    ProjectNotReadyError,
    ProjectStaleError,
)
from app.models.project_models import IndexState, IngestionResult, ProjectStatus

logger = logging.getLogger(__name__)

_FULL_HASH_LIMIT = 1 * 1024 * 1024   # 1 MB
_SAMPLE_BYTES    = 64 * 1024          # 64 KB sample for large files

# Extensions excluded from hashing (binaries, generated)
_SKIP_EXTENSIONS = {
    ".exe", ".dll", ".pdb", ".obj", ".bin", ".pyc", ".so",
    ".zip", ".tar", ".gz", ".rar", ".7z", ".db", ".sqlite",
}


class _ProjectState:
    __slots__ = (
        "project_id", "folder", "project_hash", "index_state",
        "last_result", "last_index_time", "lock",
    )

    def __init__(self, project_id: str):
        self.project_id   = project_id
        self.folder       = ""
        self.project_hash = ""
        self.index_state  = IndexState.UNLOADED
        self.last_result: IngestionResult | None = None
        self.last_index_time: datetime | None = None
        self.lock = threading.Lock()


class ProjectContextManager:
    """Thread-safe manager for project ingestion state."""

    def __init__(self):
        self._states: dict[str, _ProjectState] = {}
        self._global_lock = threading.Lock()

    # ── State access ──────────────────────────────────────────────────────────

    def _get_state(self, project_id: str) -> _ProjectState:
        with self._global_lock:
            if project_id not in self._states:
                self._states[project_id] = _ProjectState(project_id)
            return self._states[project_id]

    # ── Public API ────────────────────────────────────────────────────────────

    def set_project(self, folder_path: str, project_id: str) -> ProjectStatus:
        """
        Register a folder for a project.
        Computes content-based hash and marks previous index as STALE
        if the hash differs.
        """
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            raise ValueError(f"Folder does not exist or is not a directory: {folder_path}")

        state = self._get_state(project_id)
        new_hash = _compute_project_hash(folder)

        with state.lock:
            state.folder = str(folder)
            if state.index_state == IndexState.READY and state.project_hash != new_hash:
                logger.warning(
                    "[%s] Project hash changed (%s→%s). Marking STALE.",
                    project_id, state.project_hash[:8], new_hash[:8],
                )
                state.index_state = IndexState.STALE
            state.project_hash = new_hash

        return self.get_status(project_id)

    def mark_indexing(self, project_id: str) -> None:
        state = self._get_state(project_id)
        with state.lock:
            state.index_state = IndexState.INDEXING

    def mark_ready(self, project_id: str, result: IngestionResult) -> None:
        state = self._get_state(project_id)
        with state.lock:
            state.index_state    = IndexState.READY
            state.last_result    = result
            state.last_index_time = datetime.now(timezone.utc)

    def mark_failed(self, project_id: str, error: str) -> None:
        state = self._get_state(project_id)
        with state.lock:
            state.index_state = IndexState.FAILED
            if state.last_result:
                state.last_result.errors.append(error)

    def mark_stale(self, project_id: str) -> None:
        state = self._get_state(project_id)
        with state.lock:
            if state.index_state == IndexState.READY:
                state.index_state = IndexState.STALE

    # ── Guard ─────────────────────────────────────────────────────────────────

    def require_ready(self, project_id: str) -> None:
        """
        Raise appropriate exception if project is not ready for queries.
        Call this as the first step of any query pipeline.
        """
        if project_id not in self._states:
            raise ProjectNotFoundError(project_id)
        state = self._states[project_id]
        if state.index_state == IndexState.STALE:
            raise ProjectStaleError(project_id)
        if state.index_state != IndexState.READY:
            raise ProjectNotReadyError(project_id)

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self, project_id: str) -> ProjectStatus:
        if project_id not in self._states:
            return ProjectStatus(project_id=project_id, project_loaded=False)

        state = self._states[project_id]
        result = state.last_result

        # Pull memory footprint from structured index
        from app.indexes.structured_index import get_structured_index
        si = get_structured_index(project_id)
        si_stats = si.stats()

        return ProjectStatus(
            project_id=project_id,
            project_loaded=(state.index_state == IndexState.READY),
            folder=state.folder,
            project_hash=state.project_hash,
            index_state=state.index_state,
            files_indexed=result.files_indexed if result else 0,
            tags_indexed=si_stats.tags,
            routines_indexed=si_stats.routines,
            aois_indexed=si_stats.aois,
            io_rows_indexed=si_stats.io_rows,
            semantic_chunks=0,   # caller can populate from SemanticIndex
            memory_footprint_mb=si_stats.memory_footprint_mb,
            last_index_time=state.last_index_time,
            ingestion_duration_ms=result.duration_ms if result else 0.0,
            errors=result.errors if result else [],
            warnings=(result.warnings if result else []) + si_stats.warnings,
        )

    def reset(self, project_id: str) -> None:
        state = self._get_state(project_id)
        with state.lock:
            state.index_state  = IndexState.UNLOADED
            state.project_hash = ""
            state.last_result  = None
            state.last_index_time = None
        logger.info("[%s] ProjectContextManager reset.", project_id)


# ── Content-based hashing ──────────────────────────────────────────────────────

def _compute_project_hash(folder: Path) -> str:
    """
    SHA-256 fingerprint of project folder contents.
    - Files < 1MB: full content hash
    - Files >= 1MB: first 64KB sampled
    - Sorted by relative path for determinism
    - Binary/generated files skipped
    """
    h = hashlib.sha256()
    try:
        all_files = sorted(
            f for f in folder.rglob("*")
            if f.is_file() and f.suffix.lower() not in _SKIP_EXTENSIONS
            and not any(p in f.parts for p in ("venv", "__pycache__", ".git", "node_modules"))
        )
    except PermissionError as exc:
        logger.warning("Permission error walking folder: %s", exc)
        return hashlib.sha256(str(folder).encode()).hexdigest()

    for file_path in all_files:
        try:
            rel = str(file_path.relative_to(folder))
            h.update(rel.encode())           # include path in hash
            size = file_path.stat().st_size
            if size <= _FULL_HASH_LIMIT:
                h.update(file_path.read_bytes())
            else:
                with open(file_path, "rb") as f:
                    h.update(f.read(_SAMPLE_BYTES))
                h.update(str(size).encode())  # include size as proxy for rest
        except (OSError, PermissionError):
            continue

    return h.hexdigest()


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: ProjectContextManager | None = None
_singleton_lock = threading.Lock()


def get_project_context_manager() -> ProjectContextManager:
    global _instance
    if _instance is None:
        with _singleton_lock:
            if _instance is None:
                _instance = ProjectContextManager()
    return _instance
