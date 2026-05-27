"""
Project Knowledge Engine API routes.

Endpoints:
  POST   /api/project/ingest   — Start ingestion (async)
  GET    /api/project/status   — Full status + memory footprint
  POST   /api/project/query    — 9-step orchestrated Q&A
  GET    /api/project/metrics  — Observability metrics
  DELETE /api/project/reset    — Clear indexes for project
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.firebase_auth import AuthenticatedUser, get_current_user

from app.core.project_exceptions import (
    HallucinatedTagError,
    IngestionLockError,
    ProjectNotFoundError,
    ProjectNotReadyError,
    ProjectStaleError,
)
from app.models.project_models import (
    IngestionResult,
    ProjectMetrics,
    ProjectQueryRequest,
    ProjectQueryResponse,
    ProjectStatus,
)
from app.services.project_ingestion_pipeline import get_ingestion_pipeline
from app.services.query_orchestrator import get_query_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/project", tags=["Project Knowledge"])


# ── Request models ─────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    folder_path: str
    project_id: str = "default"


# ── POST /api/project/ingest ──────────────────────────────────────────────────

@router.post("/ingest", response_model=IngestionResult)
async def ingest_project(
    body: IngestRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Walk the folder, classify files, and populate StructuredIndex + SemanticIndex.
    Returns IngestionResult with counts and any errors.
    409 if ingestion is already running for this project.
    """
    try:
        pipeline = get_ingestion_pipeline()
        result = await pipeline.ingest([body.folder_path], body.project_id, user.uid)
        return result
    except IngestionLockError as exc:
        return JSONResponse(
            status_code=409,
            content={"error_type": exc.error_type, "message": exc.message},
        )
    except ValueError as exc:
        # ValueError from set_project carries a JSON-encoded PathDiagnostic
        import json
        raw = str(exc)
        try:
            diag = json.loads(raw)
            error_code = diag.get("error", "INVALID_FOLDER")
        except (json.JSONDecodeError, Exception):
            diag = {"message": raw}
            error_code = "INVALID_FOLDER"


        return JSONResponse(
            status_code=400,
            content={"error": error_code, **diag},
        )
    except Exception as exc:
        logger.exception("Ingestion failed for project=%s", body.project_id)
        return JSONResponse(
            status_code=500,
            content={"error_type": "INGESTION_FAILED", "message": str(exc)},
        )


# ── GET /api/project/status ───────────────────────────────────────────────────

@router.get("/status", response_model=ProjectStatus)
def project_status(
    project_id: str = Query(default="default"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Return project index status from database + index stats.
    """
    from app.indexes.semantic_index import get_semantic_index
    from app.indexes.structured_index import get_structured_index
    from app.config.dependency_injection import get_container

    ps = get_container()._project_service
    project = ps.get_project(user.uid, project_id)

    sem = get_semantic_index()
    si = get_structured_index(project_id)
    si_stats = si.stats()

    chunk_count = 0
    try:
        chunk_count = sem.collection_size(project_id)
    except Exception:
        pass

    state = "UNLOADED"
    if project:
        state = project.get("index_status", "UNLOADED")
    elif chunk_count > 0:
        state = "READY"

    # Map database telemetry file if registered
    datasets = ps.get_telemetry_datasets(user.uid, project_id)
    io_rows = sum(d.get("row_count", 0) for d in datasets) if datasets else 0

    files = ps.get_project_files(user.uid, project_id)

    return {
        "project_id": project_id,
        "project_loaded": chunk_count > 0,
        "folder": project.get("root_directory", "") if project else "",
        "project_hash": project.get("index_version", "") if project else "",
        "index_state": state,
        "files_indexed": len(files),
        "tags_indexed": si_stats.tags,
        "routines_indexed": si_stats.routines,
        "io_rows_indexed": io_rows,
        "semantic_chunks": chunk_count,
        "memory_footprint_mb": si_stats.memory_footprint_mb,
        "errors": [],
        "warnings": [],
    }


# ── POST /api/project/query ───────────────────────────────────────────────────

@router.post("/query", response_model=ProjectQueryResponse)
def project_query(
    body: ProjectQueryRequest,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Execute the 9-step orchestrated Q&A pipeline.
    412 if project not indexed.
    409 if index is stale — re-ingest required.
    """
    try:
        orch = get_query_orchestrator()
        body.uid = user.uid
        return orch.query(body)
    except ProjectNotReadyError as exc:
        return JSONResponse(
            status_code=412,
            content={
                "error_type": exc.error_type,
                "message": exc.message,
                "action": f"POST /api/project/ingest with project_id='{body.project_id}'",
            },
        )
    except ProjectStaleError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "error_type": exc.error_type,
                "message": exc.message,
                "action": f"POST /api/project/ingest to rebuild the index.",
            },
        )
    except ProjectNotFoundError as exc:
        return JSONResponse(
            status_code=404,
            content={"error_type": exc.error_type, "message": exc.message},
        )
    except Exception as exc:
        logger.exception("Query failed for project=%s", body.project_id)
        return JSONResponse(
            status_code=500,
            content={"error_type": "QUERY_FAILED", "message": str(exc)},
        )


# ── GET /api/project/files ────────────────────────────────────────────────────

@router.get("/files")
def project_files(
    project_id: str = Query(default="default"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Return a nested file tree of all indexed files for this project.
    Only includes files successfully parsed by reading index metadata.
    """
    from app.indexes.structured_index import get_structured_index
    from app.indexes.semantic_index import get_semantic_index
    import os

    si = get_structured_index(project_id)
    files = si.all_source_files()

    try:
        sem = get_semantic_index()
        files.update(sem.all_source_files(project_id))
    except Exception:
        pass

    if not files:
        return []

    try:
        common = os.path.commonpath(list(files))
        if os.path.isfile(common):
            common = os.path.dirname(common)
    except ValueError:
        common = ""

    tree_dict = {}
    for path in sorted(files):
        if common and path.startswith(common):
            rel_path = path[len(common):].lstrip("/")
        else:
            rel_path = path.lstrip("/")

        if not rel_path:
            continue

        parts = rel_path.split("/")
        current = tree_dict
        for i, part in enumerate(parts):
            is_file = (i == len(parts) - 1)
            
            if part not in current:
                current[part] = {
                    "name": part,
                    "type": "file" if is_file else "folder",
                    "path": path, # will fix folder path below
                }
                if not is_file:
                    folder_idx = path.find(part, len(common) if common else 0)
                    if folder_idx != -1:
                        folder_path = path[:folder_idx + len(part)]
                    else:
                        folder_path = part
                    current[part]["path"] = folder_path
                    current[part]["children"] = {}
                    
            if not is_file:
                current = current[part]["children"]

    def _to_list(d: dict) -> list[dict]:
        res = []
        for k, v in d.items():
            node = {
                "name": v["name"],
                "type": v["type"],
                "path": v["path"]
            }
            if v["type"] == "folder":
                node["children"] = _to_list(v.get("children", {}))
            res.append(node)
        res.sort(key=lambda x: (0 if x["type"] == "folder" else 1, x["name"].lower()))
        return res

    return _to_list(tree_dict)


# ── GET /api/project/metrics ──────────────────────────────────────────────────

@router.get("/metrics", response_model=ProjectMetrics)
def project_metrics(
    project_id: str = Query(default="default"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Observability endpoint: embedding count, memory usage, ingestion duration.
    """
    from app.indexes.structured_index import get_structured_index
    from app.indexes.semantic_index import get_semantic_index

    si = get_structured_index(project_id)
    si_stats = si.stats()

    sem_count = 0
    try:
        sem = get_semantic_index()
        sem_count = sem.collection_size(project_id)
    except Exception:
        pass

    return ProjectMetrics(
        project_id=project_id,
        embedding_count=sem_count,
        vector_db_collection_size=sem_count,
        structured_index_tags=si_stats.tags,
        structured_index_routines=si_stats.routines,
        memory_usage_mb=si_stats.memory_footprint_mb,
    )


# ── DELETE /api/project/reset ─────────────────────────────────────────────────

@router.delete("/reset")
def project_reset(
    project_id: str = Query(default="default"),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Clear all indexes and reset project state."""
    from app.indexes.structured_index import clear_structured_index
    from app.indexes.semantic_index import get_semantic_index

    clear_structured_index(project_id)
    try:
        get_semantic_index().delete_project(project_id)
    except Exception as exc:
        logger.warning("SemanticIndex delete failed: %s", exc)

    return {"status": "reset", "project_id": project_id}