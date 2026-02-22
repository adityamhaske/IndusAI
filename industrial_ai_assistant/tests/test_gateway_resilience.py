import asyncio
import time
import json
import requests
from unittest.mock import patch, MagicMock

from app.models.ai_models import AIRequest
from app.ai_providers.local_ollama_provider import LocalOllamaProvider
from app.services.ai_gateway import AIGatewayService


def simulate_network_delay(delay_seconds: float):
    time.sleep(delay_seconds)
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": json.dumps({"diagnosis": "delayed", "metrics": {}, "primary_action": "wait", "confidence": "LOW"}),
        "prompt_eval_count": 10,
        "eval_count": 20
    }
    return mock_response

def simulate_timeout(*args, **kwargs):
    time.sleep(1.0)
    raise requests.exceptions.Timeout("Connection timed out")

def simulate_502(*args, **kwargs):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("502 Server Error")
    return mock_response

def simulate_invalid_json(*args, **kwargs):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": "{invalid json",
        "prompt_eval_count": 10,
        "eval_count": 20
    }
    return mock_response

def simulate_success(*args, **kwargs):
    # Simulate some small latency
    time.sleep(0.1)
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "response": json.dumps({"diagnosis": "success", "metrics": {}, "primary_action": "action", "confidence": "HIGH"}),
        "prompt_eval_count": 50,
        "eval_count": 100
    }
    return mock_response


def run_tests():
    print("=== Phase 7A.5: AI Gateway Controlled Failure Validation ===")
    
    provider = LocalOllamaProvider(base_url="http://mock", model="mock-model")
    # Tweak window for testing quickly
    gateway = AIGatewayService(primary_provider=provider, failure_threshold=3, window_seconds=5)
    
    req = AIRequest(prompt="test", response_format="json")

    print("\n[1] Testing: Invalid JSON Injection")
    with patch("requests.post", side_effect=simulate_invalid_json):
        res = gateway.execute(req)
        print(f"Success: {res.success}, Error: {res.error}, Type: {res.error_type}")
        assert not res.success
        assert res.error_type == "PARSE"
        
    print("\n[2] Testing: Connection Timeout (60s simulation represented as standard timeout exception)")
    with patch("requests.post", side_effect=simulate_timeout):
        res = gateway.execute(req)
        print(f"Success: {res.success}, Error: {res.error}, Type: {res.error_type}")
        assert not res.success
        assert res.error_type == "TIMEOUT"
        
    print("\n[3] Testing: 502 Server Error")
    with patch("requests.post", side_effect=simulate_502):
        res = gateway.execute(req)
        print(f"Success: {res.success}, Error: {res.error}, Type: {res.error_type}")
        assert not res.success
        assert res.error_type == "CONNECTION"
        
    health = gateway.get_health()
    print(f"\nHealth Check Mid-Failures: {health['status']} | Circuit: {health['circuit_breaker']['state']}")
    assert health['circuit_breaker']['failures_in_window'] == 3
    assert health['circuit_breaker']['state'] == "OPEN"
    
    print("\n[4] Testing: Circuit Breaker Open Rejection")
    # Even if the provider is fine now, it should reject because circuit is open
    with patch("requests.post", side_effect=simulate_success):
        res = gateway.execute(req)
        print(f"Success: {res.success}, Error: {res.error}, Type: {res.error_type}")
        assert not res.success
        assert res.error_type == "CONNECTION"
        assert "Circuit Breaker OPEN" in str(res.error)

    print("\n[5] Testing: Circuit Breaker Recovery")
    print("Waiting 6 seconds for circuit breaker window to expire...")
    time.sleep(6)
    
    with patch("requests.post", side_effect=simulate_success):
        res = gateway.execute(req, retrieval_coverage_score=0.85)
        print(f"Success: {res.success}, Parsed Output: {res.parsed_output}")
        assert res.success
    
    print("\n[6] Validating Telemetry Accuracy")
    health = gateway.get_health()
    print(json.dumps(health, indent=2))
    assert health["status"] == "OPERATIONAL"
    assert health["rolling_latency_ms"] > 0
    assert health["recent_traces"][0]["retrieval_coverage_score"] == 0.85
    assert health["last_error_timestamp"] is not None

    print("\n=== All Tests Passed Successfully ===")

if __name__ == "__main__":
    run_tests()
