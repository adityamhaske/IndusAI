"""
Unified Knowledge Query Endpoint.

POST /api/knowledge/query

Routing rules (explicit, no silent fallback):
  If project_loaded → ALWAYS ProjectKnowledgeEngine (QueryOrchestrator)
    - Handles general questions via SemanticIndex docs
    - Handles tag/routine questions via StructuredIndex
  If not project_loaded:
    - Check if query contains known PLC tags (deterministic, via StructuredIndex)
    - If yes → return PROJECT_NOT_INDEXED error (fail-fast)
    - If no  → route to legacy ChatService (LEGACY_RAG mode)

Tag detection: tokenize query → intersect with StructuredIndex.all_tag_names_lower()
(NOT regex heuristics — exact match only).

Always returns:
  knowledge_mode: "PROJECT" | "LEGACY_RAG"
  prompt_version: str
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.project_exceptions import (
    ProjectNotReadyError,
    ProjectStaleError,
)
from app.indexes.structured_index import get_structured_index
from app.services.project_context_manager import get_project_context_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["Knowledge"])

KNOWLEDGE_MODE_PROJECT    = "PROJECT"
KNOWLEDGE_MODE_LEGACY_RAG = "LEGACY_RAG"


# ── Request / Response schemas ─────────────────────────────────────────────────

class KnowledgeQueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    project_id: str = Field(default="default")
    top_k: int = Field(default=5, ge=1, le=20)
    selected_files: list[str] = Field(default_factory=list)
    selected_folders: list[str] = Field(default_factory=list)
    scope_mode: Literal["STRICT", "PREFER", "GLOBAL"] = "GLOBAL"
    session_id: str = Field(default="")   # Optional: pass existing session_id to append to it


class StructuredHitOut(BaseModel):
    hit_type: str
    data: dict[str, Any]


class KnowledgeQueryResponse(BaseModel):
    question: str
    project_id: str
    knowledge_mode: str                         # "PROJECT" | "LEGACY_RAG"
    # ── Structured answer fields (v2 schema) ──
    summary: str
    root_causes: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    # ── Metadata ──
    structured_hits: list[StructuredHitOut] = Field(default_factory=list)
    documentation_sources: list[str] = Field(default_factory=list)
    confidence: str = "LOW"
    prompt_version: str = Field(default="v3.0.0")
    hallucinated_tags_removed: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    context_scope: dict[str, Any] = Field(default_factory=dict)
    llm_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    session_id: str = Field(default="")   # returned so frontend can link messages to this session


# ── Unified endpoint ───────────────────────────────────────────────────────────

@router.post("/query", response_model=KnowledgeQueryResponse)
def knowledge_query(body: KnowledgeQueryRequest):
    t_start = time.perf_counter()
    ctx = get_project_context_manager()
    status = ctx.get_status(body.project_id)

    # ── Route 1: Project loaded → always use Project Knowledge Engine ──────────
    if status.project_loaded:
        return _route_project(body, t_start)

    # ── Route 2: No project. Tag-specific query? → fail-fast. ─────────────────
    tag_hits = _detect_project_tags(body.question, body.project_id)
    if tag_hits:
        return JSONResponse(
            status_code=412,
            content={
                "error_type": "PROJECT_NOT_INDEXED",
                "message": (
                    "Your query references project-specific PLC tags but no project "
                    "has been indexed. Please ingest a project folder first."
                ),
                "detected_tags": tag_hits,
                "action": "POST /api/project/ingest to index your project folder.",
            },
        )

    # ── Route 3: No project, general question → legacy RAG ────────────────────
    return _route_legacy_rag(body, t_start)


# ── Project engine route ───────────────────────────────────────────────────────

def _route_project(body: KnowledgeQueryRequest, t_start: float) -> KnowledgeQueryResponse:
    """Route to QueryOrchestrator. Handles both structured and semantic questions."""
    try:
        from app.models.project_models import ProjectQueryRequest
        from app.services.query_orchestrator import get_query_orchestrator

        req = ProjectQueryRequest(
            question=body.question,
            project_id=body.project_id,
            top_k=body.top_k,
            selected_files=body.selected_files,
            selected_folders=body.selected_folders,
            scope_mode=body.scope_mode,
        )
        result = get_query_orchestrator().query(req)
        total_ms = (time.perf_counter() - t_start) * 1000

        logger.info(
            "[%s] KNOWLEDGE mode=PROJECT intent=%s confidence=%s prompt_v=%s",
            body.project_id, [l.value for l in result.query_intent.labels],
            result.confidence, result.prompt_version,
        )

        # Decompose answer JSON (stored as JSON string from orchestrator)
        import json as _json
        summary = result.answer
        root_causes: list[str] = []
        recommended_actions: list[str] = []
        supporting_evidence: list[str] = []
        limitations: list[str] = []
        try:
            parsed_answer = _json.loads(result.answer)
            summary             = parsed_answer.get("summary", result.answer)
            root_causes         = parsed_answer.get("root_causes", [])
            recommended_actions = parsed_answer.get("recommended_actions", [])
            supporting_evidence = parsed_answer.get("supporting_evidence", [])
            limitations         = parsed_answer.get("limitations", [])
        except Exception:
            pass  # If answer is plain text, use it as summary

        resp = KnowledgeQueryResponse(
            question=body.question,
            project_id=body.project_id,
            knowledge_mode=KNOWLEDGE_MODE_PROJECT,
            summary=summary,
            root_causes=root_causes,
            recommended_actions=recommended_actions,
            supporting_evidence=supporting_evidence,
            limitations=limitations,
            structured_hits=[
                StructuredHitOut(hit_type=h.hit_type, data=h.data)
                for h in result.structured_hits
            ],
            documentation_sources=result.semantic_sources,
            confidence=result.confidence,
            prompt_version=result.prompt_version,
            hallucinated_tags_removed=result.hallucinated_tags_removed,
            warnings=result.warnings,
            llm_latency_ms=result.llm_latency_ms,
            total_latency_ms=round(total_ms, 1),
        )

        # ── Auto-persist session (fire-and-forget, never breaks query) ──
        try:
            from app.config.dependency_injection import get_container
            hs = get_container().history_service
            session_id = body.session_id or None
            conf_float = {"HIGH": 0.85, "MEDIUM": 0.55, "LOW": 0.25}.get(result.confidence, 0.5)
            if session_id:
                hs.append_message(session_id, "user", body.question)
                hs.append_message(session_id, "assistant", summary)
                hs.complete_session(session_id, latency_ms=int(total_ms), confidence_score=conf_float)
            else:
                title = body.question[:60] + ("…" if len(body.question) > 60 else "")
                gateway = get_container().ai_gateway
                provider = gateway.policy.primary
                sess = hs.create_session(
                    session_type="chat",
                    title=title,
                    provider=provider,
                    project_id=body.project_id,
                )
                hs.append_message(sess.id, "user", body.question)
                hs.append_message(sess.id, "assistant", summary)
                hs.complete_session(sess.id, latency_ms=int(total_ms), confidence_score=conf_float)
                session_id = sess.id
            resp.session_id = session_id or ""
        except Exception as _pe:
            logger.warning("Session persist failed (non-fatal): %s", _pe)

        return resp

    except (ProjectNotReadyError, ProjectStaleError) as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error_type": exc.error_type, "message": exc.message},
        )
    except Exception as exc:
        logger.exception("Project route failed for project=%s", body.project_id)
        return JSONResponse(
            status_code=500,
            content={"error_type": "QUERY_FAILED", "message": str(exc)},
        )


# ── Legacy RAG route ───────────────────────────────────────────────────────────

def _route_legacy_rag(body: KnowledgeQueryRequest, t_start: float) -> KnowledgeQueryResponse:
    """
    Route to legacy basic QA when no project is loaded.
    """
    try:
        from app.config.dependency_injection import get_container
        from app.models.ai_models import AIRequest
        
        container = get_container()
        gateway = container.ai_gateway
        
        t_llm = time.perf_counter()
        
        # Simple systemic generic QA prompt
        system_prompt = (
            "You are an Industrial AI assistant. The user is asking a general question "
            "but has not loaded a specific PLC project. Answer generally and concisely."
        )
        
        req = AIRequest(
            system_prompt=system_prompt,
            prompt=body.question,
            temperature=0.3,
            max_tokens=500
        )
        
        result = gateway.execute(req)
        
        llm_ms = (time.perf_counter() - t_llm) * 1000
        total_ms = (time.perf_counter() - t_start) * 1000

        if not result.success:
            raise Exception(result.error_message or "Gateway execution failed")

        return KnowledgeQueryResponse(
            question=body.question,
            project_id=body.project_id,
            knowledge_mode=KNOWLEDGE_MODE_LEGACY_RAG,
            summary=result.raw_output,
            reasoning="General knowledge only.",
            structured_hits=[],
            documentation_sources=[],
            confidence="MEDIUM",
            prompt_version="v3.0.0",
            warnings=["No project indexed — answers are based on general knowledge only."],
            llm_latency_ms=round(llm_ms, 1),
            total_latency_ms=round(total_ms, 1),
        )

    except Exception as exc:
        # Legacy RAG unavailable (e.g. gateway error).
        logger.warning("Legacy RAG unavailable: %s", exc)
        total_ms = (time.perf_counter() - t_start) * 1000
        return KnowledgeQueryResponse(
            question=body.question,
            project_id=body.project_id,
            knowledge_mode=KNOWLEDGE_MODE_LEGACY_RAG,
            summary=(
                "General documentation search is currently unavailable. "
                "To get full PLC-level answers: go to Settings → select your project folder → click Index Project."
            ),
            confidence="LOW",
            prompt_version="v3.0.0",
            warnings=[
                "Legacy RAG unavailable — ai gateway error.",
                f"Technical detail: {str(exc)[:120]}",
            ],
            total_latency_ms=round(total_ms, 1),
        )


# ── Tag detection ──────────────────────────────────────────────────────────────

def _detect_project_tags(query: str, project_id: str) -> list[str]:
    """
    Deterministic tag detection: tokenise query, intersect with StructuredIndex.
    Returns list of matched known tag names.
    Empty list = no project-specific tags detected.
    """
    si = get_structured_index(project_id)
    known = si.all_tag_names_lower()
    if not known:
        return []   # No tags indexed at all — can't detect

    tokens = set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_.:\-]*', query))
    hits = []
    for token in tokens:
        t_lower = token.lower().split(".")[-1].split(":")[-1]  # strip scope prefix
        if t_lower in known:
            hits.append(token)
    return hits


# ── Helpers ────────────────────────────────────────────────────────────────────

def _float_to_confidence(score: float) -> str:
    if score >= 0.75:
        return "HIGH"
    if score >= 0.45:
        return "MEDIUM"
    return "LOW"
