"""
LLM Provider Factory — creates per-user LLM provider instances from BYOK settings.

Usage:
    provider = get_llm_for_user(uid)
    response = provider.generate(request)
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.interfaces.ai_provider import AIProvider
from app.services.user_settings_service import UserSettingsService

logger = logging.getLogger(__name__)

# Default models per provider
DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "ollama": "mistral",
}


def get_llm_for_user(uid: str, svc: Optional[UserSettingsService] = None) -> AIProvider:
    """
    Create an LLM provider instance using the user's BYOK configuration.
    
    Raises ValueError if the user has not configured a provider or key.
    """
    if svc is None:
        svc = UserSettingsService()

    config = svc.get_provider_config(uid)
    provider_name = config.get("llm_provider")
    model = config.get("llm_model")

    if not provider_name:
        raise ValueError(
            "No LLM provider configured. Go to Settings → AI Provider to set up your API key."
        )

    api_key = svc.get_raw_key(uid, "llm_api_key_enc")

    if provider_name == "gemini":
        from app.ai_providers.gemini_provider import GeminiProvider
        return GeminiProvider(
            api_key=api_key or "",
            model=model or DEFAULT_MODELS["gemini"],
        )

    elif provider_name == "openai":
        from app.ai_providers.openai_provider import OpenAIProvider
        if not api_key:
            raise ValueError("OpenAI API key is required. Set it in Settings → AI Provider.")
        return OpenAIProvider(
            api_key=api_key,
            model=model or DEFAULT_MODELS["openai"],
        )

    elif provider_name == "deepseek":
        # DeepSeek uses OpenAI-compatible API
        from app.ai_providers.openai_provider import OpenAIProvider
        if not api_key:
            raise ValueError("DeepSeek API key is required. Set it in Settings → AI Provider.")
        provider = OpenAIProvider(
            api_key=api_key,
            model=model or DEFAULT_MODELS["deepseek"],
        )
        # Override base URL to DeepSeek
        provider.base_url = "https://api.deepseek.com/v1/chat/completions"
        provider._sync_client = None  # Force re-creation with new URL
        import httpx
        provider._sync_client = httpx.Client(
            base_url="https://api.deepseek.com",
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            timeout=30.0,
        )
        return provider

    elif provider_name == "ollama":
        from app.ai_providers.local_ollama_provider import LocalOllamaProvider
        ollama_url = config.get("ollama_url", "http://localhost:11434")
        return LocalOllamaProvider(
            base_url=ollama_url,
            model=model or DEFAULT_MODELS["ollama"],
        )

    else:
        raise ValueError(f"Unsupported LLM provider: {provider_name}")
