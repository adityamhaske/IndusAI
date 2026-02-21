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

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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
from app.services.project_context_manager import get_project_context_manager
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
async def ingest_project(body: IngestRequest):
    """
    Walk the folder, classify files, and populate StructuredIndex + SemanticIndex.
    Returns IngestionResult with counts and any errors.
    409 if ingestion is already running for this project.
    """
    try:
        pipeline = get_ingestion_pipeline()
        result = await pipeline.ingest(body.folder_path, body.project_id)
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

        # Surface IS_DOCKER warning if path not found
        from app.services.project_context_manager import IS_DOCKER
        if IS_DOCKER:
            diag.setdefault("warnings", [])
            diag["warnings"].append(
                "Backend is running inside a Docker container. "
                "Ensure the host path is volume-mounted into the container."
            )

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
def project_status(project_id: str = Query(default="default")):
    """
    Return full project index status including memory footprint and warnings.
    """
    ctx = get_project_context_manager()
    status = ctx.get_status(project_id)

    # Enrich with SemanticIndex chunk count
    try:
        from app.indexes.semantic_index import get_semantic_index
        sem = get_semantic_index()
        status.semantic_chunks = sem.collection_size(project_id)
    except Exception:
        pass

    return status


# ── POST /api/project/query ───────────────────────────────────────────────────

@router.post("/query", response_model=ProjectQueryResponse)
def project_query(body: ProjectQueryRequest):
    """
    Execute the 9-step orchestrated Q&A pipeline.
    412 if project not indexed.
    409 if index is stale — re-ingest required.
    """
    try:
        orch = get_query_orchestrator()
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
def project_files(project_id: str = Query(default="default")):
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
        return {"root": project_id, "children": []}

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

    children = _to_list(tree_dict)
    
    # Try to extract a clean root name from the common path
    root_name = project_id
    if common:
        root_name = os.path.basename(common) or project_id
        
    return {
        "root": root_name,
        "children": children
    }


# ── GET /api/project/metrics ──────────────────────────────────────────────────

@router.get("/metrics", response_model=ProjectMetrics)
def project_metrics(project_id: str = Query(default="default")):
    """
    Observability endpoint: embedding count, memory usage, ingestion duration.
    """
    from app.indexes.structured_index import get_structured_index
    from app.indexes.semantic_index import get_semantic_index
    from app.services.project_context_manager import get_project_context_manager

    si = get_structured_index(project_id)
    si_stats = si.stats()
    ctx = get_project_context_manager()
    status = ctx.get_status(project_id)

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
        ingestion_duration_ms=status.ingestion_duration_ms,
        last_index_time=status.last_index_time,
    )

# ── GET /api/project/debug-path ───────────────────────────────────────────────

@router.get("/debug-path")
def debug_path(folder_path: str = Query(..., description="Path to test")):
    """
    Quick diagnostic: checks whether the backend process can access a given path.
    Does NOT ingest or modify any state.

    Returns exists, is_dir, resolved_path, cwd, container_mode, allowed_root.
    Use this to diagnose Docker mount issues or path typos.
    """
    from app.services.project_context_manager import validate_folder_path, IS_DOCKER
    import os
    from pathlib import Path

    diag = validate_folder_path(folder_path)
    resp = {
        "provided_path": diag.provided_path,
        "resolved_path": diag.resolved_path,
        "exists": os.path.exists(diag.resolved_path) if diag.resolved_path != "ERROR" else False,
        "is_dir": os.path.isdir(diag.resolved_path) if diag.resolved_path != "ERROR" else False,
        "cwd": diag.cwd,
        "container_mode": diag.container_mode,
        "allowed_root": diag.allowed_root,
        "effective_uid": diag.effective_uid,
        "ok": diag.ok,
    }
    if not diag.ok:
        resp["error_code"] = diag.error_code
        resp["message"] = diag.message
    if IS_DOCKER:
        resp["docker_warning"] = (
            "Backend running in Docker. Host paths must be mounted as volumes."
        )
    return resp


# ── DELETE /api/project/reset ─────────────────────────────────────────────────

@router.delete("/reset")
def project_reset(project_id: str = Query(default="default")):
    """Clear all indexes and reset project state."""
    from app.indexes.structured_index import clear_structured_index
    from app.indexes.semantic_index import get_semantic_index

    clear_structured_index(project_id)
    try:
        get_semantic_index().delete_project(project_id)
    except Exception as exc:
        logger.warning("SemanticIndex delete failed: %s", exc)

    get_project_context_manager().reset(project_id)
    return {"status": "reset", "project_id": project_id}
