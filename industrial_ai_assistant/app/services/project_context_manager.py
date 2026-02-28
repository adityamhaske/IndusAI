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
import os
import threading
from dataclasses import dataclass
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

# ── Environment detection ──────────────────────────────────────────────────────
# Running inside Docker container?
IS_DOCKER: bool = os.path.exists("/.dockerenv")

# Security: only allow ingestion within home directory tree
# Override by setting INDUSAI_ALLOWED_ROOT env var
_env_root = os.environ.get("INDUSAI_ALLOWED_ROOT", "")
ALLOWED_ROOT: Path = Path(_env_root).resolve() if _env_root else Path.home()


@dataclass
class PathDiagnostic:
    """Returned by validate_folder_path() — full diagnostic context."""
    provided_path: str
    resolved_path: str
    cwd: str
    container_mode: bool
    allowed_root: str
    effective_uid: int
    ok: bool
    error_code: str = ""
    message: str = ""


def normalize_path(raw_path: str) -> Path:
    """
    Safely normalise any user-supplied folder path.

    Order of operations (critical):
      1. Strip surrounding whitespace and quotes (prevents CWD-prepend bug)
      2. Expand ~ to home directory
      3. If absolute → resolve directly (NEVER prepend CWD)
      4. If relative → resolve relative to CWD
    """
    # Step 1: strip quotes — the root cause of "CWD prepended" bug
    clean = raw_path.strip().strip('"').strip("'").strip()
    # Step 2: expand ~
    raw = Path(clean).expanduser()
    # Step 3: absolute vs relative (NEVER join CWD with an absolute path)
    if raw.is_absolute():
        return raw.resolve()
    return (Path.cwd() / raw).resolve()


def validate_folder_path(raw_path: str) -> PathDiagnostic:
    """
    Resolve and validate the folder path robustly.
    Returns PathDiagnostic(ok=True) when valid, or ok=False + error info.
    Never raises.
    """
    cwd = os.getcwd()
    uid = os.getuid() if hasattr(os, 'getuid') else -1
    clean = raw_path.strip().strip('"').strip("'").strip()

    try:
        path = normalize_path(raw_path)
    except Exception as exc:
        return PathDiagnostic(
            provided_path=raw_path, resolved_path="ERROR",
            cwd=cwd, container_mode=IS_DOCKER,
            allowed_root=str(ALLOWED_ROOT), effective_uid=uid,
            ok=False, error_code="PATH_RESOLUTION_FAILED",
            message=f"Could not resolve path: {exc}",
        )

    resolved = str(path)
    is_abs = Path(clean).expanduser().is_absolute()

    logger.info(
        "[path-validate] provided=%r clean=%r resolved=%r is_absolute=%s cwd=%r docker=%s uid=%s",
        raw_path, clean, resolved, is_abs, cwd, IS_DOCKER, uid,
    )

    if not path.exists():
        return PathDiagnostic(
            provided_path=raw_path, resolved_path=resolved,
            cwd=cwd, container_mode=IS_DOCKER,
            allowed_root=str(ALLOWED_ROOT), effective_uid=uid,
            ok=False, error_code="PATH_NOT_FOUND",
            message=(
                f"Path does not exist: {resolved!r}"
                + (" — backend is running inside a Docker container; "
                   "ensure the host path is mounted into the container."
                   if IS_DOCKER else "")
            ),
        )

    if not path.is_dir():
        return PathDiagnostic(
            provided_path=raw_path, resolved_path=resolved,
            cwd=cwd, container_mode=IS_DOCKER,
            allowed_root=str(ALLOWED_ROOT), effective_uid=uid,
            ok=False, error_code="NOT_A_DIRECTORY",
            message=f"{resolved!r} exists but is a file, not a directory.",
        )

    # Security: must be within ALLOWED_ROOT
    try:
        path.relative_to(ALLOWED_ROOT)
    except ValueError:
        return PathDiagnostic(
            provided_path=raw_path, resolved_path=resolved,
            cwd=cwd, container_mode=IS_DOCKER,
            allowed_root=str(ALLOWED_ROOT), effective_uid=uid,
            ok=False, error_code="OUTSIDE_ALLOWED_ROOT",
            message=(
                f"Security policy: {resolved!r} is outside the allowed root "
                f"{str(ALLOWED_ROOT)!r}. "
                f"Set INDUSAI_ALLOWED_ROOT env var to override."
            ),
        )

    return PathDiagnostic(
        provided_path=raw_path, resolved_path=resolved,
        cwd=cwd, container_mode=IS_DOCKER,
        allowed_root=str(ALLOWED_ROOT), effective_uid=uid,
        ok=True,
    )



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
        
        # Load persisted config
        self._config_file = Path.home() / ".indusai" / "active_projects.json"
        self._load_persisted_projects()

    def _load_persisted_projects(self) -> None:
        """Hydrate project states based on global mapping cache."""
        import json
        from app.models.project_models import IndexMetadata
        from app.indexes.structured_index import get_structured_index
        from app.indexes.semantic_index import get_semantic_index

        if not self._config_file.exists():
            return
            
        try:
            with open(self._config_file, "r") as f:
                mappings = json.load(f)
                
            for pid, pfolder in mappings.items():
                meta_path = Path(pfolder) / ".indusai_index.json"
                if meta_path.exists():
                    try:
                        with open(meta_path, "r", encoding="utf-8") as mf:
                            meta = IndexMetadata.model_validate_json(mf.read())
                            
                        # Validate Qdrant semantic integrity
                        sem = get_semantic_index()
                        if sem.collection_size(pid) > 0:
                            # Load ram structure
                            si = get_structured_index(pid)
                            if si.load_from_disk(pfolder):
                                # Reconstruct memory
                                state = self._get_state(pid)
                                state.folder = pfolder
                                state.project_hash = meta.project_hash
                                state.index_state = IndexState.READY
                                
                                import time
                                from app.models.project_models import IngestionResult
                                state.last_result = IngestionResult(
                                    project_id=pid,
                                    project_hash=meta.project_hash,
                                    folder=pfolder,
                                    files_indexed=len(meta.files),
                                    duration_ms=0.0
                                )
                                logger.info("[%s] Successfully reconstructed project mapping from cache natively.", pid)
                    except Exception as me:
                        logger.warning("Metadata reconstruction failed for %s: %s", pid, me)
        except Exception as e:
            logger.warning("Could not read project config mapping: %s", e)

    def _save_persisted_projects(self) -> None:
        import json
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        mappings = {pid: state.folder for pid, state in self._states.items() if state.folder}
        try:
            with open(self._config_file, "w") as f:
                json.dump(mappings, f, indent=2)
        except Exception as e:
            logger.error("Failed to save project mapping cache: %s", e)

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
        Uses validate_folder_path() for robust resolution — never stores raw user string.
        Raises ValueError with structured diagnostic JSON string on failure.
        """
        diag = validate_folder_path(folder_path)
        if not diag.ok:
            import json
            raise ValueError(json.dumps({
                "error": diag.error_code,
                "provided_path": diag.provided_path,
                "resolved_path": diag.resolved_path,
                "cwd": diag.cwd,
                "container_mode": diag.container_mode,
                "allowed_root": diag.allowed_root,
                "message": diag.message,
            }))

        path = Path(diag.resolved_path)
        state = self._get_state(project_id)
        new_hash = _compute_project_hash(path)

        with state.lock:
            state.folder = diag.resolved_path   # always store resolved, not raw
            if state.index_state == IndexState.READY and state.project_hash != new_hash:
                logger.warning(
                    "[%s] Project hash changed (%s→%s). Marking STALE.",
                    project_id, state.project_hash[:8], new_hash[:8],
                )
                state.index_state = IndexState.STALE
            state.project_hash = new_hash

        logger.info(
            "[%s] Project set: resolved=%r hash=%s docker=%s",
            project_id, diag.resolved_path, new_hash[:8], IS_DOCKER,
        )
        self._save_persisted_projects()
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
