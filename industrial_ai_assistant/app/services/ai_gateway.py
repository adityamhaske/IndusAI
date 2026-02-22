import time
import logging
import json
import threading
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from collections import deque
from dataclasses import dataclass
from jsonschema import validate, ValidationError

from app.core.interfaces.ai_provider import AIProvider
from app.models.ai_models import AIRequest, AIResponse

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class SystemStatus(Enum):
    NORMAL = "NORMAL"
    DEGRADED_PRIMARY_ONLY = "DEGRADED_PRIMARY_ONLY"
    DEGRADED_NO_CLOUD = "DEGRADED_NO_CLOUD"
    RATE_LIMITED = "RATE_LIMITED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    DATA_INTEGRITY_WARNING = "DATA_INTEGRITY_WARNING"

@dataclass
class FallbackPolicy:
    primary: str = "local"
    secondary: Optional[str] = "openai"
    timeout_ms: int = 8000
    max_retries: int = 1
    json_enforced: bool = True

class AIGatewayService:
    """
    Enterprise Orchestration layer bridging all AI inferences.
    Handles: Provider routing, Fallbacks, Circuit Breaking, and Telemetry.
    """

    # Estimated cost per 1M tokens (Prompt, Completion)
    PRICING_TIERS = {
        "gpt-4o-mini": (0.150, 0.600),
        "gpt-4o": (5.00, 15.00),
        "gemini-1.5-flash": (0.075, 0.300),
        "gemini-1.5-pro": (3.50, 10.50),
        "local": (0.0, 0.0)
    }

    def __init__(
        self, 
        providers: Dict[str, AIProvider], 
        fallback_policy: FallbackPolicy,
        failure_rate_threshold: float = 0.5, 
        min_requests_window: int = 5,
        window_seconds: int = 60,
        max_concurrent_requests: int = 20,
        max_rpm: int = 100,
        max_daily_cost_usd: float = 50.0,
        enable_speculative_fallback: bool = False
    ):
        self.providers = providers
        self.policy = fallback_policy
        
        # Circuit Breaker state
        self.failure_rate_threshold = failure_rate_threshold
        self.min_requests_window = min_requests_window
        self.window_seconds = window_seconds
        
        # Sliding window queues: store tuples of (timestamp, is_failure)
        self.request_window: deque = deque()
        self.circuit_state = CircuitState.CLOSED
        self.half_open_probe_active = False
        
        # SLA & Rate Limiting
        self.max_concurrent_requests = max_concurrent_requests
        self.concurrency_semaphore = threading.BoundedSemaphore(max_concurrent_requests)
        self.max_rpm = max_rpm
        self.rpm_window: deque = deque()
        self.rpm_lock = threading.Lock()
        
        # Cost Guardrails
        self.max_daily_cost_usd = max_daily_cost_usd
        self.cumulative_daily_cost_usd = 0.0
        self.cost_guard_triggered = False
        self.cost_date = datetime.utcnow().date()
        self.cost_lock = threading.Lock()
        
        self.enable_speculative_fallback = enable_speculative_fallback
        
        # Telemetry State
        self.last_traces: List[Dict[str, Any]] = []
        self.last_error_timestamp: Optional[str] = None

    def _check_rate_limit(self) -> bool:
        """Enforces max_rpm request limits over a 60s sliding window."""
        with self.rpm_lock:
            now = time.time()
            while self.rpm_window and now - self.rpm_window[0] > 60:
                self.rpm_window.popleft()
            if len(self.rpm_window) >= self.max_rpm:
                return False
            self.rpm_window.append(now)
            return True

    def _update_circuit_window(self):
        """Evict old requests from the sliding window."""
        now = time.time()
        while self.request_window and now - self.request_window[0][0] > self.window_seconds:
            self.request_window.popleft()

    def _evaluate_circuit_state(self):
        """Transition logic for the Circuit Breaker."""
        self._update_circuit_window()
        
        if self.circuit_state == CircuitState.OPEN:
            # We don't automatically close here; HALF_OPEN transition happens on next execute call if window passes.
            # But let's check if the window is completely empty of failures, which might allow a probe.
            if not self.request_window:
                self.circuit_state = CircuitState.HALF_OPEN
            return

        total_reqs = len(self.request_window)
        if total_reqs < self.min_requests_window:
            return  # Not enough data to open circuit

        failures = sum(1 for _, is_fail in self.request_window if is_fail)
        failure_rate = failures / total_reqs

        if failure_rate >= self.failure_rate_threshold and self.circuit_state == CircuitState.CLOSED:
            logger.error(f"AIGateway: Circuit Breaker OPENED. Failure rate {failure_rate:.0%} >= {self.failure_rate_threshold:.0%}")
            self.circuit_state = CircuitState.OPEN

    def _record_result(self, is_failure: bool):
        """Log a request result into the sliding window and evaluate."""
        self.request_window.append((time.time(), is_failure))
        if is_failure:
            self.last_error_timestamp = datetime.utcnow().isoformat()
            
        if self.circuit_state == CircuitState.HALF_OPEN:
            if is_failure:
                logger.error("AIGateway: Probe failed. Circuit Breaker returning to OPEN.")
                self.circuit_state = CircuitState.OPEN
            else:
                logger.info("AIGateway: Probe succeeded. Circuit Breaker is now CLOSED.")
                self.circuit_state = CircuitState.CLOSED
                self.request_window.clear() # Reset window on recovery
            self.half_open_probe_active = False
        else:
            self._evaluate_circuit_state()

    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost based on routing tier."""
        tier = (0.0, 0.0)
        for key, rates in self.PRICING_TIERS.items():
            if key in model.lower() or key == model:
                tier = rates
                break
                
        # Handle "mock-model" from tests
        if "mock" in model:
            tier = (0.0, 0.0)
            
        if tier == (0.0, 0.0) and "gpt" not in model and "gemini" not in model:
            # Assume local
            pass
            
        prompt_cost = (prompt_tokens / 1_000_000) * tier[0]
        completion_cost = (completion_tokens / 1_000_000) * tier[1]
        return prompt_cost + completion_cost

    def _add_cost(self, cost: float):
        """Accumulates daily cloud cost and enforces the guardrail threshold."""
        with self.cost_lock:
            today = datetime.utcnow().date()
            if today != self.cost_date:
                self.cost_date = today
                self.cumulative_daily_cost_usd = 0.0
                self.cost_guard_triggered = False
                
            self.cumulative_daily_cost_usd += cost
            if self.cumulative_daily_cost_usd >= self.max_daily_cost_usd and not self.cost_guard_triggered:
                self.cost_guard_triggered = True
                logger.critical(f"AIGateway: ESCALATION - Daily cloud cost guardrail exceeded (${self.max_daily_cost_usd}). Cloud fallbacks disabled.")

    def _log_telemetry(
        self, 
        request: AIRequest, 
        response: AIResponse, 
        total_latency: int, 
        fallback_chain_depth: int, 
        retrieval_coverage: Optional[float] = None
    ):
        cost_usd = self._calculate_cost(response.model_name, response.prompt_tokens, response.completion_tokens)
        self._add_cost(cost_usd)
        
        trace = {
            "timestamp": datetime.utcnow().isoformat(),
            "provider_attempted": response.provider_name,
            "model": response.model_name,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "latency_ms": response.latency_ms,
            "total_latency_ms": total_latency,
            "success": response.success,
            "error": response.error,
            "error_type": response.error_type,
            "fallback_triggered": fallback_chain_depth > 0,
            "fallback_chain_depth": fallback_chain_depth,
            "response_format": request.response_format,
            "retrieval_coverage_score": retrieval_coverage,
            "estimated_cost_usd": cost_usd,
            "cumulative_daily_cost_usd": self.cumulative_daily_cost_usd,
            "cost_guard_triggered": self.cost_guard_triggered,
            "circuit_state": self.circuit_state.value
        }
        
        # Keep last 100 traces
        self.last_traces.insert(0, trace)
        if len(self.last_traces) > 100:
            self.last_traces.pop()
            
        status_log = "SUCCESS" if response.success else f"FAILED [{response.error_type}]"
        logger.info(
            f"AIGateway | {status_log} | {response.provider_name} | {total_latency}ms | "
            f"Depth:{fallback_chain_depth} | Cost:${cost_usd:.6f} | Error:{response.error}"
        )

    def _normalize_schema(self, response: AIResponse, schema: Dict[str, Any]) -> AIResponse:
        """Validates the parsed JSON against a strictly supplied JSON Schema Draft."""
        if not response.success or not response.parsed_output:
            return response
            
        try:
            validate(instance=response.parsed_output, schema=schema)
            return response
        except ValidationError as e:
            logger.warning(f"AIGateway: Schema normalization failed: {e.message}")
            response.success = False
            response.error = f"SCHEMA_VALIDATION_FAILED: {e.message}"
            response.error_type = "PARSE"
            response.parsed_output = None
            return response

    def _invoke_provider(self, provider_id: str, request: AIRequest) -> AIResponse:
        """Wrapper to call a provider and catch total catastrophic unhandled exceptions."""
        provider = self.providers.get(provider_id)
        if not provider:
            return AIResponse(
                raw_output="",
                model_name="unknown",
                provider_name=provider_id,
                success=False,
                error=f"Provider '{provider_id}' is not configured in Gateway.",
                error_type="UNKNOWN"
            )
            
        try:
            res = provider.generate(request)
            
            # Enforce schema validation if using structure
            if res.success and request.response_format == "json" and request.json_schema:
                res = self._normalize_schema(res, request.json_schema)
                
            return res
        except Exception as e:
            # Fallback wrapper for absolute worst-case SDK internal crashes
            logger.critical(f"AIGateway: Provider {provider_id} leaked an unhandled exception: {str(e)}")
            return AIResponse(
                raw_output="",
                model_name="unknown",
                provider_name=provider_id,
                success=False,
                error=f"Leaked Provider Exception: {str(e)}",
                error_type="UNKNOWN"
            )

    def _handle_zero_chunk_rag(self, request: AIRequest, retrieval_coverage_score: Optional[float]):
        """Injects a fallback prompt instruction if RAG returned nothing."""
        if retrieval_coverage_score is not None and retrieval_coverage_score == 0.0:
            fallback_instruction = "\n\nSYSTEM OVERRIDE: Limited retrieval context available. Provide generalized analysis."
            request.prompt += fallback_instruction

    def _invoke_speculative(self, primary_id: str, secondary_id: str, request: AIRequest) -> tuple[AIResponse, int]:
        """Races primary and secondary providers to minimize P95 tail latencies."""
        with ThreadPoolExecutor(max_workers=2) as executor:
            primary_future = executor.submit(self._invoke_provider, primary_id, request)
            
            # Delay before firing secondary aggressively (e.g. 1.5 seconds)
            delay = min(request.timeout_ms / 2000.0, 1.5)
            done, not_done = wait([primary_future], timeout=delay)
            
            if done:
                res = primary_future.result()
                if res.success:
                    return res, 0
                    
            # Primary lagging or failed. Check cloud cost guardrail before firing secondary
            if self.cost_guard_triggered and secondary_id != "local":
                logger.warning("AIGateway: Speculative execution blocked due to DEGRADED_NO_CLOUD.")
                if not primary_future.done():
                    wait([primary_future])
                return primary_future.result(), 0
                
            logger.info(f"AIGateway: Primary lagging. Spawning speculative fallback to '{secondary_id}'")
            secondary_future = executor.submit(self._invoke_provider, secondary_id, request)
            
            if primary_future.done() and not primary_future.result().success:
                return secondary_future.result(), 1
                
            done, not_done = wait([primary_future, secondary_future], return_when=FIRST_COMPLETED)
            
            first_finished = list(done)[0].result()
            if first_finished.success:
                return first_finished, 1 if first_finished.provider_name == secondary_id else 0
                
            # If the first one failed, wait for the trailing one
            remaining = list(not_done)
            if remaining:
                done, _ = wait(remaining)
                second_finished = remaining[0].result()
                return second_finished, 1 if second_finished.provider_name == secondary_id else 0
                
            return primary_future.result(), 0

    def execute(self, request: AIRequest, retrieval_coverage_score: Optional[float] = None) -> AIResponse:
        """
        Main entry point for AI inference. 
        Applies Circuit Breaking, Fallback Routing, Zero-Chunk interception, and Cost accounting.
        """
        # 1. Rate Limiting (SLA Enforcement)
        if not self.concurrency_semaphore.acquire(blocking=False):
            logger.error("AIGateway: Max concurrent requests exceeded (Rate Limited).")
            return AIResponse(
                raw_output="", model_name="unknown", provider_name="gateway",
                success=False, error="RATE_LIMIT_EXCEEDED", error_type="CONNECTION"
            )
            
        try:
            if not self._check_rate_limit():
                logger.error("AIGateway: Requests per minute limit exceeded (Rate Limited).")
                return AIResponse(
                    raw_output="", model_name="unknown", provider_name="gateway",
                    success=False, error="RATE_LIMIT_EXCEEDED", error_type="CONNECTION"
                )

            t_start = time.perf_counter()
            
            # Zero-Chunk RAG Interception
            self._handle_zero_chunk_rag(request, retrieval_coverage_score)
            
            # Dynamic override of timeout based on policy
            if self.policy.timeout_ms:
                request.timeout_ms = self.policy.timeout_ms

            chain_depth = 0
            primary_id = self.policy.primary
            
            # 2. Check Circuit Breaker State against Primary
            self._update_circuit_window()
            if self.circuit_state == CircuitState.OPEN:
                # Check if we can transition to HALF_OPEN (if window is completely free of failures because time passed)
                if not self.request_window:
                    self.circuit_state = CircuitState.HALF_OPEN
                    self.half_open_probe_active = True
                    logger.info("AIGateway: Circuit transitioned to HALF_OPEN. Allowing probe.")
                else:
                    logger.error("AIGateway: Primary circuit is OPEN. Fast-failing to Secondary.")
                    res = AIResponse(
                        raw_output="", model_name="unknown", provider_name=primary_id,
                        success=False, error="Circuit Breaker OPEN.", error_type="CONNECTION"
                    )
                    self._record_result(is_failure=True)
                    # Note: We skip the primary retry block entirely if OPEN
                    return self._trigger_secondary_fallback(request, res, t_start, chain_depth, retrieval_coverage_score)

            if self.circuit_state == CircuitState.HALF_OPEN and self.half_open_probe_active:
                # We already have a probe in flight concurrently, reject others until it lands
                logger.warning("AIGateway: HALF_OPEN probe currently active. Fast-failing parallel requests.")
                res = AIResponse(
                    raw_output="", model_name="unknown", provider_name=primary_id,
                    success=False, error="Circuit Breaker HALF_OPEN probe in progress.", error_type="CONNECTION"
                )
                return self._trigger_secondary_fallback(request, res, t_start, chain_depth, retrieval_coverage_score)
                
            if self.circuit_state == CircuitState.HALF_OPEN:
                self.half_open_probe_active = True

            # 3. Attempt Primary (Or Speculative)
            if self.enable_speculative_fallback and self.policy.secondary and self.circuit_state != CircuitState.OPEN and not self.half_open_probe_active:
                response, chain_depth = self._invoke_speculative(primary_id, self.policy.secondary, request)
                self._record_result(not response.success and response.provider_name == primary_id)
            else:
                response = self._invoke_provider(primary_id, request)
                self._record_result(not response.success)
            
            # 4. Handle Primary Failure & Retries
            if not response.success:
                logger.warning(f"AIGateway: Primary Provider '{primary_id}' Failed [{response.error_type}]: {response.error}")
                
                # Attempt Retry if Policy Allows
                if self.policy.max_retries > 0 and self.circuit_state != CircuitState.OPEN:
                    chain_depth += 1
                    logger.info(f"AIGateway: Triggering Primary Retry (Depth: {chain_depth})")
                    response = self._invoke_provider(primary_id, request)
                    self._record_result(not response.success)
                    
                # If still failing, route to Secondary Fallback
                if not response.success:
                    return self._trigger_secondary_fallback(request, response, t_start, chain_depth, retrieval_coverage_score)

            # 5. Primary Success - Log & Return
            total_ms = int((time.perf_counter() - t_start) * 1000)
            self._log_telemetry(request, response, total_ms, chain_depth, retrieval_coverage_score)
            return response
        finally:
            self.concurrency_semaphore.release()
        
    def _trigger_secondary_fallback(
        self, 
        request: AIRequest, 
        primary_last_response: AIResponse, 
        t_start: float,
        chain_depth: int, 
        retrieval_coverage_score: Optional[float]
    ) -> AIResponse:
        """Handles the secondary provider fallback logic."""
        secondary_id = self.policy.secondary
        
        # Guardrail check
        if self.cost_guard_triggered and secondary_id and secondary_id != "local":
            logger.warning("AIGateway: Fallback blocked due to DEGRADED_NO_CLOUD daily cost guardrail.")
            total_ms = int((time.perf_counter() - t_start) * 1000)
            self._log_telemetry(request, primary_last_response, total_ms, chain_depth, retrieval_coverage_score)
            return primary_last_response
            
        if not secondary_id or secondary_id not in self.providers:
            logger.error("AIGateway: Exhausted Fallback Route! Secondary Provider not configured.")
            total_ms = int((time.perf_counter() - t_start) * 1000)
            self._log_telemetry(request, primary_last_response, total_ms, chain_depth, retrieval_coverage_score)
            return primary_last_response
            
        chain_depth += 1
        logger.warning(f"AIGateway: Falling back to Secondary Provider '{secondary_id}'")
        sec_response = self._invoke_provider(secondary_id, request)
        
        total_ms = int((time.perf_counter() - t_start) * 1000)
        self._log_telemetry(request, sec_response, total_ms, chain_depth, retrieval_coverage_score)
        
        # If secondary fails, we emit its degraded response directly to the orchestrator mapping (No infinite chains).
        return sec_response

    def get_health(self) -> Dict[str, Any]:
        """Provides operational diagnostics across the Gateway."""
        self._update_circuit_window()
        
        total_reqs = len(self.request_window)
        failures = sum(1 for _, is_fail in self.request_window if is_fail)
        failure_rate = (failures / total_reqs) if total_reqs > 0 else 0.0

        # Calculate Rolling Latency over the last 10 successful traces
        successful_traces = [t for t in self.last_traces if t.get("success")]
        rolling_latency = 0.0
        if successful_traces:
            rolling_latency = sum(t.get("total_latency_ms", 0) for t in successful_traces[:10]) / len(successful_traces[:10])

        return {
            "status": "DEGRADED" if self.circuit_state != CircuitState.CLOSED else "OPERATIONAL",
            "primary_provider": self.policy.primary,
            "secondary_provider": self.policy.secondary,
            "circuit_breaker": {
                "state": self.circuit_state.value,
                "failures_in_window": failures,
                "total_in_window": total_reqs,
                "failure_rate": f"{failure_rate:.1%}",
                "window_seconds": self.window_seconds,
                "threshold_rate": f"{self.failure_rate_threshold:.1%}"
            },
            "rolling_latency_ms": round(rolling_latency, 1),
            "last_error_timestamp": self.last_error_timestamp,
            "recent_traces": self.last_traces[:10]  # Return top 10 for UI debug
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Provides high-level SLA Observability Metrics for Prometheus/Monitoring."""
        self._update_circuit_window()
        total_traces = len(self.last_traces)
        if total_traces == 0:
            return {"status": SystemStatus.NORMAL.value, "traces_recorded": 0}
            
        latencies = sorted([t["total_latency_ms"] for t in self.last_traces if t.get("success")])
        p50 = latencies[int(len(latencies) * 0.5)] if latencies else 0.0
        p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0
        
        fallbacks = sum(1 for t in self.last_traces if t.get("fallback_triggered"))
        fallback_ratio = fallbacks / total_traces
        
        schema_failures = sum(1 for t in self.last_traces if t.get("error_type") == "PARSE")
        schema_failure_rate = schema_failures / total_traces
        
        # Calculate retrieval coverage
        coverage_scores = [t["retrieval_coverage_score"] for t in self.last_traces if t.get("retrieval_coverage_score") is not None]
        avg_coverage = (sum(coverage_scores) / len(coverage_scores)) if coverage_scores else 0.0
        
        failure_rate_60s = 0.0
        if self.request_window:
            total_reqs = len(self.request_window)
            failures = sum(1 for _, is_fail in self.request_window if is_fail)
            failure_rate_60s = failures / total_reqs
            
        # Determine strict system state
        system_status = SystemStatus.NORMAL
        if self.circuit_state == CircuitState.OPEN:
            system_status = SystemStatus.CIRCUIT_OPEN
        elif self.cost_guard_triggered:
            system_status = SystemStatus.DEGRADED_NO_CLOUD
        # We check private attr _value for Semaphore capacity to guess Rate Limited load
        elif len(self.rpm_window) >= self.max_rpm or getattr(self.concurrency_semaphore, '_value', 1) == 0:
            system_status = SystemStatus.RATE_LIMITED
        elif fallback_ratio > 0.5:
            system_status = SystemStatus.DEGRADED_PRIMARY_ONLY
            
        return {
            "status": system_status.value,
            "circuit_state": self.circuit_state.value,
            "p50_latency_ms": round(p50, 1),
            "p95_latency_ms": round(p95, 1),
            "failure_rate_last_60s": round(failure_rate_60s, 3),
            "fallback_ratio": round(fallback_ratio, 3),
            "schema_failure_rate": round(schema_failure_rate, 3),
            "retrieval_coverage_score_avg": round(avg_coverage, 3),
            "cumulative_daily_cost_usd": round(self.cumulative_daily_cost_usd, 4),
            "traces_recorded": total_traces
        }
