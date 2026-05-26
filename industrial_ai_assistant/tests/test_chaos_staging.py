"""
Chaos staging tests — adapted for thin routing layer.
Tests: cascading failures, fallback behavior, error propagation.
"""
import pytest
from app.models.ai_models import AIRequest, AIResponse
from app.services.ai_gateway import AIGatewayService, FallbackPolicy
from app.core.interfaces.ai_provider import AIProvider


class _ChaosMockProvider(AIProvider):
    def __init__(self, mode: str, name: str = "chaos"):
        self._name = name
        self.mode = mode

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def provider_type(self) -> str:
        return "cloud"

    def generate(self, req: AIRequest) -> AIResponse:
        if self.mode == "timeout":
            raise TimeoutError(f"Simulated {self._name} connection timeout.")
        if self.mode == "network_drop":
            raise ConnectionError(f"Simulated {self._name} network drop.")
        if self.mode == "schema_drift":
            return AIResponse(
                raw_output='{"invalid": true}',
                success=True, error=None,
                model_name=self._name, provider_name=self._name
            )

        return AIResponse(
            raw_output="OK", success=True, error=None,
            model_name=self._name, provider_name=self._name
        )


@pytest.fixture
def chaos_gateway():
    policy = FallbackPolicy(primary="local", secondary="openai")
    return AIGatewayService(
        providers={
            "local": _ChaosMockProvider(mode="timeout", name="local"),
            "openai": _ChaosMockProvider(mode="network_drop", name="openai"),
            "gemini": _ChaosMockProvider(mode="schema_drift", name="gemini"),
        },
        fallback_policy=policy,
    )


def test_cascading_failure_returns_error(chaos_gateway):
    """Primary times out → secondary drops network → error returned."""
    req = AIRequest(prompt="Test", response_format="text")
    res = chaos_gateway.execute(req)

    # Both primary and secondary fail — result should be unsuccessful
    assert res.success is False
    assert res.error is not None


def test_all_providers_fail_gracefully(chaos_gateway):
    """Even with all providers failing, gateway returns clean error, never crashes."""
    req = AIRequest(prompt="Test", response_format="text")
    res = chaos_gateway.execute(req)
    assert isinstance(res, AIResponse)
    assert res.success is False
