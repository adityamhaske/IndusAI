"""
Embedding Provider Factory — creates per-user embedder instances from BYOK settings.

Usage:
    embedder = get_embedder_for_user(uid)
    vector = embedder.embed_text("some text")
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.interfaces.embedding_interface import EmbeddingInterface
from app.services.user_settings_service import UserSettingsService

logger = logging.getLogger(__name__)


class OpenAIEmbedder(EmbeddingInterface):
    """
    OpenAI text-embedding-3-small embedder.
    768-dimension output to match Gemini embeddings.
    """

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._dimension = 768  # Match Gemini embedding dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(
            input=text,
            model=self._model,
            dimensions=self._dimension,
        )
        return resp.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(
            input=texts,
            model=self._model,
            dimensions=self._dimension,
        )
        return [d.embedding for d in resp.data]

    def embed_query(self, query: str) -> list[float]:
        return self.embed_text(query)


def get_embedder_for_user(uid: str, svc: Optional[UserSettingsService] = None) -> EmbeddingInterface:
    """
    Create an embedding provider instance using the user's BYOK configuration.
    
    Falls back to Gemini embedder if no embedding-specific config is set.
    """
    if svc is None:
        svc = UserSettingsService()

    config = svc.get_provider_config(uid)
    emb_provider = config.get("embedding_provider")

    # Default: use same provider as LLM if embedding_provider not set
    if not emb_provider:
        emb_provider = config.get("llm_provider", "gemini")

    if emb_provider == "gemini":
        api_key = svc.get_raw_key(uid, "llm_api_key_enc")
        from app.embeddings.gemini_embedder import GeminiEmbedder
        embedder = GeminiEmbedder()
        # If user has a Gemini key, configure it
        if api_key:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
        return embedder

    elif emb_provider == "openai":
        api_key = svc.get_raw_key(uid, "embedding_api_key_enc")
        if not api_key:
            # Fall back to LLM key (OpenAI users typically use one key)
            api_key = svc.get_raw_key(uid, "llm_api_key_enc")
        if not api_key:
            raise ValueError("OpenAI API key is required for embeddings. Set it in Settings.")
        return OpenAIEmbedder(api_key=api_key)

    else:
        # Fallback to Gemini embedder
        from app.embeddings.gemini_embedder import GeminiEmbedder
        return GeminiEmbedder()
