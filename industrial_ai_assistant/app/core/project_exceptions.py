"""
Project-specific exceptions.
All inherit from AppError for consistent HTTP status mapping.
"""
from app.core.exceptions import AppError
from typing import List


class ProjectNotReadyError(AppError):
    """Raised when a query is attempted before ingestion is complete."""
    error_type = "PROJECT_NOT_READY"

    def __init__(self, project_id: str = "default"):
        super().__init__(
            f"Project '{project_id}' ingestion is not complete. "
            "Run POST /api/project/ingest first.",
            status_code=503,
        )


class IngestionError(AppError):
    """Raised when the ingestion pipeline encounters a fatal failure."""
    error_type = "INGESTION_ERROR"

    def __init__(self, message: str):
        super().__init__(message, status_code=500)


class TagHallucinationError(AppError):
    """Raised when LLM output references PLC tags not present in the StructuredIndex."""
    error_type = "TAG_HALLUCINATION"

    def __init__(self, invented_tags: List[str]):
        self.invented_tags = invented_tags
        super().__init__(
            f"LLM invented PLC tag(s) not in structured index: {invented_tags}. "
            "Response rejected.",
            status_code=422,
        )
