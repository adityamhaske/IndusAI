"""
Project API — Phase 20 Persistent Project Architecture
Mounted at /api by main.py (prefix="/api")
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from app.config.dependency_injection import get_container, Container

logger = logging.getLogger(__name__)
router = APIRouter()


# ── GET /api/projects ──────────────────────────────────────────────────────────

@router.get("/projects", tags=["Projects"])
def list_projects(container: Container = Depends(get_container)):
    """List all registered projects with index_status."""
    return container.project_service.get_all_projects()


# ── POST /api/projects ─────────────────────────────────────────────────────────

class CreateProjectBody(BaseModel):
    project_id: str
    name: str
    root_directory: Optional[str] = None

@router.post("/projects", tags=["Projects"])
def create_project(body: CreateProjectBody, container: Container = Depends(get_container)):
    """Create or update a project record."""
    obj = container.project_service.upsert_project(
        project_id=body.project_id,
        name=body.name,
        root_directory=body.root_directory,
    )
    return {"status": "created", "id": obj.id}


# ── GET /api/projects/{id} ─────────────────────────────────────────────────────

@router.get("/projects/{project_id}", tags=["Projects"])
def get_project(project_id: str, container: Container = Depends(get_container)):
    """Full project detail including index_status and version traceability."""
    data = container.project_service.get_project(project_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    # also enrich with live context manager status
    try:
        from app.services.project_context_manager import get_project_context_manager
        ctx = get_project_context_manager()
        live_status = ctx.get_status(project_id)
        data["live_state"]  = live_status.state.value if live_status.state else "UNLOADED"
        data["project_hash"] = live_status.project_hash
        data["folder"]       = live_status.folder
        data["project_loaded"] = live_status.project_loaded
    except Exception:
        pass
    return data


# ── GET /api/projects/{id}/files ───────────────────────────────────────────────

@router.get("/projects/{project_id}/files", tags=["Projects"])
def get_project_files(project_id: str, container: Container = Depends(get_container)):
    """List all tracked files with hash, status, and embedding count."""
    return container.project_service.get_project_files(project_id)


# ── GET /api/projects/{id}/telemetry ──────────────────────────────────────────

@router.get("/projects/{project_id}/telemetry", tags=["Projects"])
def get_telemetry_datasets(project_id: str, container: Container = Depends(get_container)):
    """List all registered telemetry CSV datasets for the project — for the dropdown."""
    return container.project_service.get_telemetry_datasets(project_id)


# ── POST /api/projects/{id}/reindex-delta ─────────────────────────────────────

@router.post("/projects/{project_id}/reindex-delta", tags=["Projects"])
async def reindex_delta(
    project_id: str,
    container: Container = Depends(get_container),
):
    """
    Trigger delta reindex — only files whose SHA-256 hash has changed are reindexed.
    This is the default indexing mode (safe for production use).
    """
    try:
        from app.services.project_context_manager import get_project_context_manager
        from app.services.project_ingestion_pipeline import get_ingestion_pipeline

        ctx = get_project_context_manager()
        status = ctx.get_status(project_id)
        if not status.folder:
            raise HTTPException(
                status_code=409,
                detail=f"Project '{project_id}' has no known root folder. Run full ingest first."
            )

        container.project_service.update_index_status(project_id, "INDEXING")
        pipeline = get_ingestion_pipeline()
        result = await pipeline.ingest(status.folder, project_id)

        container.project_service.update_index_status(
            project_id, "READY",
            last_indexed_at=__import__("datetime").datetime.utcnow(),
            index_version=result.project_hash,
        )
        return {
            "status": "delta_complete",
            "files_indexed": result.files_indexed,
            "files_skipped": result.files_scanned - result.files_indexed,
            "semantic_chunks": result.semantic_chunks_indexed,
            "warnings": result.warnings,
        }
    except HTTPException:
        raise
    except Exception as exc:
        container.project_service.update_index_status(project_id, "OUTDATED")
        logger.exception("Delta reindex failed for %s", project_id)
        raise HTTPException(status_code=500, detail=str(exc))


# ── POST /api/projects/{id}/rebuild ───────────────────────────────────────────

@router.post("/projects/{project_id}/rebuild", tags=["Projects"])
async def rebuild_full(
    project_id: str,
    container: Container = Depends(get_container),
):
    """
    Force a full rebuild — wipes existing embeddings and reindexes all files.
    Use only when explicitly requested. Delta reindex is preferred.
    """
    try:
        from app.services.project_context_manager import get_project_context_manager
        from app.services.project_ingestion_pipeline import get_ingestion_pipeline
        from app.indexes.structured_index import clear_structured_index
        from app.indexes.semantic_index import get_semantic_index
        from pathlib import Path

        ctx = get_project_context_manager()
        status = ctx.get_status(project_id)
        if not status.folder:
            raise HTTPException(status_code=409, detail="No folder registered for this project.")

        # Wipe metadata file to force full reindex
        meta_path = Path(status.folder) / ".indusai_index.json"
        if meta_path.exists():
            meta_path.unlink()

        clear_structured_index(project_id)
        get_semantic_index().delete_project(project_id)
        container.project_service.update_index_status(project_id, "INDEXING")

        pipeline = get_ingestion_pipeline()
        result = await pipeline.ingest(status.folder, project_id)

        container.project_service.update_index_status(
            project_id, "READY",
            last_indexed_at=__import__("datetime").datetime.utcnow(),
            index_version=result.project_hash,
        )
        return {
            "status": "rebuild_complete",
            "files_indexed": result.files_indexed,
            "semantic_chunks": result.semantic_chunks_indexed,
            "warnings": result.warnings,
        }
    except HTTPException:
        raise
    except Exception as exc:
        container.project_service.update_index_status(project_id, "OUTDATED")
        logger.exception("Full rebuild failed for %s", project_id)
        raise HTTPException(status_code=500, detail=str(exc))


# ── DELETE /api/projects/{id} ─────────────────────────────────────────────────

@router.delete("/projects/{project_id}", tags=["Projects"])
def delete_project(project_id: str, container: Container = Depends(get_container)):
    """
    Permanently delete a project and all associated data:
    - SQLite records (project, files, telemetry datasets)
    - Qdrant vectors for this project
    - Fault dataset cache
    - Context manager state
    """
    if project_id == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default project.")

    # 1. Delete vectors from Qdrant
    try:
        from app.indexes.structured_index import clear_structured_index
        from app.indexes.semantic_index import get_semantic_index
        clear_structured_index(project_id)
        get_semantic_index().delete_project(project_id)
    except Exception as e:
        logger.warning("Could not clear vectors for project %s: %s", project_id, e)

    # 2. Clear fault dataset cache
    try:
        from app.services.fault_service import get_fault_service
        get_fault_service().reset(project_id)
    except Exception as e:
        logger.warning("Could not clear fault cache for project %s: %s", project_id, e)

    # 3. Clear context manager state
    try:
        from app.services.project_context_manager import get_project_context_manager
        ctx = get_project_context_manager()
        ctx.unload(project_id)
    except Exception as e:
        logger.warning("Could not unload context for project %s: %s", project_id, e)

    # 4. Delete from SQLite (project + files + telemetry)
    deleted = container.project_service.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    logger.info("Project %s fully deleted.", project_id)
    return {"status": "deleted", "project_id": project_id}

