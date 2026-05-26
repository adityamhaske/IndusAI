"""
User Settings Service — BYOK API key management.

Stores encrypted API keys and provider preferences in Firestore
at /users/{uid}/settings/provider.

Public methods:
    get_settings(uid)     → dict (keys masked)
    save_settings(uid, …) → dict (keys masked)
    get_raw_key(uid, key_name) → plaintext key (internal use only)
"""
from __future__ import annotations

import logging
from typing import Optional

from app.storage.firestore_client import FirestoreClient, get_firestore
from app.services.encryption import encrypt, decrypt

logger = logging.getLogger(__name__)

# Supported providers
SUPPORTED_LLM_PROVIDERS = ("gemini", "openai", "deepseek", "ollama")
SUPPORTED_EMBEDDING_PROVIDERS = ("gemini", "openai")


def _mask(key: str) -> str:
    """Mask an API key for safe display: show first 4 + last 4 chars."""
    if not key or len(key) < 12:
        return "****"
    return f"{key[:4]}…{key[-4:]}"


class UserSettingsService:
    def __init__(self, db: Optional[FirestoreClient] = None):
        self._db = db or get_firestore()

    # ── Read ──────────────────────────────────────────────────────────────

    def get_settings(self, uid: str) -> dict:
        """Return user settings with keys masked."""
        doc = self._db.get_document(f"users/{uid}/settings", "provider")
        if not doc:
            return {
                "llm_provider": None,
                "llm_model": None,
                "embedding_provider": None,
                "ollama_url": None,
                "has_llm_key": False,
                "has_embedding_key": False,
                "llm_key_preview": None,
                "embedding_key_preview": None,
            }

        # Decrypt keys just to produce masked preview
        llm_key_enc = doc.get("llm_api_key_enc", "")
        emb_key_enc = doc.get("embedding_api_key_enc", "")

        llm_key_plain = ""
        emb_key_plain = ""
        try:
            if llm_key_enc:
                llm_key_plain = decrypt(llm_key_enc)
        except Exception:
            pass
        try:
            if emb_key_enc:
                emb_key_plain = decrypt(emb_key_enc)
        except Exception:
            pass

        return {
            "llm_provider": doc.get("llm_provider"),
            "llm_model": doc.get("llm_model"),
            "embedding_provider": doc.get("embedding_provider"),
            "ollama_url": doc.get("ollama_url"),
            "has_llm_key": bool(llm_key_enc),
            "has_embedding_key": bool(emb_key_enc),
            "llm_key_preview": _mask(llm_key_plain) if llm_key_plain else None,
            "embedding_key_preview": _mask(emb_key_plain) if emb_key_plain else None,
        }

    # ── Write ─────────────────────────────────────────────────────────────

    def save_settings(
        self,
        uid: str,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        embedding_provider: Optional[str] = None,
        embedding_api_key: Optional[str] = None,
        ollama_url: Optional[str] = None,
    ) -> dict:
        """Persist user provider settings. Returns masked view."""
        if llm_provider and llm_provider not in SUPPORTED_LLM_PROVIDERS:
            raise ValueError(f"Unsupported LLM provider: {llm_provider}. Choose from {SUPPORTED_LLM_PROVIDERS}")
        if embedding_provider and embedding_provider not in SUPPORTED_EMBEDDING_PROVIDERS:
            raise ValueError(f"Unsupported embedding provider: {embedding_provider}. Choose from {SUPPORTED_EMBEDDING_PROVIDERS}")

        # Build update payload — only set fields that were provided
        update: dict = {}
        if llm_provider is not None:
            update["llm_provider"] = llm_provider
        if llm_model is not None:
            update["llm_model"] = llm_model
        if llm_api_key is not None:
            update["llm_api_key_enc"] = encrypt(llm_api_key)
        if embedding_provider is not None:
            update["embedding_provider"] = embedding_provider
        if embedding_api_key is not None:
            update["embedding_api_key_enc"] = encrypt(embedding_api_key)
        if ollama_url is not None:
            update["ollama_url"] = ollama_url

        if not update:
            return self.get_settings(uid)

        self._db.set_document(f"users/{uid}/settings", "provider", update, merge=True)
        logger.info("Saved provider settings for uid=%s provider=%s", uid, llm_provider)
        return self.get_settings(uid)

    # ── Internal: raw key retrieval for factory ────────────────────────────

    def get_raw_key(self, uid: str, key_name: str = "llm_api_key_enc") -> Optional[str]:
        """Decrypt and return a raw API key. For internal factory use only."""
        doc = self._db.get_document(f"users/{uid}/settings", "provider")
        if not doc:
            return None
        enc = doc.get(key_name, "")
        if not enc:
            return None
        try:
            return decrypt(enc)
        except Exception:
            logger.warning("Failed to decrypt %s for uid=%s", key_name, uid)
            return None

    def get_provider_config(self, uid: str) -> dict:
        """Return raw provider config (provider name, model, ollama url) without keys."""
        doc = self._db.get_document(f"users/{uid}/settings", "provider")
        if not doc:
            return {}
        return {
            "llm_provider": doc.get("llm_provider"),
            "llm_model": doc.get("llm_model"),
            "embedding_provider": doc.get("embedding_provider"),
            "ollama_url": doc.get("ollama_url"),
        }
