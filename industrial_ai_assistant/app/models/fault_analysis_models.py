"""
Extended Pydantic models for the v2 Fault Analysis response.
These supplement (not replace) fault_models.py.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class RetrievedDoc(BaseModel):
    """A single document chunk returned from RAG retrieval."""
    source_file: str
    section_title: Optional[str] = None
    page_number: Optional[int] = None
    content: str
    relevance_score: Optional[float] = None


class StructuredLLMOutput(BaseModel):
    """
    Schema the LLM must return (strict JSON).
    Backend parses, validates, and rejects/retries if malformed.
    """
    fault_summary: str
    root_cause: str
    trigger_mechanism: str
    resolution_steps: List[str]
    confidence: str


class FlexibleLLMOutput(BaseModel):
    """
    Flexible schema for non-fault intents (e.g. general questions or document summaries).
    """
    summary: str
    key_points: List[str]
    confidence: str


class FaultAnalysisV2Response(BaseModel):
    """Full enriched fault analysis response (v2)."""
    analysis_version: str = "v2.0"
    dataset_hash: str
    row_id: int
    fault_code: str
    device: str
    timestamp: datetime
    user_question: Optional[str] = None

    # Deterministic (never computed by LLM)
    confidence: str                       # LOW / MEDIUM / HIGH
    # Original Deterministic Stats (kept for backend tracking)
    statistics: Dict[str, Any]

    # New Minimal UI Schema mapped from LLM + Stats
    fault_summary: str
    root_cause: str
    trigger_mechanism: str
    resolution_steps: List[str]
    confidence: str

    # RAG sources
    docs_used: int
    sources: List[RetrievedDoc]

    # Validation
    hallucinated_tags_removed: List[str] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)

    # Observability
    llm_latency_ms: float
    rag_latency_ms: float
    total_latency_ms: float


class FaultAnalysisRequest(BaseModel):
    """Updated analyze request — now includes optional custom question."""
    row_id: int
    project_id: str = "default"
    question: Optional[str] = None        # If None → default analysis

class QuickStatsResponse(BaseModel):
    """Instant deterministic statistical response for UI dual-engine view."""
    occurrences_last_hour: Optional[int] = 0
    occurrences_last_24h: Optional[int] = 0
    top_cooccurring_fault: Optional[str] = None
    cooccurrence_count: Optional[int] = 0
    burst_detected: Optional[bool] = False
    burst_description: Optional[str] = ""
    burst_count: Optional[int] = 0
    confidence: Optional[str] = "MEDIUM"
    rolling_avg_5m: Optional[float] = None
    rolling_avg_1h: Optional[float] = None
    delta_last_30m: Optional[float] = None
    anomaly_score: Optional[float] = None
    trend: Optional[str] = "STABLE"
    integrity_passed: Optional[bool] = True
