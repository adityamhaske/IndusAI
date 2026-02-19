"""
Pydantic models for the Project Knowledge Engine.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Structured PLC entities ───────────────────────────────────────────────────

class TagRecord(BaseModel):
    name: str
    data_type: str = ""
    description: str = ""
    scope: str = "Controller"          # Controller | Program name
    external_access: str = "Read/Write"
    value: Optional[str] = None
    source_file: str = ""


class RoutineRecord(BaseModel):
    name: str
    program_name: str = ""
    type: str = "LAD"                  # LAD | FBD | SFC | ST
    description: str = ""
    rung_count: int = 0
    source_file: str = ""


class AOIRecord(BaseModel):
    name: str
    description: str = ""
    parameters: List[Dict[str, str]] = Field(default_factory=list)
    source_file: str = ""


class IORecord(BaseModel):
    slot: str                          # e.g. "1:2:0"
    rack: str = ""
    module_type: str = ""
    channel: str = ""
    tag_name: str = ""
    description: str = ""
    source_file: str = ""


# ── Ingestion metrics ─────────────────────────────────────────────────────────

class FileIngestionResult(BaseModel):
    file_path: str
    file_type: str
    success: bool
    tags_extracted: int = 0
    routines_extracted: int = 0
    aois_extracted: int = 0
    io_rows_extracted: int = 0
    semantic_chunks: int = 0
    error: Optional[str] = None
    duration_ms: float = 0.0


class IngestionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


# ── API shapes ────────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    project_id: str = "default"
    folder_path: str


class ProjectStatusResponse(BaseModel):
    project_id: str
    project_loaded: bool
    folder: Optional[str] = None
    status: IngestionStatus = IngestionStatus.PENDING
    files_indexed: int = 0
    tags_indexed: int = 0
    routines_indexed: int = 0
    aois_indexed: int = 0
    io_rows_indexed: int = 0
    semantic_chunks: int = 0
    last_index_time: Optional[datetime] = None
    errors: List[str] = Field(default_factory=list)


class ProjectQueryRequest(BaseModel):
    project_id: str = "default"
    query: str
    top_k_semantic: int = Field(default=5, ge=1, le=20)


class StructuredMatch(BaseModel):
    match_type: str        # tag | routine | io | aoi
    data: Dict[str, Any]


class ProjectQueryResponse(BaseModel):
    project_id: str
    query: str
    query_type: str
    structured_matches: List[StructuredMatch] = Field(default_factory=list)
    semantic_sources: List[str] = Field(default_factory=list)
    answer: str
    tags_referenced: List[str] = Field(default_factory=list)
    confidence: str = "LOW"
    llm_latency_ms: float = 0.0
