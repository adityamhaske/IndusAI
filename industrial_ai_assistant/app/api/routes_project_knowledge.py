"""
Project Knowledge Engine — API routes.

Endpoints:
  POST   /api/project/ingest   — Ingest a project folder
  GET    /api/project/status   — Full readiness status
  POST   /api/project/query    — Query the indexed project
  DELETE /api/project/reset    — Purge all indexes
  GET    /api/project/metrics  — Observability metrics
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from app.core.project_exceptions import (
    HallucinatedTagError,
    IngestionAlreadyRunningError,
    IngestionFailedError,
    ProjectIndexStaleError,
    ProjectNotFoundError,
    ProjectNotReadyError,
)
from app.models.project_models import (
    IngestRequest,
    ProjectQueryRequest,
    ProjectQueryResponse,
    ProjectStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/project", tags=["Project Knowledge"])


# ── POST /project/ingest ──────────────────────────────────────────────────────

@router.post("/ingest")
def ingest_project(body: IngestRequest):
    """
    Walk a project folder and index all supported files.
    Returns 409 if ingestion is already running for this project.
    """
    folder = Path(body.folder_path)
    if not folder.is_dir():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "FOLDER_NOT_FOUND",
                     "message": f"Folder not found: {body.folder_path}"},
        )
    try:
        from app.services.project_ingestion_pipeline import get_ingestion_pipeline
        result = get_ingestion_pipeline().ingest(body.folder_path, body.project_id)
        return result.model_dump()
    except IngestionAlreadyRunningError as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": exc.error_type, "message": exc.message},
        )
    except Exception as exc:
        logger.exception("Ingestion error for project '%s'", body.project_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "INGESTION_FAILED", "message": str(exc)},
        )


# ── GET /project/status ───────────────────────────────────────────────────────

@router.get("/status", response_model=ProjectStatus)
def project_status(project_id: str = Query(default="default")):
    """
    Return full readiness and ingestion metrics for a project.
    Includes memory footprint, stale-index flag, and any warnings.
    """
    from app.services.project_context_manager import get_project_context_manager
    return get_project_context_manager().get_status(project_id)


# ── POST /project/query ───────────────────────────────────────────────────────

@router.post("/query", response_model=ProjectQueryResponse)
def query_project(body: ProjectQueryRequest):
    """
    9-step orchestrated query:
    readiness check → classify → structured lookup → semantic retrieval
    → merge → prompt → LLM → validate → return.

    Returns 503 if project not ready.
    Returns 409 if index stale.
    Returns 422 if LLM generates hallucinated tags.
    """
    try:
        from app.services.query_orchestrator import get_query_orchestrator
        return get_query_orchestrator().query(body)
    except ProjectNotReadyError as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": exc.error_type, "message": exc.message},
        )
    except ProjectIndexStaleError as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": exc.error_type, "message": exc.message,
                     "reindex_required": True},
        )
    except HallucinatedTagError as exc:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": exc.error_type, "message": exc.message,
                     "hallucinated_tags": exc.tags},
        )
    except Exception as exc:
        logger.exception("Query error for project '%s'", body.project_id)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "QUERY_FAILED", "message": str(exc)},
        )


# ── DELETE /project/reset ─────────────────────────────────────────────────────

@router.delete("/reset")
def reset_project(project_id: str = Query(default="default")):
    """Purge all StructuredIndex and SemanticIndex data for this project."""
    from app.services.project_context_manager import get_project_context_manager
    get_project_context_manager().reset(project_id)
    return {"status": "reset", "project_id": project_id}


# ── GET /project/metrics ──────────────────────────────────────────────────────

@router.get("/metrics")
def project_metrics(project_id: str = Query(default="default")):
    """
    Observability metrics:
    - structured_memory_mb
    - semantic_chunk_count
    - tags, routines, aois, io_rows
    - ingestion_duration_s
    """
    from app.services.project_context_manager import get_project_context_manager
    return get_project_context_manager().get_metrics(project_id)
