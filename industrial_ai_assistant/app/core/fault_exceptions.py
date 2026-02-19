"""
Typed exception hierarchy for the PLC Fault System.
All fault-domain errors extend AppError for unified handling.
"""
from app.core.exceptions import AppError


class FaultSchemaError(AppError):
    """Raised when the CSV does not match the required schema.
    e.g., missing required columns, unparseable timestamps."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}


class FaultTooLargeError(AppError):
    """Raised when the uploaded file exceeds size or row limits."""
    def __init__(self, message: str):
        super().__init__(message)


class FaultParsingError(AppError):
    """Raised when the CSV cannot be parsed (corrupt file, encoding)."""
    def __init__(self, message: str):
        super().__init__(message)


class DatasetNotLoadedError(AppError):
    """Raised when an operation requires a dataset that hasn't been uploaded."""
    def __init__(self):
        super().__init__("No dataset loaded. Please upload a fault CSV first.")


class DatasetHashMismatchError(AppError):
    """Raised when the request references a stale or different dataset."""
    def __init__(self):
        super().__init__("Dataset has changed. Please re-upload or refresh.")


class FaultRowNotFoundError(AppError):
    """Raised when a requested row_id does not exist in the dataset."""
    def __init__(self, row_id: int):
        super().__init__(f"Row ID {row_id} not found in active dataset.")


class AnalysisPrerequisiteError(AppError):
    """Raised when LLM analysis prerequisites are not met."""
    def __init__(self, reason: str):
        super().__init__(f"Analysis prerequisites not met: {reason}")
