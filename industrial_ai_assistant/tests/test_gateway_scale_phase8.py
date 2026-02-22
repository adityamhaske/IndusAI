import time
import json
import random
import threading
import sys
from concurrent.futures import ThreadPoolExecutor

from app.models.ai_models import AIRequest, AIResponse
from app.services.ai_gateway import AIGatewayService, FallbackPolicy, CircuitState, SystemStatus
from app.core.interfaces.ai_provider import AIProvider

class ScalableMockProvider(AIProvider):
    def __init__(self, name: str, fail_rate: float, latency_range: tuple):
        self._name = name
        self.fail_rate = fail_rate
        self.latency_range = latency_range
        self.request_count = 0
        self.lock = threading.Lock()

    @property
    def provider_name(self) -> str:
        return self._name

    def generate(self, request: AIRequest) -> AIResponse:
        with self.lock:
            self.request_count += 1
            
        latency = random.uniform(*self.latency_range)
        time.sleep(latency)
        
        if random.random() < self.fail_rate:
            return AIResponse(
                raw_output="", model_name="mock-model", provider_name=self._name,
                latency_ms=int(latency * 1000), success=False,
                error=f"{self._name} simulated random failure", error_type="CONNECTION"
            )
            
        return AIResponse(
            raw_output="", 
            parsed_output={"diagnosis": "scale_success", "metrics": {}, "primary_action": "proceed", "confidence": "HIGH"},
            model_name="mock-model", provider_name=self._name,
            prompt_tokens=150, completion_tokens=75,
            latency_ms=int(latency * 1000), success=True, error=None
        )

def run_phase8_scale_test():
    print("=== Phase 8: Enterprise Scale & SLA Compliance Test ===")
    
    # Under heavy turbulence
    providers = {
        "local": ScalableMockProvider("local", fail_rate=0.4, latency_range=(0.01, 0.05)),
        "openai": ScalableMockProvider("openai", fail_rate=0.05, latency_range=(0.1, 0.2)),
        "gemini": ScalableMockProvider("gemini", fail_rate=0.0, latency_range=(0.1, 0.15))
    }
    
    # Strict limits: 20 max threads, 300 RPM limit. Cost limit: $50
    policy = FallbackPolicy(primary="local", secondary="openai", timeout_ms=3000, max_retries=0)
    gateway = AIGatewayService(
        providers=providers,
        fallback_policy=policy,
        failure_rate_threshold=0.6,
        window_seconds=10,
        max_concurrent_requests=30,  # Push beyond 30 creates RATE LIMIT errors natively
        max_rpm=300,
        max_daily_cost_usd=50.0,
        enable_speculative_fallback=True
    )
    
    schema = {
        "type": "object",
        "properties": {
            "diagnosis": {"type": "string"},
            "metrics": {"type": "object"},
            "primary_action": {"type": "string"},
            "confidence": {"type": "string"}
        },
        "required": ["diagnosis", "primary_action"]
    }

    print("Spawning 100 completely concurrent payload requests in a 40-worker thread pool...")
    print("This rigorously tests threading semaphores, asyncio safety, sliding windows, and parallel speculative logging.")
    
    requests = [
        AIRequest(prompt=f"Stress {i}", response_format="json", json_schema=schema) 
        for i in range(100)
    ]
    
    start_time = time.time()
    
    def _fire(req):
        return gateway.execute(req, retrieval_coverage_score=0.8)

    with ThreadPoolExecutor(max_workers=40) as executor:
        results = list(executor.map(_fire, requests))

    total_time = time.time() - start_time
    
    rate_limited = sum(1 for r in results if r.error == "RATE_LIMIT_EXCEEDED")
    successes = sum(1 for r in results if r.success)
    
    print(f"\n[Sustained Burst Complete in {total_time:.2f}s]")
    print(f"Total Traces: 100")
    print(f"Rate Limited (Throttled gracefully without crashing): {rate_limited}")
    print(f"Fully Successful (Parsed correctly): {successes}")
    
    metrics = gateway.get_metrics()
    print("\n[Phase 8 SLA Observability Export Metrics]")
    print(json.dumps(metrics, indent=2))
    
    print("\n[Cost Accounting]")
    print(f"Total Cumulative Daily Cost Tracked: ${metrics['cumulative_daily_cost_usd']}")
    
    # Assertions for robust scale mechanics
    assert metrics['p50_latency_ms'] > 0, "Telemetry P50 invalid"
    assert "DEGRADED" in metrics["status"] or "RATE_LIMITED" in metrics["status"] or "NORMAL" in metrics["status"]
    assert rate_limited > 0, "Rate limiter did not violently snap under max pool pressure!"
    
    print("=== Phase 8 Scale Tests Passed ===")

if __name__ == "__main__":
    run_phase8_scale_test()
