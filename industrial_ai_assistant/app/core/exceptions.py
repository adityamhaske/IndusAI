class AppError(Exception):
    """Base exception for the application."""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

class ConfigurationError(AppError):
    """Raised when there is a configuration issue."""
    def __init__(self, message: str):
        super().__init__(message, status_code=500)

class LLMGenerationError(AppError):
    """Raised when the LLM fails to generate a response."""
    def __init__(self, message: str):
        super().__init__(message, status_code=502)

class VectorStoreError(AppError):
    """Raised when the vector store operation fails."""
    def __init__(self, message: str):
        super().__init__(message, status_code=503)

class RetriverError(AppError):
    """Raised when retrieval fails."""
    def __init__(self, message: str):
        super().__init__(message, status_code=500)

class ValidationError(AppError):
    """Raised when data validation fails (e.g., hallucination check)."""
    def __init__(self, message: str):
        super().__init__(message, status_code=422)
