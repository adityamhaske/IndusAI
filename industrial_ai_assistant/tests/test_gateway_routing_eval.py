"""
Gateway routing tests — adapted for thin routing layer.
Tests: basic primary routing, fallback on failure.
"""
import pytest
from app.services.ai_gateway import AIGatewayService, FallbackPolicy
from app.models.ai_models import AIRequest, AIResponse
from app.core.interfaces.ai_provider import AIProvider


class MockProvider(AIProvider):
    def __init__(self, name: str, success=True):
        self._name = name
        self.should_succeed = success
        self.request_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def provider_type(self) -> str:
        return "cloud"

    def generate(self, req: AIRequest) -> AIResponse:
        self.request_count += 1
        return AIResponse(
            raw_output="test",
            model_name=f"mock-{self._name}",
            provider_name=self._name,
            prompt_tokens=10,
            completion_tokens=20,
            success=self.should_succeed,
            error=None if self.should_succeed else "Forced failure"
        )


def test_primary_routing():
    """Requests go to primary provider first."""
    primary = MockProvider("gemini")
    secondary = MockProvider("openai")

    gw = AIGatewayService(
        providers={"gemini": primary, "openai": secondary},
        fallback_policy=FallbackPolicy(primary="gemini", secondary="openai")
    )

    req = AIRequest(prompt="hello", response_format="text")
    res = gw.execute(req)

    assert res.success
    assert res.provider_name == "gemini"
    assert primary.request_count == 1
    assert secondary.request_count == 0


def test_fallback_on_failure():
    """When primary fails, secondary handles the request."""
    primary = MockProvider("gemini", success=False)
    secondary = MockProvider("openai", success=True)

    gw = AIGatewayService(
        providers={"gemini": primary, "openai": secondary},
        fallback_policy=FallbackPolicy(primary="gemini", secondary="openai")
    )

    req = AIRequest(prompt="hello", response_format="text")
    res = gw.execute(req)

    assert res.success
    assert res.provider_name == "openai"


def test_health_reports_providers():
    """get_health returns correct provider info."""
    provider = MockProvider("gemini")
    gw = AIGatewayService(
        providers={"gemini": provider},
        fallback_policy=FallbackPolicy(primary="gemini")
    )

    health = gw.get_health()
    assert health["status"] == "OPERATIONAL"
    assert "gemini" in health["registered_providers"]
