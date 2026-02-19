"""
Typed exceptions for LLM and RAG connectivity failures.
These are raised explicitly — no silent fallback allowed.
"""
from app.core.exceptions import AppError


class LLMConnectionError(AppError):
    """Raised when the LLM service is unreachable."""
    error_type = "LLM_NOT_CONNECTED"

    def __init__(self, message: str = "Local LLM is not reachable. Please start Ollama."):
        super().__init__(message, status_code=503)


class RAGConnectionError(AppError):
    """Raised when the RAG retriever or vector store is unreachable."""
    error_type = "RAG_NOT_INITIALIZED"

    def __init__(self, message: str = "RAG retriever is not initialized."):
        super().__init__(message, status_code=503)


class LLMResponseParseError(AppError):
    """Raised when LLM response cannot be parsed into the expected schema."""
    error_type = "LLM_RESPONSE_INVALID"

    def __init__(self, message: str = "LLM returned an invalid structured response."):
        super().__init__(message, status_code=502)

