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
    summary: str
    likely_causes: List[str] = Field(default_factory=list)
    diagnostic_steps: List[str] = Field(default_factory=list)
    preventive_actions: List[str] = Field(default_factory=list)
    related_plc_tags: List[str] = Field(default_factory=list)
    confidence_explanation: str = ""


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
    statistics: Dict[str, Any]

    # LLM output
    summary: str
    likely_causes: List[str]
    diagnostic_steps: List[str]
    preventive_actions: List[str]
    related_plc_tags: List[str]
    confidence_explanation: str

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
