"""
Pydantic v2 models for the Project Knowledge Engine.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Structured record types ────────────────────────────────────────────────────

class TagRecord(BaseModel):
    name: str
    data_type: str = "UNKNOWN"
    scope: str = "Controller"          # Controller | Program:<name>
    description: str = ""
    value: str = ""
    source_file: str = ""


class RoutineRecord(BaseModel):
    name: str
    program: str = ""
    routine_type: str = "LAD"          # LAD | ST | FBD | SFC
    rung_count: int = 0
    content_snippet: str = ""          # first 1000 chars of rung text
    source_file: str = ""


class AOIRecord(BaseModel):
    name: str
    revision: str = "1.0"
    description: str = ""
    parameters: list[str] = Field(default_factory=list)
    source_file: str = ""


class IORecord(BaseModel):
    slot: str                          # e.g. "1:2" (rack:slot)
    rack: str = ""
    module: str = ""
    description: str = ""
    tag_name: str = ""
    source_file: str = ""


# ── Semantic chunk ────────────────────────────────────────────────────────────

class SemanticChunk(BaseModel):
    chunk_id: str                      # deterministic: sha1(project_id + source + offset)
    content: str
    source_file: str
    section_title: str = ""
    file_type: str = ""                # l5x | excel | pdf | txt
    page: int = 0
    project_id: str = ""


class ScoredChunk(BaseModel):
    chunk: SemanticChunk
    score: float
    retrieval_method: str = "vector"   # vector | bm25 | hybrid


# ── Ingestion ─────────────────────────────────────────────────────────────────

class IngestionResult(BaseModel):
    project_id: str
    project_hash: str
    folder: str
    files_scanned: int = 0
    files_indexed: int = 0
    files_failed: int = 0
    files_skipped: int = 0
    tags_indexed: int = 0
    routines_indexed: int = 0
    aois_indexed: int = 0
    io_rows_indexed: int = 0
    semantic_chunks_indexed: int = 0
    duration_ms: float = 0.0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ── Project status ────────────────────────────────────────────────────────────

class IndexState(str, Enum):
    UNLOADED = "UNLOADED"
    INDEXING = "INDEXING"
    READY    = "READY"
    STALE    = "STALE"
    FAILED   = "FAILED"


class ProjectStatus(BaseModel):
    project_id: str
    project_loaded: bool
    folder: str = ""
    project_hash: str = ""
    index_state: IndexState = IndexState.UNLOADED
    files_indexed: int = 0
    tags_indexed: int = 0
    routines_indexed: int = 0
    aois_indexed: int = 0
    io_rows_indexed: int = 0
    semantic_chunks: int = 0
    memory_footprint_mb: float = 0.0
    last_index_time: Optional[datetime] = None
    ingestion_duration_ms: float = 0.0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ── Project metrics ───────────────────────────────────────────────────────────

class ProjectMetrics(BaseModel):
    project_id: str
    embedding_count: int = 0
    vector_db_collection_size: int = 0
    structured_index_tags: int = 0
    structured_index_routines: int = 0
    memory_usage_mb: float = 0.0
    ingestion_duration_ms: float = 0.0
    last_index_time: Optional[datetime] = None


# ── Query classification ──────────────────────────────────────────────────────

class QueryType(str, Enum):
    TAG_LOOKUP          = "TAG_LOOKUP"
    IO_LOOKUP           = "IO_LOOKUP"
    ROUTINE_FLOW        = "ROUTINE_FLOW"
    SYSTEM_FLOW         = "SYSTEM_FLOW"
    DOCUMENTATION       = "DOCUMENTATION"
    COMMISSION_PROGRESS = "COMMISSION_PROGRESS"
    UNKNOWN             = "UNKNOWN"


class IntentType(str, Enum):
    FAULT_ANALYSIS = "FAULT_ANALYSIS"
    FILE_EXPLANATION = "FILE_EXPLANATION"
    SYSTEM_FLOW = "SYSTEM_FLOW"
    GENERAL_QUERY = "GENERAL_QUERY"


class QueryIntent(BaseModel):
    labels: list[QueryType]
    structured_required: bool
    semantic_required: bool
    progress_required: bool
    raw_query: str
    intent_type: str = IntentType.GENERAL_QUERY.value


# ── Query request & response ──────────────────────────────────────────────────

class ProjectQueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    project_id: str = Field(default="default")
    top_k: int = Field(default=5, ge=1, le=20)
    selected_files: list[str] = Field(default_factory=list)
    selected_folders: list[str] = Field(default_factory=list)
    scope_mode: Literal["STRICT", "PREFER", "GLOBAL"] = "GLOBAL"


class StructuredHit(BaseModel):
    hit_type: str                       # tag | io | routine | aoi
    data: dict[str, Any]


# ── Response Schemas ──────────────────────────────────────────────────────────

class FaultAnalysisResponseModel(BaseModel):
    summary: str
    root_causes: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"

class FileExplanationResponseModel(BaseModel):
    summary: str
    structure_breakdown: list[str] = Field(default_factory=list)
    key_fields_explained: list[str] = Field(default_factory=list)
    engineering_insight: str = ""
    examples: list[str] = Field(default_factory=list)
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"

class GeneralQueryResponseModel(BaseModel):
    explanation: str
    supporting_sources: list[str] = Field(default_factory=list)
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"


class ProjectQueryResponse(BaseModel):
    question: str
    project_id: str
    intent_type: str = IntentType.GENERAL_QUERY.value
    query_intent: QueryIntent
    structured_hits: list[StructuredHit] = Field(default_factory=list)
    semantic_sources: list[str] = Field(default_factory=list)
    answer: str
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    hallucinated_tags_removed: list[str] = Field(default_factory=list)
    prompt_version: str = "project_v1.0"
    llm_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    context_scope: dict[str, Any] = Field(default_factory=dict)
