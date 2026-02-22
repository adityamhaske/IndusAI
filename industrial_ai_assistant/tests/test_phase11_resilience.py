import pytest
import asyncio
from app.models.ai_models import AIRequest, AIResponse
from app.services.ai_gateway import AIGatewayService, FallbackPolicy
from app.ai_providers.local_ollama_provider import LocalOllamaProvider

class FailingProvider(LocalOllamaProvider):
    def __init__(self, name="failing"):
        super().__init__(base_url="http://mock", model="mock")
        self.name = name
        
    def generate(self, req: AIRequest) -> AIResponse:
        raise TimeoutError("Test timeout")

class ExpensiveProvider(LocalOllamaProvider):
    def __init__(self, name="expensive"):
        super().__init__(base_url="http://mock", model="mock")
        self.name = name
    
    def generate(self, req: AIRequest) -> AIResponse:
        return AIResponse(
            raw_output='{"status": "ok"}',
            success=True,
            parsed_output={"status": "ok"},
            model_name=self.name,
            provider_name=self.name,
            cost_usd=1.0 # Simulate massive cost
        )


@pytest.fixture
def resilience_gateway():
    policy = FallbackPolicy(primary="fail", secondary="fail", timeout_ms=10)
    return AIGatewayService(
        providers={
            "fail": FailingProvider(name="fail_local"),
            "expensive": ExpensiveProvider(name="expensive_cloud")
        },
        fallback_policy=policy,
        failure_rate_threshold=0.5,
        window_seconds=10
    )


def test_circuit_breaker_opens_after_failures():
    policy = FallbackPolicy(primary="fail", secondary=None, timeout_ms=10)
    gateway = AIGatewayService(
        providers={"fail": FailingProvider(name="fail_local")},
        fallback_policy=policy,
        failure_rate_threshold=0.5,
        window_seconds=10
    )
    req = AIRequest(prompt="Test")
    
    # Send enough requests to breach the default min_requests_window (10)
    for _ in range(12):
        gateway.execute(req)
        
    # If we request again, it evaluates state -> trips to OPEN -> fail-fasts instantly
    res = gateway.execute(req)
    assert res.success is False
    assert gateway.circuit_state.value == "OPEN"
    assert "Circuit Breaker OPEN" in res.error

def test_cost_guard_blocks_expensive_cloud():
    policy = FallbackPolicy(primary="fail", secondary="expensive", timeout_ms=100)
    gateway = AIGatewayService(
        providers={
            "fail": FailingProvider(name="fail"),
            "expensive": ExpensiveProvider(name="expensive")
        },
        fallback_policy=policy,
        max_daily_cost_usd=2.5
    )
    req = AIRequest(prompt="Cost test")
    
    # 1. Simulate the gateway crossing the SLA guardrail budget threshold
    gateway._add_cost(50.0)
    
    # 2. Attempt a request. Primary will fail/timeout, and fallback should be blocked.
    res = gateway.execute(req)
    
    # Primary failed ("TimeoutError"), Secondary blocked ("DEGRADED_NO_CLOUD")
    assert res.success is False
    assert "timeout" in res.error.lower()
    assert gateway.cost_guard_triggered is True

def test_hard_concurrency_rate_limits():
    policy = FallbackPolicy(primary="expensive", secondary=None, timeout_ms=100)
    gateway = AIGatewayService(
        providers={"expensive": ExpensiveProvider(name="expensive")},
        fallback_policy=policy,
        max_rpm=3
    )
    req = AIRequest(prompt="Rate test")
    
    gateway.execute(req)
    gateway.execute(req)
    gateway.execute(req)
    
    # 4th request in the minute should RATE_LIMIT
    res4 = gateway.execute(req)
    assert res4.success is False
    assert "RATE_LIMIT" in res4.error
