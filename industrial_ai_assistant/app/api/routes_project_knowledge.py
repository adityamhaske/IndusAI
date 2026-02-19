"""
Project Knowledge Engine API routes.

Endpoints:
  POST   /api/project/ingest   — Set folder and trigger ingestion
  GET    /api/project/status   — Return ingestion status + metrics
  POST   /api/project/query    — Run 9-step query orchestrator
  DELETE /api/project/reset    — Clear project from memory
"""
from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import JSONResponse

from app.core.project_exceptions import (
    IngestionError,
    ProjectNotReadyError,
    TagHallucinationError,
)
from app.indexes.structured_index import get_structured_store
from app.models.project_models import (
    IngestRequest,
    ProjectQueryRequest,
    ProjectQueryResponse,
    ProjectStatusResponse,
)
from app.services.project_context_manager import get_project_context_manager
from app.services.project_ingestion_pipeline import ingest_project

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Project Knowledge Engine"])

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_semantic_index():
    """Lazy-init SemanticIndex from the DI container."""
    from app.config.dependency_injection import get_container
    container = get_container()
    from app.indexes.semantic_index import SemanticIndex
    from qdrant_client import QdrantClient
    from app.config.settings import settings
    client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    embedder = container.embedder
    return SemanticIndex(
        qdrant_client=client,
        collection_name=settings.QDRANT_COLLECTION,
        embedder=embedder,
    )


def _get_llm():
    from app.config.dependency_injection import get_container
    return get_container().llm


# ── POST /project/ingest ──────────────────────────────────────────────────────

@router.post("/ingest", response_model=ProjectStatusResponse)
def ingest(body: IngestRequest, background_tasks: BackgroundTasks):
    """
    Register a project folder and start ingestion in the background.
    Returns immediately with status=running.
    Poll GET /project/status for completion.
    """
    ctx = get_project_context_manager()

    try:
        project_hash = ctx.set_project(body.project_id, body.folder_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    logger.info(
        "Ingest request: project=%s folder=%s hash=%s",
        body.project_id, body.folder_path, project_hash,
    )

    struct_store = get_structured_store()
    struct_store.reset(body.project_id)   # clear any prior indexed data

    try:
        semantic_index = _get_semantic_index()
        semantic_index.delete_project(body.project_id)
    except Exception as exc:
        logger.warning("Could not clear semantic index for project=%s: %s", body.project_id, exc)
        semantic_index = None

    def _run_ingestion():
        try:
            if semantic_index is None:
                # SemanticIndex unavailable — create a noop one
                from app.indexes.semantic_index import SemanticIndex
                _sem = _noop_semantic_index()
            else:
                _sem = semantic_index
            ingest_project(
                project_id=body.project_id,
                folder_path=body.folder_path,
                context_manager=ctx,
                struct_store=struct_store,
                semantic_index=_sem,
            )
        except Exception as exc:
            ctx.mark_failed(body.project_id, str(exc))
            logger.exception("Background ingestion failed: project=%s", body.project_id)

    background_tasks.add_task(_run_ingestion)
    return ctx.get_status(body.project_id)


# ── GET /project/status ───────────────────────────────────────────────────────

@router.get("/status", response_model=ProjectStatusResponse)
def project_status(project_id: str = Query(default="default")):
    """Return current ingestion status and indexed metrics for a project."""
    return get_project_context_manager().get_status(project_id)


# ── POST /project/query ───────────────────────────────────────────────────────

@router.post("/query", response_model=ProjectQueryResponse)
def project_query(body: ProjectQueryRequest):
    """
    Run the 9-step QueryOrchestrator against an ingested project.
    Returns structured matches + semantic context + verified LLM answer.
    Raises 503 if project not ready, 422 if LLM hallucinates tags.
    """
    ctx = get_project_context_manager()

    try:
        ctx.require_ready(body.project_id)
    except ProjectNotReadyError as exc:
        return JSONResponse(
            status_code=503,
            content={"error": "PROJECT_NOT_READY", "message": exc.message},
        )

    struct_store = get_structured_store()
    struct_idx = struct_store.get(body.project_id)
    if struct_idx is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": "PROJECT_NOT_READY",
                "message": f"Structured index not found for project '{body.project_id}'.",
            },
        )

    try:
        semantic_index = _get_semantic_index()
        llm = _get_llm()
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"error": "SERVICE_UNAVAILABLE", "message": str(exc)},
        )

    from app.services.query_orchestrator import QueryOrchestrator
    orchestrator = QueryOrchestrator(
        context_manager=ctx,
        struct_idx=struct_idx,
        semantic_index=semantic_index,
        llm=llm,
    )

    try:
        return orchestrator.query(body)
    except TagHallucinationError as exc:
        return JSONResponse(
            status_code=422,
            content={
                "error": "TAG_HALLUCINATION",
                "message": exc.message,
                "invented_tags": exc.invented_tags,
            },
        )
    except Exception as exc:
        logger.exception("Query failed: project=%s query=%s", body.project_id, body.query)
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_ERROR", "message": str(exc)},
        )


# ── DELETE /project/reset ─────────────────────────────────────────────────────

@router.delete("/reset")
def reset_project(project_id: str = Query(default="default")):
    """Remove project from memory (does not delete files)."""
    ctx = get_project_context_manager()
    struct_store = get_structured_store()
    struct_store.reset(project_id)

    try:
        semantic_index = _get_semantic_index()
        semantic_index.delete_project(project_id)
    except Exception:
        pass

    ctx.reset(project_id)
    return {"message": f"Project '{project_id}' reset successfully."}


# ── Noop SemanticIndex (when Qdrant unavailable) ─────────────────────────────

class _NoopSemanticIndex:
    def index_chunks(self, project_id, chunks): return 0
    def search(self, project_id, query, top_k=5): return []
    def delete_project(self, project_id): pass


def _noop_semantic_index():
    return _NoopSemanticIndex()
