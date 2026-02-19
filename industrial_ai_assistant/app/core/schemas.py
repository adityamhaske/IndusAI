from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    query: str
    project_id: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    summary: str = Field(..., description="A concise summary of the issue or answer.")
    likely_causes: List[str] = Field(default_factory=list, description="List of potential causes for the issue.")
    resolution_steps: List[str] = Field(default_factory=list, description="Step-by-step resolution guide.")
    related_tags: List[str] = Field(default_factory=list, description="Tags related to the equipment or fault.")
    formulas: List[str] = Field(default_factory=list, description="Mathematical formulas relevant to the solution.")
    source_sections: List[str] = Field(default_factory=list, description="References to the documents used.")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score of the answer.")
    limitations: str = Field(..., description="Any limitations or caveats of the provided answer.")

class ChunkMetadata(BaseModel):
    source_file: str
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    chunk_id: str
    project_id: Optional[str] = None    # for cross-project contamination prevention

class DocumentChunk(BaseModel):
    content: str
    metadata: ChunkMetadata
    embedding: Optional[List[float]] = None

class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str
    module: str

class ProjectInfo(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    files: List[str] = []

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None
