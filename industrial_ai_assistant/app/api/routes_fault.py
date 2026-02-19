"""
API routes for the PLC Fault System.

Endpoints:
  POST   /api/fault/upload   — Upload and normalize CSV
  GET    /api/fault/list     — Paginated rows
  GET    /api/fault/summary  — Aggregate stats (from cache)
  GET    /api/fault/detail   — Single row + history
  POST   /api/fault/analyze  — LLM analysis with safety guard
  DELETE /api/fault/reset    — Clear dataset + GC
  GET    /api/fault/metrics  — Observability metrics
"""
import io
import logging
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse

from app.core.fault_exceptions import (
    AnalysisPrerequisiteError,
    DatasetHashMismatchError,
    DatasetNotLoadedError,
    FaultParsingError,
    FaultRowNotFoundError,
    FaultSchemaError,
    FaultTooLargeError,
)
from app.core.llm_exceptions import LLMConnectionError, LLMResponseParseError, RAGConnectionError
from app.models.fault_models import (
    ErrorResponse,
    FaultDetailResponse,
    FaultListResponse,
    FaultMetricsResponse,
    FaultSummaryResponse,
    UploadResponse,
)
from app.models.fault_analysis_models import FaultAnalysisRequest, FaultAnalysisV2Response
from app.services.fault_service import MAX_FILE_SIZE_MB, get_fault_service
from app.utils.schema_normalizer import normalize

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/fault", tags=["PLC Faults"])


def _fault_error(exc: Exception, http_status: int = 400) -> JSONResponse:
    body = ErrorResponse(
        error_type=type(exc).__name__,
        message=str(exc),
    )
    return JSONResponse(status_code=http_status, content=body.model_dump())


# ── POST /fault/upload ────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_fault_csv(
    file: UploadFile = File(...),
    project_id: str = Form(default="default"),
):
    """
    Upload a PLC fault log CSV.
    Validates file size, normalizes schema, caches stats, returns preview.
    """
    # File size check (before reading all bytes)
    raw_bytes = await file.read()
    size_mb = len(raw_bytes) / (1024 ** 2)

    if size_mb > MAX_FILE_SIZE_MB:
        return _fault_error(
            FaultTooLargeError(f"File size {size_mb:.1f} MB exceeds limit of {MAX_FILE_SIZE_MB} MB."),
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    try:
        df_raw = pd.read_csv(io.BytesIO(raw_bytes))
    except Exception as exc:
        return _fault_error(FaultParsingError(f"Could not parse CSV: {exc}"))

    try:
        df_norm, warnings = normalize(df_raw, source_filename=file.filename)
    except FaultSchemaError as exc:
        return _fault_error(exc)

    try:
        svc = get_fault_service()
        result = svc.upload(
            df=df_norm,
            source_filename=file.filename or "unknown.csv",
            raw_bytes=raw_bytes,
            project_id=project_id,
            warnings=warnings,
        )
    except FaultTooLargeError as exc:
        return _fault_error(exc, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    return UploadResponse(**result)


# ── GET /fault/list ───────────────────────────────────────────────────────────

@router.get("/list", response_model=FaultListResponse)
def list_faults(
    project_id: str = Query(default="default"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=1000),
):
    """Return a paginated page of fault rows. Never sends full dataset."""
    try:
        return get_fault_service().get_page(project_id, page, size)
    except DatasetNotLoadedError as exc:
        return _fault_error(exc, status.HTTP_404_NOT_FOUND)


# ── GET /fault/summary ────────────────────────────────────────────────────────

@router.get("/summary", response_model=FaultSummaryResponse)
def fault_summary(project_id: str = Query(default="default")):
    """Return aggregate statistics from cache (no recomputation)."""
    try:
        return get_fault_service().get_summary(project_id)
    except DatasetNotLoadedError as exc:
        return _fault_error(exc, status.HTTP_404_NOT_FOUND)


# ── GET /fault/detail ─────────────────────────────────────────────────────────

@router.get("/detail", response_model=FaultDetailResponse)
def fault_detail(
    row_id: int = Query(...),
    project_id: str = Query(default="default"),
):
    """Return a single fault row with historical context (O(log n) retrieval)."""
    try:
        return get_fault_service().get_detail(project_id, row_id)
    except DatasetNotLoadedError as exc:
        return _fault_error(exc, status.HTTP_404_NOT_FOUND)
    except FaultRowNotFoundError as exc:
        return _fault_error(exc, status.HTTP_404_NOT_FOUND)


# ── POST /fault/analyze ───────────────────────────────────────────────────────

@router.post("/analyze", response_model=FaultAnalysisV2Response)
def analyze_fault(body: FaultAnalysisRequest):
    """
    Orchestrated fault analysis: deterministic stats + RAG docs + LLM reasoning.
    Optional 'question' field enables custom row-level Q&A.
    Returns structured error if LLM/RAG connectivity fails.
    """
    from app.config.dependency_injection import get_container
    try:
        container = get_container()
        orchestrator = container.fault_orchestrator
    except Exception as exc:
        logger.error("DI container failed to initialize: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error_type": "SERVICE_UNAVAILABLE",
                "message": f"Backend services failed to initialize: {exc}. "
                           "Check that Qdrant and Ollama are running.",
            }
        )

    try:
        return orchestrator.analyze_fault(body)
    except LLMConnectionError as exc:
        logger.error("LLM not connected: %s", exc.message)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error_type": "LLM_NOT_CONNECTED",
                "message": exc.message,
                "action": "Start Ollama with: ollama serve",
            }
        )
    except RAGConnectionError as exc:
        logger.error("RAG not initialized: %s", exc.message)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error_type": "RAG_NOT_INITIALIZED",
                "message": exc.message,
            }
        )
    except LLMResponseParseError as exc:
        logger.error("LLM returned invalid response: %s", exc.message)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "error_type": "LLM_RESPONSE_INVALID",
                "message": exc.message,
            }
        )
    except (DatasetNotLoadedError, FaultRowNotFoundError) as exc:
        return _fault_error(exc, status.HTTP_404_NOT_FOUND)
    except (DatasetHashMismatchError, AnalysisPrerequisiteError) as exc:
        return _fault_error(exc, status.HTTP_409_CONFLICT)
    except Exception as exc:
        logger.exception("Unexpected error during fault analysis")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error_type": "INTERNAL_ERROR", "message": str(exc)}
        )


# ── DELETE /fault/reset ───────────────────────────────────────────────────────

@router.delete("/reset")
def reset_fault_dataset(project_id: str = Query(default="default")):
    """Clear the in-memory dataset and force garbage collection."""
    result = get_fault_service().reset(project_id)
    return result


# ── GET /fault/metrics ────────────────────────────────────────────────────────

@router.get("/metrics", response_model=FaultMetricsResponse)
def fault_metrics(project_id: str = Query(default="default")):
    """Return observability metrics: memory, row count, timing."""
    return get_fault_service().get_metrics(project_id)
