"""
API routes for AI Gateway metrics and observability.
Mounted at /api/ai by main.py.
"""
from fastapi import APIRouter, Response
from app.config.dependency_injection import get_container

router = APIRouter()

@router.get("/health", tags=["AI"])
def get_ai_gateway_health():
    """
    Returns full diagnostic telemetry and circuit breaker status 
    across all configured AI Providers via the AIGatewayService.
    """
    gateway = get_container().ai_gateway
    return gateway.get_health()

@router.get("/metrics", tags=["AI"])
def get_ai_gateway_metrics():
    """
    Returns high-level SLA Observability Metrics for Prometheus/Monitoring
    such as P50/P95 latencies, failure rates, and fallback ratios.
    """
    gateway = get_container().ai_gateway
    m = gateway.get_metrics()
    
    # Prometheus plain text exporter format
    lines = [
        "# HELP ai_gateway_status Global system status (0=NORMAL, higher=DEGRADED)",
        "# TYPE ai_gateway_status gauge",
        f"ai_gateway_status {1 if m.get('status') != 'NORMAL' else 0}",
        
        "# HELP ai_gateway_local_p50_latency_ms P50 latency of successful local AI requests",
        "# TYPE ai_gateway_local_p50_latency_ms gauge",
        f"ai_gateway_local_p50_latency_ms {m.get('local_p50_latency_ms', 0)}",
        
        "# HELP ai_gateway_local_p95_latency_ms P95 latency of successful local AI requests",
        "# TYPE ai_gateway_local_p95_latency_ms gauge",
        f"ai_gateway_local_p95_latency_ms {m.get('local_p95_latency_ms', 0)}",
        
        "# HELP ai_gateway_cloud_p50_latency_ms P50 latency of successful cloud AI requests",
        "# TYPE ai_gateway_cloud_p50_latency_ms gauge",
        f"ai_gateway_cloud_p50_latency_ms {m.get('cloud_p50_latency_ms', 0)}",
        
        "# HELP ai_gateway_cloud_p95_latency_ms P95 latency of successful cloud AI requests",
        "# TYPE ai_gateway_cloud_p95_latency_ms gauge",
        f"ai_gateway_cloud_p95_latency_ms {m.get('cloud_p95_latency_ms', 0)}",
        
        "# HELP ai_gateway_failure_rate_last_60s Sliding window failure rate",
        "# TYPE ai_gateway_failure_rate_last_60s gauge",
        f"ai_gateway_failure_rate_last_60s {m.get('failure_rate_last_60s', 0)}",
        
        "# HELP ai_gateway_fallback_ratio Ratio of cloud fallbacks triggered",
        "# TYPE ai_gateway_fallback_ratio gauge",
        f"ai_gateway_fallback_ratio {m.get('fallback_ratio', 0)}",
        
        "# HELP ai_gateway_schema_failure_rate Rate of JSON Pydantic parsing failures",
        "# TYPE ai_gateway_schema_failure_rate gauge",
        f"ai_gateway_schema_failure_rate {m.get('schema_failure_rate', 0)}",
        
        "# HELP ai_gateway_cumulative_daily_cost_usd Tracked daily usage spend",
        "# TYPE ai_gateway_cumulative_daily_cost_usd counter",
        f"ai_gateway_cumulative_daily_cost_usd {m.get('cumulative_daily_cost_usd', 0)}",
        
        "# HELP ai_gateway_traces_recorded Total requests tracked in cache",
        "# TYPE ai_gateway_traces_recorded gauge",
        f"ai_gateway_traces_recorded {m.get('traces_recorded', 0)}",
    ]
    return Response(content="\\n".join(lines) + "\\n", media_type="text/plain")
