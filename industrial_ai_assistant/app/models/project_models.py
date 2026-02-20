"""
Pydantic v2 models for the Project Knowledge Engine.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


# ── Structured index records ───────────────────────────────────────────────────

class TagRecord(BaseModel):
    name: str
    data_type: str = ""
    tag_type: str = ""          # Base | Alias | Produced | Consumed
    scope: str = "Controller"   # Controller | Program:<name>
    description: str = ""
    value: str = ""
    source_file: str = ""


class RoutineRecord(BaseModel):
    name: str
    program: str = ""
    routine_type: str = ""       # RLL | ST | FBD | SFC
    rung_count: int = 0
    content: str = ""            # rung text (truncated at 8 KB)
    source_file: str = ""


class AOIRecord(BaseModel):
    name: str
    description: str = ""
    revision: str = ""
    parameters: List[str] = Field(default_factory=list)
    source_file: str = ""


class IORecord(BaseModel):
    slot: str = ""
    rack: str = ""
    module: str = ""
    description: str = ""
    channel: str = ""
    tag_name: str = ""
    source_file: str = ""

    @property
    def key(self) -> str:
        return f"{self.rack}/{self.slot}".strip("/")


# ── Semantic chunk ─────────────────────────────────────────────────────────────

class SemanticChunk(BaseModel):
    chunk_id: str
    project_id: str
    content: str
    source_file: str
    section_title: str = ""
    file_type: str = ""           # l5x | excel | pdf | txt
    page: Optional[int] = None
    char_offset: Optional[int] = None


# ── Query intent (multi-label) ─────────────────────────────────────────────────

QueryLabel = Literal[
    "TAG_LOOKUP",
    "IO_LOOKUP",
    "ROUTINE_FLOW",
    "SYSTEM_FLOW",
    "DOCUMENTATION",
    "COMMISSION_PROGRESS",
    "UNKNOWN",
]


class QueryIntent(BaseModel):
    structured_required: bool = False
    semantic_required: bool = False
    progress_required: bool = False
    labels: List[QueryLabel] = Field(default_factory=list)


# ── Ingestion ──────────────────────────────────────────────────────────────────

class IngestionResult(BaseModel):
    project_id: str
    folder: str
    project_hash: str
    files_scanned: int = 0
    files_indexed: int = 0
    files_failed: int = 0
    tags_indexed: int = 0
    routines_indexed: int = 0
    aois_indexed: int = 0
    io_rows_indexed: int = 0
    semantic_chunks: int = 0
    duration_s: float = 0.0
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ── Project status ─────────────────────────────────────────────────────────────

class ProjectStatus(BaseModel):
    project_id: str
    project_loaded: bool = False
    folder: str = ""
    project_hash: str = ""
    index_stale: bool = False
    files_indexed: int = 0
    tags_indexed: int = 0
    routines_indexed: int = 0
    aois_indexed: int = 0
    io_rows_indexed: int = 0
    semantic_chunks: int = 0
    memory_mb: float = 0.0
    last_index_time: Optional[datetime] = None
    ingestion_running: bool = False
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


# ── Project metrics ────────────────────────────────────────────────────────────

class ProjectMetrics(BaseModel):
    project_id: str
    structured_memory_mb: float = 0.0
    semantic_chunk_count: int = 0
    vector_collection_size: int = 0
    ingestion_duration_s: float = 0.0
    tags: int = 0
    routines: int = 0
    aois: int = 0
    io_rows: int = 0


# ── Query API ──────────────────────────────────────────────────────────────────

class ProjectQueryRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Engineering question about the project")
    project_id: str = Field(default="default")


class StructuredHit(BaseModel):
    type: str                    # tag | routine | io | aoi
    name: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ProjectQueryResponse(BaseModel):
    project_id: str
    question: str
    summary: str
    reasoning: str = ""
    structured_hits: List[StructuredHit] = Field(default_factory=list)
    documentation_sources: List[str] = Field(default_factory=list)
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    prompt_version: str = "project_v1.0"
    hallucinated_tags_rejected: List[str] = Field(default_factory=list)
    query_labels: List[str] = Field(default_factory=list)
    llm_latency_ms: float = 0.0


# ── Ingest request ─────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    folder_path: str = Field(..., description="Absolute path to the project folder to index")
    project_id: str = Field(default="default", description="Unique project identifier")
