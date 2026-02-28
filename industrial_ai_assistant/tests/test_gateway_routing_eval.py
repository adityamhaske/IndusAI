import pytest
from unittest.mock import MagicMock
from app.services.ai_gateway import AIGatewayService, FallbackPolicy
from app.models.ai_models import AIRequest
from app.core.interfaces.ai_provider import AIProvider
from app.api.routes_ai_eval import get_ai_evaluation_data

class MockProvider(AIProvider):
    def __init__(self, p_type, success=True):
        self.provider_type = p_type
        self.should_succeed = success
        
    def generate(self, req: AIRequest):
        from app.models.ai_models import AIResponse
        return AIResponse(
            raw_output="test",
            model_name="mock-" + self.provider_type,
            provider_name=self.provider_type,
            prompt_tokens=req.prompt_tokens if hasattr(req, 'prompt_tokens') else 10,
            completion_tokens=20,
            success=self.should_succeed,
            error=None if self.should_succeed else "Forced failure"
        )

def test_intelligent_routing_to_cloud():
    cloud_mock = MockProvider("cloud")
    cloud_mock.api_key = "test"
    local_mock = MockProvider("local")
    
    gw = AIGatewayService(
        providers={"openai": cloud_mock, "local": local_mock},
        fallback_policy=FallbackPolicy(primary="local", secondary=None)
    )
    
    # 1. Normal short query goes to Local
    req1 = AIRequest(prompt="short", response_format="text")
    res1 = gw.execute(req1, retrieval_chunk_count=1)
    assert res1.provider_name == "local"
    
    # 2. Large query goes to Cloud
    req2 = AIRequest(prompt="long " * 1000, response_format="text", intent_type="DOCUMENT_SUMMARY")
    res2 = gw.execute(req2, retrieval_chunk_count=5)
    assert res2.provider_name == "openai"

def test_ai_evaluation_data_aggregation():
    # Insert dummy traces matching what execute() produces
    cloud_mock = MockProvider("cloud")
    local_mock = MockProvider("local")
    
    gw = AIGatewayService(
        providers={"openai": cloud_mock, "local": local_mock},
        fallback_policy=FallbackPolicy(primary="local", secondary=None)
    )
    
    # Manually seed traces
    gw.last_traces = [
        {"provider_type": "local", "success": True, "total_latency_ms": 100, "prompt_tokens": 10, "completion_tokens": 20, "retrieval_coverage_score": 0.5, "fallback_triggered": False},
        {"provider_type": "local", "success": True, "total_latency_ms": 200, "prompt_tokens": 10, "completion_tokens": 20, "retrieval_coverage_score": 0.5, "fallback_triggered": False},
        {"provider_type": "cloud", "success": True, "total_latency_ms": 500, "prompt_tokens": 1000, "completion_tokens": 500, "retrieval_coverage_score": 0.9, "fallback_triggered": True},
        {"provider_type": "cloud", "success": False, "total_latency_ms": 50, "prompt_tokens": 0, "completion_tokens": 0, "retrieval_coverage_score": 0.0, "fallback_triggered": False, "error": "timeout"}
    ]
    
    # Mock the dependency injection container for the router
    import app.api.routes_ai_eval as ev
    original_get = ev.get_container
    
    class DummyContainer:
        ai_gateway = gw
        
    ev.get_container = lambda: DummyContainer()
    
    try:
        data = get_ai_evaluation_data()
        assert data["status"] == "EVALUATION_READY"
        
        metrics = data["evaluation_metrics"]
        assert metrics["local_models"]["sample_size"] == 2
        assert metrics["local_models"]["avg_latency_ms"] == 150.0  # (100+200)/2
        
        assert metrics["cloud_models"]["sample_size"] == 1 # Excludes failures
        assert metrics["cloud_models"]["avg_latency_ms"] == 500.0
        assert metrics["cloud_models"]["fallback_triggers"] == 1
        
        assert len(data["recent_anomalies"]) == 1
    finally:
        ev.get_container = original_get
