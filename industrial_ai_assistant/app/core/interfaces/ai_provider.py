from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from app.models.ai_models import AIRequest, AIResponse

class AIProvider(ABC):
    """
    Enterprise abstraction for an AI Model Provider (Local, Cloud, API).
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g., 'local_ollama', 'openai', 'gemini')"""
        pass

    @abstractmethod
    def generate(self, request: AIRequest) -> AIResponse:
        """
        Execute an AI Request.
        
        Must return an AIResponse containing raw string, parsed json (if requested),
        token counts, and latency, OR explicitly trap errors returning success=False.
        """
        pass
