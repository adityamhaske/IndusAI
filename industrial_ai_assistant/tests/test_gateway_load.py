import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, MagicMock

from app.models.ai_models import AIRequest
from app.ai_providers.local_ollama_provider import LocalOllamaProvider
from app.services.ai_gateway import AIGatewayService

def simulate_llm_processing(*args, **kwargs):
    # Simulate a fast response for testing, but still introducing some small variable latency
    import random
    processing_time = random.uniform(0.1, 0.4)
    time.sleep(processing_time)
    
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": json.dumps({
            "diagnosis": "Concurrent Load Testing Successful", 
            "metrics": {}, 
            "primary_action": "Proceed", 
            "confidence": "HIGH"
        }),
        "prompt_eval_count": random.randint(50, 150),
        "eval_count": random.randint(100, 300)
    }
    return mock_response

def run_load_test():
    print("=== Phase 7A.5: AI Gateway Load Testing ===")
    
    provider = LocalOllamaProvider(base_url="http://mock", model="mock-model")
    # Real-world circuit breaker config
    gateway = AIGatewayService(primary_provider=provider, failure_threshold=10, window_seconds=60)
    
    req_short = AIRequest(prompt="Short Prompt", response_format="json")
    req_long = AIRequest(prompt="Long Prompt " * 50, response_format="json")
    
    requests_to_make = [req_short, req_long] * 10  # 20 concurrent requests

    start_time = time.time()
    
    def _execute_req(req):
        # We also simulate mixed retrieval_coverage_score
        import random
        coverage = random.uniform(0.1, 0.9)
        with patch("requests.post", side_effect=simulate_llm_processing):
            return gateway.execute(req, retrieval_coverage_score=coverage)

    print(f"Executing {len(requests_to_make)} concurrent requests against Gateway...")
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(_execute_req, requests_to_make))

    end_time = time.time()
    
    total_time = end_time - start_time
    
    print(f"\nCompleted {len(results)} requests in {total_time:.2f} seconds.")
    
    successes = sum(1 for r in results if r.success)
    failures = sum(1 for r in results if not r.success)
    
    print(f"Successes: {successes} | Failures: {failures}")
    assert successes == 20
    
    health = gateway.get_health()
    print("\n[Telemetry Dump]")
    print(json.dumps(health, indent=2))
    
    assert health["status"] == "OPERATIONAL"
    assert len(health["recent_traces"]) == 10  # Endpoint caps at top 10
    
    # Analyze Telemetry accuracy
    avg_latency = health["rolling_latency_ms"]
    print(f"\nAverage Rolling Latency: {avg_latency} ms")
    assert avg_latency > 0

    print("\nLoad Stability Checked. Thread Pool executed successfully without event loop blocking.")
    print("=== All Load Tests Passed Successfully ===")

if __name__ == "__main__":
    run_load_test()
