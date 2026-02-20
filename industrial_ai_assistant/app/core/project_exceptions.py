"""
Project Knowledge Engine — Custom exceptions.
All exceptions are explicitly raised; no silent fallback.
"""
from app.core.exceptions import AppError


class ProjectNotReadyError(AppError):
    error_type = "PROJECT_NOT_READY"

    def __init__(self, message: str = "Project ingestion not completed. POST /api/project/ingest first."):
        super().__init__(message, status_code=503)


class IngestionAlreadyRunningError(AppError):
    error_type = "INGESTION_ALREADY_RUNNING"

    def __init__(self, project_id: str = ""):
        super().__init__(
            f"Ingestion already running for project '{project_id}'. Wait for it to complete.",
            status_code=409,
        )


class HallucinatedTagError(AppError):
    error_type = "HALLUCINATED_TAG"

    def __init__(self, tags: list):
        self.tags = tags
        super().__init__(
            f"LLM invented PLC tags not found in structured index: {tags}",
            status_code=422,
        )


class ProjectNotFoundError(AppError):
    error_type = "PROJECT_NOT_FOUND"

    def __init__(self, project_id: str = ""):
        super().__init__(f"Project '{project_id}' has not been ingested.", status_code=404)


class ProjectIndexStaleError(AppError):
    error_type = "PROJECT_INDEX_STALE"
    reindex_required = True

    def __init__(self, project_id: str = ""):
        super().__init__(
            f"Project '{project_id}' index is stale — source files changed. "
            "Re-run POST /api/project/ingest.",
            status_code=409,
        )


class IngestionFailedError(AppError):
    error_type = "INGESTION_FAILED"

    def __init__(self, message: str):
        super().__init__(message, status_code=500)
