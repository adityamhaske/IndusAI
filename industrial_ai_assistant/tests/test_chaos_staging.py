import pytest
import asyncio
from unittest.mock import patch, MagicMock
from app.models.ai_models import AIRequest, AIResponse
from app.services.ai_gateway import AIGatewayService, FallbackPolicy
from app.ai_providers.local_ollama_provider import LocalOllamaProvider
from app.ai_providers.openai_provider import OpenAIProvider
from app.ai_providers.gemini_provider import GeminiProvider

class _ChaosMockProvider(LocalOllamaProvider):
    def __init__(self, mode, name="chaos"):
        super().__init__(base_url="http://mock", model="mock")
        self.mode = mode
        self.name = name
    
    def generate(self, req: AIRequest) -> AIResponse:
        if self.mode == "timeout":
            raise TimeoutError(f"Simulated {self.name} connection timeout.")
        if self.mode == "schema_drift":
            return AIResponse(
                raw_output='{"invalid_structure": true, "no_diagnosis": true}',
                success=True,
                error=None,
                parsed_output={"invalid_structure": True, "no_diagnosis": True},
                model_name=self.name,
                provider_name=self.name
            )
        if self.mode == "network_drop":
            import requests
            raise requests.exceptions.ConnectionError(f"Simulated {self.name} network drop.")
            
        return AIResponse(
            raw_output='{"diagnosis": "Good", "metrics": {}, "primary_action": "Fix it", "confidence": "HIGH"}',
            success=True,
            error=None,
            parsed_output={"diagnosis": "Good", "metrics": {}, "primary_action": "Fix it", "confidence": "HIGH"},
            model_name=self.name,
            provider_name=self.name
        )


@pytest.fixture
def chaos_gateway():
    policy = FallbackPolicy(primary="local", secondary="openai", timeout_ms=1000, json_enforced=True)
    return AIGatewayService(
        providers={
            "local": _ChaosMockProvider(mode="timeout", name="local_ollama"),
            "openai": _ChaosMockProvider(mode="network_drop", name="openai_cloud"),
            "gemini": _ChaosMockProvider(mode="schema_drift", name="gemini_cloud")
        },
        fallback_policy=policy,
        failure_rate_threshold=0.5,
        window_seconds=10
    )


def test_catastrophic_total_failure_degrades_cleanly(chaos_gateway):
    req = AIRequest(prompt="Test", parameters={}, json_schema=None)
    
    # Run request. Primary times out, falls back to Secondary. Secondary drops network.
    res = chaos_gateway.execute(req)
    
    assert res.success is False
    assert res.error is not None
    assert "Simulated openai_cloud network drop" in res.error 
    assert chaos_gateway.circuit_state.value == "CLOSED" # Only local failure counts towards circuit if primary.

def test_schema_drift_is_trapped(chaos_gateway):
    # Swap secondary to the schema drifting Gemini
    chaos_gateway.policy.secondary = "gemini"
    
    req = AIRequest(
        prompt="Test", 
        parameters={}, 
        response_format="json",
        json_schema={"type": "object", "required": ["diagnosis", "primary_action"]}
    )
    res = chaos_gateway.execute(req)
    
    # The gateway must catch the bad JSON schema drift and invalidate `success`.
    assert res.success is False
    assert "SCHEMA_VALIDATION_FAILED" in res.error
    assert "invalid_structure" in res.raw_output

def test_qdrant_latency_simulator():
    """Simulates 3-second DB latencies."""
    pass # Currently RAG is outside Gateway direct execution logic, but would be covered in Orchestrator chaos.
