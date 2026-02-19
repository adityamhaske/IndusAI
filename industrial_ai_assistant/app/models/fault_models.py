"""
Explicit Pydantic data contracts for the PLC Fault System.
Never use loose dicts in API responses — always use these models.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class FaultRecord(BaseModel):
    """Single normalized fault row. Exact schema contract."""
    row_id: int
    fault_code: str
    timestamp: datetime
    device: str
    message: str
    severity: Optional[str] = None


class UploadResponse(BaseModel):
    total_rows: int
    sampled: bool = False
    sample_limit: Optional[int] = None
    columns: List[str]
    preview: List[Dict[str, Any]]   # First 10 rows as dicts
    source_filename: str
    dataset_hash: str
    parse_duration_ms: float
    stats_duration_ms: float
    warnings: List[str] = []


class FaultListResponse(BaseModel):
    total_rows: int
    page: int
    size: int
    total_pages: int
    rows: List[Dict[str, Any]]


class FaultSummaryResponse(BaseModel):
    total_rows: int
    unique_fault_codes: int
    most_common_fault: str
    most_common_count: int
    time_range_start: Optional[datetime]
    time_range_end: Optional[datetime]
    top_devices: List[Dict[str, Any]]        # [{device, count}]
    fault_frequency_per_hour: Dict[str, int] # {HH:00 -> count}
    burst_detected: bool
    max_burst_window_description: Optional[str]
    dataset_hash: str


class FaultDetailResponse(BaseModel):
    row: FaultRecord
    occurrences_last_hour: int
    occurrences_last_24h: int
    previous_occurrences: List[FaultRecord]  # Up to 10 prior rows, same code
    top_cooccurring_fault: Optional[str]
    cooccurrence_count: int


class AnalysisRequest(BaseModel):
    row_id: int
    project_id: str = "default"


class FaultAnalysisResponse(BaseModel):
    analysis_version: str = "v1.0"
    dataset_hash: str
    row_id: int
    fault_code: str
    device: str
    timestamp: datetime
    confidence: str                          # LOW / MEDIUM / HIGH — deterministic
    summary: str
    likely_causes: List[str]
    resolution_steps: List[Dict[str, str]]   # [{title, description}]
    related_tags: List[str]
    limitations: Optional[str] = None
    statistics: Dict[str, Any]
    llm_duration_ms: float


class FaultMetricsResponse(BaseModel):
    dataset_loaded: bool
    row_count: int = 0
    memory_mb: float = 0.0
    source_filename: Optional[str] = None
    created_at: Optional[datetime] = None
    parse_duration_ms: Optional[float] = None
    stats_duration_ms: Optional[float] = None
    dataset_hash: Optional[str] = None


class ErrorResponse(BaseModel):
    error_type: str
    message: str
    details: Optional[Dict[str, Any]] = None
