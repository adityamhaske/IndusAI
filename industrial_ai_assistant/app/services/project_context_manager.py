"""
ProjectContextManager — singleton store tracking ingestion state per project.

Responsibilities:
  - Register a project folder (set_project)
  - Compute a project_hash from mtime of the folder tree
  - Track ingestion status (PENDING → RUNNING → COMPLETE | FAILED)
  - Enforce project readiness gate: raise ProjectNotReadyError if not COMPLETE
  - Expose status for GET /api/project/status
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.core.project_exceptions import ProjectNotReadyError
from app.models.project_models import IngestionStatus, ProjectStatusResponse

logger = logging.getLogger(__name__)


def _compute_folder_hash(folder_path: str) -> str:
    """
    SHA-256 of the sorted (path, mtime) pairs in a folder tree.
    Cheap enough to run at ingest time; not called on every query.
    """
    parts = []
    for root, dirs, files in os.walk(folder_path):
        dirs.sort()
        for f in sorted(files):
            fp = os.path.join(root, f)
            try:
                mtime = os.path.getmtime(fp)
                parts.append(f"{fp}:{mtime:.0f}")
            except OSError:
                pass
    digest = hashlib.sha256("\n".join(parts).encode()).hexdigest()
    return digest[:16]


class _ProjectState:
    """Internal state for one project."""

    def __init__(self, project_id: str, folder_path: str):
        self.project_id = project_id
        self.folder = folder_path
        self.project_hash = _compute_folder_hash(folder_path)
        self.status = IngestionStatus.PENDING
        self.last_index_time: Optional[datetime] = None
        self.errors: List[str] = []
        # Metrics (populated by pipeline)
        self.files_indexed = 0
        self.tags_indexed = 0
        self.routines_indexed = 0
        self.aois_indexed = 0
        self.io_rows_indexed = 0
        self.semantic_chunks = 0


class ProjectContextManager:
    """
    Module-level singleton (get_project_context_manager()) holding per-project state.
    """

    def __init__(self):
        self._projects: Dict[str, _ProjectState] = {}

    # ── Project lifecycle ─────────────────────────────────────────────────────

    def set_project(self, project_id: str, folder_path: str) -> str:
        """
        Register / re-register a project folder.
        Resets status to PENDING so a new ingestion run is required.

        Returns the computed project_hash.
        """
        if not os.path.isdir(folder_path):
            raise FileNotFoundError(
                f"Project folder does not exist: {folder_path}"
            )
        state = _ProjectState(project_id, folder_path)
        self._projects[project_id] = state
        logger.info(
            "ProjectContextManager: set project=%s folder=%s hash=%s",
            project_id, folder_path, state.project_hash,
        )
        return state.project_hash

    def mark_running(self, project_id: str) -> None:
        self._require(project_id).status = IngestionStatus.RUNNING

    def mark_complete(self, project_id: str, metrics: dict) -> None:
        state = self._require(project_id)
        state.status = IngestionStatus.COMPLETE
        state.last_index_time = datetime.now(timezone.utc)
        state.files_indexed = metrics.get("files_indexed", 0)
        state.tags_indexed = metrics.get("tags_indexed", 0)
        state.routines_indexed = metrics.get("routines_indexed", 0)
        state.aois_indexed = metrics.get("aois_indexed", 0)
        state.io_rows_indexed = metrics.get("io_rows_indexed", 0)
        state.semantic_chunks = metrics.get("semantic_chunks", 0)
        logger.info("ProjectContextManager: project=%s COMPLETE %s", project_id, metrics)

    def mark_failed(self, project_id: str, error: str) -> None:
        state = self._require(project_id)
        state.status = IngestionStatus.FAILED
        state.errors.append(error)
        logger.error("ProjectContextManager: project=%s FAILED: %s", project_id, error)

    def add_error(self, project_id: str, error: str) -> None:
        state = self._projects.get(project_id)
        if state:
            state.errors.append(error)

    # ── Query gate ────────────────────────────────────────────────────────────

    def is_ready(self, project_id: str) -> bool:
        state = self._projects.get(project_id)
        return state is not None and state.status == IngestionStatus.COMPLETE

    def require_ready(self, project_id: str) -> None:
        """Raise ProjectNotReadyError if project not fully ingested."""
        if not self.is_ready(project_id):
            raise ProjectNotReadyError(project_id)

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self, project_id: str) -> ProjectStatusResponse:
        state = self._projects.get(project_id)
        if state is None:
            return ProjectStatusResponse(
                project_id=project_id,
                project_loaded=False,
                status=IngestionStatus.PENDING,
            )
        return ProjectStatusResponse(
            project_id=project_id,
            project_loaded=state.status == IngestionStatus.COMPLETE,
            folder=state.folder,
            status=state.status,
            files_indexed=state.files_indexed,
            tags_indexed=state.tags_indexed,
            routines_indexed=state.routines_indexed,
            aois_indexed=state.aois_indexed,
            io_rows_indexed=state.io_rows_indexed,
            semantic_chunks=state.semantic_chunks,
            last_index_time=state.last_index_time,
            errors=state.errors,
        )

    def reset(self, project_id: str) -> None:
        self._projects.pop(project_id, None)
        logger.info("ProjectContextManager: removed project=%s", project_id)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _require(self, project_id: str) -> _ProjectState:
        state = self._projects.get(project_id)
        if state is None:
            raise KeyError(
                f"Project '{project_id}' not registered. Call set_project() first."
            )
        return state


# ── Module-level singleton ─────────────────────────────────────────────────────
_manager: Optional[ProjectContextManager] = None


def get_project_context_manager() -> ProjectContextManager:
    global _manager
    if _manager is None:
        _manager = ProjectContextManager()
    return _manager
