"""
ProjectContextManager — Manages project state, hashing, and readiness.

Design:
  - Per-project singleton via _registry
  - Content-based hashing: SHA-256 of file contents for <5MB, sampling for larger
  - Detects stale index when project_hash changes after ingestion
  - Thread-safe state via RLock
"""
import hashlib
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from app.core.project_exceptions import (
    ProjectIndexStaleError,
    ProjectNotFoundError,
    ProjectNotReadyError,
)
from app.models.project_models import IngestionResult, ProjectStatus

logger = logging.getLogger(__name__)

_LARGE_FILE_THRESHOLD = 5 * 1024 * 1024   # 5 MB
_SAMPLE_SIZE = 64 * 1024                   # 64 KB per sample


def _content_fingerprint(path: Path) -> str:
    """
    SHA-256 content fingerprint.
    Small files (<5MB): full content hash.
    Large files: sample first + middle + last 64KB.
    """
    size = path.stat().st_size
    hasher = hashlib.sha256()
    if size < _LARGE_FILE_THRESHOLD:
        hasher.update(path.read_bytes())
    else:
        with open(path, "rb") as f:
            hasher.update(f.read(_SAMPLE_SIZE))                # first
            f.seek(max(0, size // 2 - _SAMPLE_SIZE // 2))
            hasher.update(f.read(_SAMPLE_SIZE))                # middle
            f.seek(max(0, size - _SAMPLE_SIZE))
            hasher.update(f.read(_SAMPLE_SIZE))                # last
        hasher.update(str(size).encode())
    return hasher.hexdigest()


def compute_project_hash(folder: Path) -> tuple[str, int]:
    """
    Compute a deterministic fingerprint for the project folder.
    Returns (hash_str, file_count).
    """
    fingerprints = []
    count = 0
    for p in sorted(folder.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(folder))
        # Skip ignored paths
        if any(part in rel for part in ("__pycache__", ".git", "node_modules", "venv", ".venv")):
            continue
        try:
            fingerprints.append(f"{rel}:{_content_fingerprint(p)}")
            count += 1
        except Exception as exc:
            logger.debug("Hash skip %s: %s", p, exc)

    combined = "\n".join(fingerprints) + f"\ncount:{count}"
    return hashlib.sha256(combined.encode()).hexdigest(), count


class _ProjectState:
    """Internal state for one project."""

    def __init__(self, project_id: str, folder: str):
        self.project_id = project_id
        self.folder = folder
        self.project_hash = ""
        self.indexed_hash = ""       # hash at time of last successful ingestion
        self.file_count = 0
        self.is_ready = False
        self.ingestion_running = False
        self.last_result: Optional[IngestionResult] = None
        self.last_index_time: Optional[datetime] = None
        self._lock = threading.RLock()

    @property
    def index_stale(self) -> bool:
        return self.is_ready and self.project_hash != self.indexed_hash


class ProjectContextManager:
    """
    Manages project metadata and readiness state.
    Thread-safe per project.
    """

    def __init__(self):
        self._projects: Dict[str, _ProjectState] = {}
        self._registry_lock = threading.Lock()

    def _get_or_create(self, project_id: str, folder: str) -> _ProjectState:
        with self._registry_lock:
            if project_id not in self._projects:
                self._projects[project_id] = _ProjectState(project_id, folder)
            return self._projects[project_id]

    def set_project(self, folder_path: str, project_id: str) -> tuple[str, int]:
        """
        Register a project folder. Computes content-based project_hash.
        Returns (project_hash, file_count).
        Raises FileNotFoundError if folder doesn't exist.
        """
        folder = Path(folder_path)
        if not folder.is_dir():
            raise FileNotFoundError(f"Project folder not found: {folder_path}")

        state = self._get_or_create(project_id, folder_path)
        with state._lock:
            state.folder = folder_path
            ph, fc = compute_project_hash(folder)
            state.project_hash = ph
            state.file_count = fc
            logger.info(
                "Project '%s' registered: folder=%s hash=%s files=%d",
                project_id, folder_path, ph[:8], fc,
            )
        return ph, fc

    def mark_ingested(self, project_id: str, result: IngestionResult) -> None:
        """Called by pipeline after successful ingestion."""
        state = self._projects.get(project_id)
        if state is None:
            return
        with state._lock:
            state.indexed_hash = state.project_hash
            state.is_ready = True
            state.last_result = result
            state.last_index_time = datetime.now(timezone.utc)

    def require_ready(self, project_id: str) -> None:
        """
        Raise if project is not ready or index is stale.
        Must be called at the start of every query.
        """
        state = self._projects.get(project_id)
        if state is None or not state.is_ready:
            raise ProjectNotReadyError()
        if state.index_stale:
            raise ProjectIndexStaleError(project_id)

    def get_status(self, project_id: str) -> ProjectStatus:
        from app.indexes.structured_index import get_structured_index
        from app.indexes.semantic_index import get_semantic_index

        state = self._projects.get(project_id)
        if state is None:
            return ProjectStatus(project_id=project_id)

        si_stats = get_structured_index(project_id).stats()
        sem_idx = get_semantic_index()

        warnings = list(si_stats.get("warnings", []))
        if si_stats.get("memory_mb", 0) > 200:
            warnings.append(f"StructuredIndex memory {si_stats['memory_mb']:.1f} MB — consider splitting large projects.")

        with state._lock:
            result = state.last_result
            return ProjectStatus(
                project_id=project_id,
                project_loaded=state.is_ready,
                folder=state.folder,
                project_hash=state.project_hash,
                index_stale=state.index_stale,
                files_indexed=result.files_indexed if result else 0,
                tags_indexed=si_stats["tags"],
                routines_indexed=si_stats["routines"],
                aois_indexed=si_stats["aois"],
                io_rows_indexed=si_stats["ios"],
                semantic_chunks=sem_idx.chunk_count(project_id),
                memory_mb=si_stats["memory_mb"],
                last_index_time=state.last_index_time,
                ingestion_running=state.ingestion_running,
                warnings=warnings,
                errors=result.errors if result else [],
            )

    def get_metrics(self, project_id: str) -> dict:
        from app.indexes.structured_index import get_structured_index
        from app.indexes.semantic_index import get_semantic_index

        state = self._projects.get(project_id)
        si = get_structured_index(project_id).stats()
        sem = get_semantic_index()
        return {
            "project_id": project_id,
            "structured_memory_mb": si["memory_mb"],
            "tags": si["tags"],
            "routines": si["routines"],
            "aois": si["aois"],
            "io_rows": si["ios"],
            "semantic_chunk_count": sem.chunk_count(project_id),
            "ingestion_duration_s": state.last_result.duration_s if state and state.last_result else 0,
        }

    def reset(self, project_id: str) -> None:
        """Purge all state for a project."""
        from app.indexes.structured_index import delete_structured_index
        from app.indexes.semantic_index import get_semantic_index

        delete_structured_index(project_id)
        get_semantic_index().delete_project(project_id)

        with self._registry_lock:
            self._projects.pop(project_id, None)
        logger.info("Project '%s' reset complete.", project_id)


# ── Singleton ─────────────────────────────────────────────────────────────────
_ctx_manager: Optional[ProjectContextManager] = None


def get_project_context_manager() -> ProjectContextManager:
    global _ctx_manager
    if _ctx_manager is None:
        _ctx_manager = ProjectContextManager()
    return _ctx_manager
