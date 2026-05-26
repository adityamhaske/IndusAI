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
from pydantic import BaseModel


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
from app.models.fault_analysis_models import FaultAnalysisRequest, FaultAnalysisV2Response, QuickStatsResponse
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
    Upload a PLC fault log CSV to Firebase Storage and process.
    """
    import uuid
    from app.core.firebase import get_storage_bucket

    if not file.filename.endswith(".csv"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only CSV files accepted")

    # File size check (before reading all bytes)
    raw_bytes = await file.read()
    size_mb = len(raw_bytes) / (1024 ** 2)

    if size_mb > MAX_FILE_SIZE_MB:
        return _fault_error(
            FaultTooLargeError(f"File size {size_mb:.1f} MB exceeds limit of {MAX_FILE_SIZE_MB} MB."),
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    # Generate unique filename
    file_id = str(uuid.uuid4())
    blob_path = f"fault-logs/{file_id}/{file.filename}"
    
    # Upload to Firebase Storage
    try:
        bucket = get_storage_bucket()
        blob = bucket.blob(blob_path)
        blob.upload_from_string(raw_bytes, content_type="text/csv")
        logger.info(f"Uploaded {file.filename} to Firebase Storage at {blob_path}")
    except Exception as e:
        logger.warning(f"Failed to upload to Firebase Storage: {e}")

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


# ── POST /fault/load-dataset ──────────────────────────────────────────────────

class LoadDatasetRequest(BaseModel):
    file_path: str
    project_id: str = "default"

@router.post("/load-dataset", response_model=UploadResponse)
async def load_stored_dataset(body: "LoadDatasetRequest"):
    """
    Load a previously uploaded telemetry CSV by its stored file_path —
    no re-upload required. Used by the persistent telemetry dropdown.
    """
    from pathlib import Path
    from pydantic import BaseModel as _BM
    p = Path(body.file_path)
    if not p.exists() or not p.is_file():
        return JSONResponse(
            status_code=404,
            content={"error": "DATASET_NOT_FOUND", "message": f"File not found: {body.file_path}"},
        )
    try:
        raw_bytes = p.read_bytes()
        df_raw = pd.read_csv(io.BytesIO(raw_bytes))
        df_norm, warnings = normalize(df_raw, source_filename=p.name)
        svc = get_fault_service()
        result = svc.upload(
            df=df_norm,
            source_filename=p.name,
            raw_bytes=raw_bytes,
            project_id=body.project_id,
            warnings=warnings,
        )
        return UploadResponse(**result)
    except FaultSchemaError as exc:
        return _fault_error(exc)
    except Exception as exc:
        logger.exception("load-dataset failed for %s", body.file_path)
        return JSONResponse(status_code=500, content={"error": "LOAD_FAILED", "message": str(exc)})


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


# ── GET /fault/quick-stats ────────────────────────────────────────────────────

@router.get("/quick-stats", response_model=QuickStatsResponse)
def quick_stats(
    row_id: int = Query(...),
    project_id: str = Query(default="default"),
):
    """
    Returns deterministic stats instantly (no LLM, no RAG) for the dual-engine UI.
    Computes time-windows, bursts, anomalies, and confidence in <100ms.
    """
    from app.config.dependency_injection import get_container
    from app.utils.fault_statistics import (
        _timestamps_for_code,
        check_metric_integrity,
        compute_cooccurrence,
        compute_occurrences_in_window,
        compute_rolling_metrics,
        compute_trend,
    )
    from app.utils.fault_confidence import compute_confidence
    from app.core.fault_exceptions import DatasetNotLoadedError, FaultRowNotFoundError, AnalysisPrerequisiteError

    try:
        container = get_container()
        fault_svc = container.fault_orchestrator._fault_svc
        ds = fault_svc._store.get(project_id)
        if ds is None:
            raise DatasetNotLoadedError()

        df = ds.dataframe
        matches = df[df["row_id"] == row_id]
        if matches.empty:
            raise FaultRowNotFoundError(row_id)
        if not ds.stats_cache:
            raise AnalysisPrerequisiteError("Stats cache empty — re-upload dataset.")

        row = matches.iloc[0]
        fault_code = str(row["fault_code"])
        ref_ts = row["timestamp"].to_pydatetime()

        ts_list = _timestamps_for_code(df, fault_code)
        
        occ_1h  = compute_occurrences_in_window(ts_list, ref_ts, hours=1)
        occ_24h = compute_occurrences_in_window(ts_list, ref_ts, hours=24)
        co_fault, co_count = compute_cooccurrence(df, ref_ts)
        burst = ds.stats_cache.get("burst_detected", False)
        burst_desc = ds.stats_cache.get("burst_description", "")
        burst_count = ds.stats_cache.get("burst_count", 0)
        
        rolling_avg_5m, rolling_avg_1h, delta_last_30m, anomaly_score = compute_rolling_metrics(ts_list, ref_ts)
        trend = compute_trend(delta_last_30m, rolling_avg_1h)
        
        integrity_passed = check_metric_integrity(burst, burst_count, occ_1h, anomaly_score)
        
        confidence = compute_confidence(
            burst_detected=burst,
            anomaly_score=anomaly_score,
            integrity_passed=integrity_passed,
            occurrences_1h=occ_1h
        )

        return QuickStatsResponse(
            occurrences_last_hour=occ_1h,
            occurrences_last_24h=occ_24h,
            top_cooccurring_fault=co_fault,
            cooccurrence_count=co_count,
            burst_detected=burst,
            burst_description=burst_desc,
            burst_count=burst_count,
            confidence=confidence,
            rolling_avg_5m=rolling_avg_5m,
            rolling_avg_1h=rolling_avg_1h,
            delta_last_30m=delta_last_30m,
            anomaly_score=anomaly_score,
            trend=trend,
            integrity_passed=integrity_passed
        )
    except (DatasetNotLoadedError, FaultRowNotFoundError) as exc:
        return _fault_error(exc, status.HTTP_404_NOT_FOUND)
    except AnalysisPrerequisiteError as exc:
        return _fault_error(exc, status.HTTP_409_CONFLICT)
    except Exception as exc:
        logger.exception("Unexpected error in quick-stats")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error_type": "INTERNAL_ERROR", "message": str(exc)}
        )


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
