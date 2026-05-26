import os
import google.generativeai as genai
from typing import List, Union
from app.core.interfaces.embedding_interface import EmbeddingInterface

class GeminiEmbedder(EmbeddingInterface):
    """
    Drop-in replacement for SentenceTransformers.
    Uses Gemini Embeddings API — free, no local model download.
    """

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
        self.model = "models/text-embedding-004"
        self._dimension = 768

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> List[float]:
        """Embed a single string. Returns a list of floats."""
        result = genai.embed_content(
            model=self.model,
            content=text,
            task_type="retrieval_document"
        )
        return result["embedding"]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of strings."""
        result = genai.embed_content(
            model=self.model,
            content=texts,
            task_type="retrieval_document"
        )
        return result["embedding"]

    def embed_query(self, query: str) -> List[float]:
        """Embed a query string (different task type for better retrieval)."""
        result = genai.embed_content(
            model=self.model,
            content=query,
            task_type="retrieval_query"
        )
        return result["embedding"]
