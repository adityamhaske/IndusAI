"""
Exceptions for the Project Knowledge Engine.
All are explicit — no silent fallback anywhere in the pipeline.
"""
from app.core.exceptions import AppError


class ProjectNotReadyError(AppError):
    """Project folder has not been indexed yet."""
    error_type = "PROJECT_NOT_READY"

    def __init__(self, project_id: str = ""):
        msg = (
            f"Project '{project_id}' has not been indexed. "
            "POST /api/project/ingest first."
        )
        super().__init__(msg, status_code=412)


class ProjectStaleError(AppError):
    """Project folder content changed — re-ingestion required."""
    error_type = "PROJECT_STALE"

    def __init__(self, project_id: str = ""):
        msg = (
            f"Project '{project_id}' index is stale (folder contents changed). "
            "POST /api/project/ingest to rebuild the index."
        )
        super().__init__(msg, status_code=409)


class IngestionLockError(AppError):
    """Ingestion already running for this project."""
    error_type = "INGESTION_IN_PROGRESS"

    def __init__(self, project_id: str = ""):
        super().__init__(
            f"Ingestion already running for project '{project_id}'. Try again later.",
            status_code=409,
        )


class IngestionFailedError(AppError):
    """A parser crashed during ingestion."""
    error_type = "INGESTION_FAILED"

    def __init__(self, message: str = "Ingestion failed."):
        super().__init__(message, status_code=500)


class HallucinatedTagError(AppError):
    """LLM invented PLC tag names not present in the structured index."""
    error_type = "HALLUCINATED_TAGS"

    def __init__(self, tags: list[str]):
        super().__init__(
            f"LLM response contains hallucinated PLC tags: {tags}. "
            "Response rejected.",
            status_code=422,
        )
        self.tags = tags


class ProjectNotFoundError(AppError):
    """No project registered under this project_id."""
    error_type = "PROJECT_NOT_FOUND"

    def __init__(self, project_id: str = ""):
        super().__init__(
            f"No project registered as '{project_id}'.",
            status_code=404,
        )
