"""
AIGatewayService — Thin routing layer for AI inference.

Stripped per architecture redesign:
  - Removed circuit breaker, speculative fallback, cost tracking
  - Removed rate limiting, SLA metrics, telemetry
  - Kept: provider routing, basic error handling, schema validation, fallback
"""
import logging
import time
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass

from jsonschema import validate, ValidationError

from app.core.interfaces.ai_provider import AIProvider
from app.models.ai_models import AIRequest, AIResponse

logger = logging.getLogger(__name__)


@dataclass
class FallbackPolicy:
    primary: str = "gemini"
    secondary: Optional[str] = None
    timeout_ms: int = 8000
    max_retries: int = 1
    json_enforced: bool = True


class AIGatewayService:
    """
    Lightweight orchestration layer for AI provider routing.
    Each user has one active provider (BYOK). No multi-provider fallback needed.
    """

    def __init__(
        self,
        providers: Dict[str, AIProvider] = None,
        fallback_policy: FallbackPolicy = None,
    ):
        self.providers = providers or {}
        self.policy = fallback_policy or FallbackPolicy()

        if self.providers:
            logger.info(
                "AIGateway initialized. Providers: %s | Primary: %s",
                list(self.providers.keys()),
                self.policy.primary,
            )
        else:
            logger.warning("AIGateway initialized with no providers.")

    def reload_providers(self, new_providers: Dict[str, AIProvider], new_policy: FallbackPolicy):
        """Hot-reload the provider registry and routing policy."""
        self.providers = new_providers
        self.policy = new_policy
        logger.info("AIGateway reloaded. Providers: %s", list(self.providers.keys()))

    def _invoke_provider(self, provider_id: str, request: AIRequest) -> AIResponse:
        """Call a provider and catch unhandled exceptions."""
        # Normalize legacy key aliases
        if provider_id == "local":
            provider_id = "local_ollama"

        provider = self.providers.get(provider_id)
        if not provider:
            registered = list(self.providers.keys())
            logger.error("Provider '%s' not found. Registered: %s", provider_id, registered)
            return AIResponse(
                raw_output="",
                model_name="unknown",
                provider_name=provider_id,
                success=False,
                error=f"Provider '{provider_id}' is not configured. Active providers: {registered}",
                error_type="PROVIDER_NOT_FOUND",
            )

        try:
            res = provider.generate(request)

            # Schema validation if requested
            if res.success and request.response_format == "json" and request.json_schema:
                res = self._normalize_schema(res, request.json_schema)

            return res
        except Exception as e:
            logger.exception("Provider %s leaked an unhandled exception", provider_id)
            return AIResponse(
                raw_output="",
                model_name="unknown",
                provider_name=provider_id,
                success=False,
                error=f"Provider exception: {str(e)}",
                error_type="UNKNOWN",
            )

    def _normalize_schema(self, response: AIResponse, schema: Dict[str, Any]) -> AIResponse:
        """Validate parsed JSON against a JSON Schema."""
        if not response.success or not response.parsed_output:
            return response

        try:
            validate(instance=response.parsed_output, schema=schema)
            return response
        except ValidationError as e:
            logger.warning("Schema validation failed: %s", e.message)
            response.success = False
            response.error = f"SCHEMA_VALIDATION_FAILED: {e.message}"
            response.error_type = "PARSE"
            response.parsed_output = None
            return response

    def execute(
        self,
        request: AIRequest,
        retrieval_coverage_score: Optional[float] = None,
        retrieval_chunk_count: int = 0,
    ) -> AIResponse:
        """
        Main entry point for AI inference.
        Routes to the primary provider; falls back to secondary if configured.
        """
        t_start = time.perf_counter()
        primary_id = self.policy.primary

        # Zero-chunk RAG interception
        if retrieval_chunk_count == 0 or (
            retrieval_coverage_score is not None and retrieval_coverage_score == 0.0
        ):
            request.prompt += "\n\nSYSTEM OVERRIDE: Limited retrieval context available. Provide generalized analysis."

        # Attempt primary
        response = self._invoke_provider(primary_id, request)

        # Retry once if failed
        if not response.success and self.policy.max_retries > 0:
            logger.warning("Primary '%s' failed [%s]: %s. Retrying...", primary_id, response.error_type, response.error)
            response = self._invoke_provider(primary_id, request)

        # Fallback to secondary if still failed
        if not response.success and self.policy.secondary and self.policy.secondary in self.providers:
            logger.warning("Primary exhausted. Falling back to '%s'", self.policy.secondary)
            response = self._invoke_provider(self.policy.secondary, request)

        total_ms = int((time.perf_counter() - t_start) * 1000)
        status = "SUCCESS" if response.success else f"FAILED [{response.error_type}]"
        logger.info(
            "AIGateway | %s | %s | %dms | Error: %s",
            status, response.provider_name, total_ms, response.error,
        )
        return response

    def get_health(self) -> Dict[str, Any]:
        """Basic health diagnostics."""
        return {
            "status": "OPERATIONAL" if self.providers else "NO_PROVIDERS",
            "primary_provider": self.policy.primary,
            "secondary_provider": self.policy.secondary,
            "registered_providers": list(self.providers.keys()),
        }
