import time
import json
import random
import threading
import sys
from concurrent.futures import ThreadPoolExecutor

from app.models.ai_models import AIRequest, AIResponse
from app.services.ai_gateway import AIGatewayService, FallbackPolicy, CircuitState
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
            parsed_output={"diagnosis": "success", "metrics": {}, "primary_action": "action", "confidence": "HIGH"},
            model_name="mock-model", provider_name=self._name,
            prompt_tokens=100, completion_tokens=50,
            latency_ms=int(latency * 1000), success=True, error=None
        )

def run_7b_load_test():
    print("=== Phase 7B: Enterprise AI Gateway Load Test ===")
    
    # 1. Setup Providers
    providers = {
        "local": MockProvider("local", fail_rate=0.3, latency_range=(0.05, 0.1)),     # 30% failure rate (Forces Fallbacks)
        "openai": MockProvider("openai", fail_rate=0.01, latency_range=(0.2, 0.4)),   # 1% failure rate
        "gemini": MockProvider("gemini", fail_rate=0.0, latency_range=(0.1, 0.3))     # Perfect fallback
    }
    
    # 2. Setup Gateway with aggressive Circuit Breaker thresholds for rapid testing
    policy = FallbackPolicy(primary="local", secondary="openai", timeout_ms=5000, max_retries=0)
    gateway = AIGatewayService(
        providers=providers,
        fallback_policy=policy,
        failure_rate_threshold=0.5,  # 50% failure rate to open
        min_requests_window=5,
        window_seconds=10
    )
    
    # We enforce JSON Schema internally on execute
    test_schema = {
        "type": "object",
        "properties": {
            "diagnosis": {"type": "string"},
            "metrics": {"type": "object"},
            "primary_action": {"type": "string"},
            "confidence": {"type": "string"}
        },
        "required": ["diagnosis", "metrics", "primary_action", "confidence"]
    }

    requests_to_make = [
        AIRequest(prompt=f"Req {i}", response_format="json", json_schema=test_schema) 
        for i in range(50)
    ]
    
    print("Executing 50 concurrent requests bridging Primary -> Secondary Routing...")
    
    start_time = time.time()
    
    def _fire(req):
        return gateway.execute(req, retrieval_coverage_score=0.5)

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(_fire, requests_to_make))

    end_time = time.time()
    total_time = end_time - start_time
    
    print(f"\n[Test Complete in {total_time:.2f}s]")
    
    success_count = sum(1 for r in results if r.success)
    failed_count = len(results) - success_count
    
    print(f"Total Requests: 50 | Success: {success_count} | Failed: {failed_count}")
    
    print("\n[Provider Load Distribution]")
    for name, p in providers.items():
        print(f" - {name}: {p.request_count} calls handled")
    
    health = gateway.get_health()
    print("\n[Gateway Health State]")
    print(json.dumps(health['circuit_breaker'], indent=2))
    
    # We expect roughly 30% to hit OpenAI fallback.
    assert providers["openai"].request_count > 5, "Fallback routing fundamentally failed!"
    assert success_count > 40, "Too many absolute failures!"
    
    print(f"\nRolling Average Latency: {health['rolling_latency_ms']} ms")
    assert health['rolling_latency_ms'] > 0
    
    print("=== Phase 7B Validated: Deterministic Routing and Circuit Mesh Stable ===")

if __name__ == "__main__":
    run_7b_load_test()
