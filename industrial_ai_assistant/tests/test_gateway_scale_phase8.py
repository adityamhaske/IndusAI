"""
AI Gateway scale test — adapted for stripped thin routing layer.
Tests: concurrent load, retry, fallback behavior.
"""
import time
import random
from concurrent.futures import ThreadPoolExecutor

from app.models.ai_models import AIRequest, AIResponse
from app.services.ai_gateway import AIGatewayService, FallbackPolicy
from app.core.interfaces.ai_provider import AIProvider


class MockProvider(AIProvider):
    def __init__(self, name: str, fail_rate: float = 0.0, latency_ms: float = 10):
        self._name = name
        self.fail_rate = fail_rate
        self._latency = latency_ms / 1000.0
        self.request_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def provider_type(self) -> str:
        return "cloud"

    def generate(self, request: AIRequest) -> AIResponse:
        self.request_count += 1
        time.sleep(self._latency)

        if random.random() < self.fail_rate:
            return AIResponse(
                raw_output="", model_name="mock", provider_name=self._name,
                success=False, error="simulated", error_type="CONNECTION"
            )

        return AIResponse(
            raw_output="OK", model_name="mock", provider_name=self._name,
            prompt_tokens=10, completion_tokens=5, success=True, error=None
        )


def test_scale_50_concurrent():
    """50 requests over 10 workers — gateway stays healthy."""
    providers = {
        "gemini": MockProvider("gemini", fail_rate=0.0, latency_ms=5),
    }
    policy = FallbackPolicy(primary="gemini")
    gw = AIGatewayService(providers=providers, fallback_policy=policy)

    reqs = [AIRequest(prompt=f"scale-{i}", response_format="text") for i in range(50)]

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(gw.execute, reqs))

    successes = sum(1 for r in results if r.success)
    assert successes == 50, f"Expected 50 successes, got {successes}"
    assert providers["gemini"].request_count == 50


def test_fallback_under_load():
    """Primary fails 50%. Secondary should catch most."""
    providers = {
        "primary": MockProvider("primary", fail_rate=0.5, latency_ms=5),
        "secondary": MockProvider("secondary", fail_rate=0.0, latency_ms=5),
    }
    policy = FallbackPolicy(primary="primary", secondary="secondary", max_retries=0)
    gw = AIGatewayService(providers=providers, fallback_policy=policy)

    reqs = [AIRequest(prompt=f"fb-{i}", response_format="text") for i in range(40)]

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(gw.execute, reqs))

    successes = sum(1 for r in results if r.success)
    assert successes >= 35, f"Too many failures: only {successes}/40 succeeded"
    assert providers["secondary"].request_count > 5, "Secondary fallback never engaged"
