"""
AI Gateway load test — adapted for the stripped thin routing layer.
Tests: provider routing, retry, and fallback under simulated failure.
"""
import time
import json
import random
from concurrent.futures import ThreadPoolExecutor

from app.models.ai_models import AIRequest, AIResponse
from app.services.ai_gateway import AIGatewayService, FallbackPolicy
from app.core.interfaces.ai_provider import AIProvider


class MockProvider(AIProvider):
    def __init__(self, name: str, fail_rate: float, latency_range: tuple):
        self._name = name
        self.fail_rate = fail_rate
        self.latency_range = latency_range
        self.request_count = 0

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def provider_type(self) -> str:
        return "cloud"

    def generate(self, request: AIRequest) -> AIResponse:
        self.request_count += 1
        latency = random.uniform(*self.latency_range)
        time.sleep(latency)

        if random.random() < self.fail_rate:
            return AIResponse(
                raw_output="", model_name="mock-model", provider_name=self._name,
                latency_ms=int(latency * 1000), success=False,
                error=f"{self._name} simulated failure", error_type="CONNECTION"
            )

        return AIResponse(
            raw_output="",
            parsed_output={"diagnosis": "success", "primary_action": "action", "confidence": "HIGH"},
            model_name="mock-model", provider_name=self._name,
            prompt_tokens=100, completion_tokens=50,
            latency_ms=int(latency * 1000), success=True, error=None
        )


def test_gateway_load():
    """Tests basic routing and fallback under concurrent load."""
    providers = {
        "primary": MockProvider("primary", fail_rate=0.3, latency_range=(0.01, 0.03)),
        "secondary": MockProvider("secondary", fail_rate=0.01, latency_range=(0.01, 0.03)),
    }

    policy = FallbackPolicy(primary="primary", secondary="secondary", max_retries=1)
    gateway = AIGatewayService(providers=providers, fallback_policy=policy)

    requests_to_make = [
        AIRequest(prompt=f"Req {i}", response_format="text")
        for i in range(30)
    ]

    def _fire(req):
        return gateway.execute(req)

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(_fire, requests_to_make))

    success_count = sum(1 for r in results if r.success)
    assert success_count > 25, f"Too many failures: {30 - success_count}/30"

    # Secondary should have handled some fallback requests
    assert providers["secondary"].request_count > 0, "Fallback never triggered"

    health = gateway.get_health()
    assert health["status"] in ("OPERATIONAL", "NO_PROVIDERS")
