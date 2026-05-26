"""
Resilience tests — adapted for thin routing layer.
Circuit breaker, cost guard, and rate limiting were removed per architecture redesign.
Tests now verify basic failure handling and fallback behavior.
"""
import pytest
from app.models.ai_models import AIRequest, AIResponse
from app.services.ai_gateway import AIGatewayService, FallbackPolicy
from app.core.interfaces.ai_provider import AIProvider


class FailingProvider(AIProvider):
    def __init__(self, name: str = "failing"):
        self._name = name
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def provider_type(self) -> str:
        return "local"

    def generate(self, req: AIRequest) -> AIResponse:
        self.call_count += 1
        raise TimeoutError("Test timeout")


class SucceedingProvider(AIProvider):
    def __init__(self, name: str = "good"):
        self._name = name
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def provider_type(self) -> str:
        return "cloud"

    def generate(self, req: AIRequest) -> AIResponse:
        self.call_count += 1
        return AIResponse(
            raw_output="OK", success=True, error=None,
            model_name=self._name, provider_name=self._name
        )


def test_repeated_failures_still_handled():
    """Even after many failures, gateway returns clean error responses."""
    failing = FailingProvider("primary")
    gw = AIGatewayService(
        providers={"primary": failing},
        fallback_policy=FallbackPolicy(primary="primary"),
    )
    req = AIRequest(prompt="Test", response_format="text")

    for _ in range(10):
        res = gw.execute(req)
        assert res.success is False
        assert res.error is not None

    assert failing.call_count >= 10


def test_fallback_after_primary_timeout():
    """Primary times out, secondary succeeds."""
    primary = FailingProvider("primary")
    secondary = SucceedingProvider("secondary")

    gw = AIGatewayService(
        providers={"primary": primary, "secondary": secondary},
        fallback_policy=FallbackPolicy(primary="primary", secondary="secondary"),
    )

    req = AIRequest(prompt="Test", response_format="text")
    res = gw.execute(req)

    assert res.success is True
    assert res.provider_name == "secondary"


def test_no_providers_returns_error():
    """Gateway with empty providers returns error, never crashes."""
    gw = AIGatewayService(
        providers={},
        fallback_policy=FallbackPolicy(primary="missing"),
    )

    req = AIRequest(prompt="Test", response_format="text")
    res = gw.execute(req)

    assert res.success is False
