from fastapi import APIRouter
from app.config.dependency_injection import get_container
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/evaluation", tags=["AI"])
def get_ai_evaluation_data():
    """
    Returns structured model evaluation telemetry to compare local vs. cloud performance.
    Evaluates Provider State, Token Usage, Latency, Fallback depth, RAG coverage, and Output lengths.
    """
    gateway = get_container().ai_gateway
    gateway._update_circuit_window()
    traces = gateway.last_traces
    
    if not traces:
        return {"status": "NO_DATA", "metrics": {}}
        
    # Segment by provider
    local_traces = [t for t in traces if t.get("provider_type") == "local" and t.get("success")]
    cloud_traces = [t for t in traces if t.get("provider_type") == "cloud" and t.get("success")]
    
    def _calc_stats(grp):
        if not grp:
            return None
        count = len(grp)
        avg_latency = sum(t["total_latency_ms"] for t in grp) / count
        avg_prompt_tokens = sum(t["prompt_tokens"] for t in grp) / count
        avg_completion_tokens = sum(t["completion_tokens"] for t in grp) / count
        avg_coverage = sum(t.get("retrieval_coverage_score") or 0 for t in grp) / count
        
        # Estimate output length if not directly logged in trace (derive from completion tokens approx)
        avg_output_length = avg_completion_tokens * 4 
        
        return {
            "sample_size": count,
            "avg_latency_ms": round(avg_latency, 1),
            "avg_prompt_tokens": round(avg_prompt_tokens, 1),
            "avg_completion_tokens": round(avg_completion_tokens, 1),
            "avg_rag_coverage_score": round(avg_coverage, 3),
            "estimated_avg_output_chars": round(avg_output_length, 0),
            "fallback_triggers": sum(1 for t in grp if t.get("fallback_triggered"))
        }

    return {
        "status": "EVALUATION_READY",
        "timestamp": datetime.utcnow().isoformat(),
        "total_traces_analyzed": len(traces),
        "circuit_breaker_state": gateway.circuit_state.value,
        "daily_cost_usd": round(gateway.cumulative_daily_cost_usd, 4),
        "evaluation_metrics": {
            "local_models": _calc_stats(local_traces),
            "cloud_models": _calc_stats(cloud_traces)
        },
        "recent_anomalies": [t for t in traces if not t.get("success")][:5]
    }
