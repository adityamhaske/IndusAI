# Industrial AI Assistant - Enterprise Incident Playbook
## Performance Guardrails & SLOs

The IndusAI system is designed for deterministic fault diagnostics. To maintain trust in enterprise and air-gapped environments, the following Service Level Objectives (SLOs) are strictly enforced and monitored via Prometheus (`/api/ai/metrics`):

- **P95 Latency:** `< 2.5s` (End-to-end, including Semantic Indexing lookup and LLM Generation)
- **Primary Failure Rate:** `< 5%` over any 60-second sliding window
- **Fallback Ratio:** `< 15%` (The system should rarely need to rely on Cloud tokens)
- **Daily Cost Variance:** `< 10%` daily deviation against expected token models
- **Schema Validation Rate:** `100%` (Zero tolerance for unstructured hallucination parsing)

## Playbook Scenarios & Automated Responses

### Scenario 1: Catastrophic Hardware / Edge Node Failure (Local Ollama)
**Trigger Metrics:**
- `failure_rate_last_60s > 30%`
- `ai_gateway_status = 1 (DEGRADED)`
- `circuit_state = OPEN` (> 5 min)
**Automated Action:**
1. AIGatewayService opens the circuit to protect the failing local LLM container from cascading timeouts.
2. `fallback_ratio` climbs dramatically.
**Engineering Response:**
- Force-restart the `ollama` daemon on the edge device.
- The `AIGatewayService` will automatically transition to `HALF_OPEN` and fire a probe request. If successful, the circuit will return to `CLOSED` and Cloud Fallback will drop.

### Scenario 2: Uncontrollable Cloud Inference Spikes
**Trigger Metrics:**
- `fallback_ratio > 50%`
- `ai_gateway_cumulative_daily_cost_usd > MAX_DAILY_COST_USD`
**Automated Action:**
1. System transitions internally to `DEGRADED_NO_CLOUD`.
2. All subsequent queries failing the primary provider will **abort immediately** returning the deterministic error `"DATA INTEGRITY WARNING"`.
**Engineering Response:**
- Adjust the `MAX_DAILY_COST_USD` budget if it was artificially too low for the current volume.
- Evaluate the root cause of the local Ollama failure that triggered the heavy fallback volume to begin with.
- A restart of the FastAPI container will reset the cost guard.

### Scenario 3: Cloud Provider Rate Limiting (OpenAI 429s)
**Trigger Metrics:**
- `ai_gateway_status = RATE_LIMITED`
- Semaphore blocked metrics spike.
**Automated Action:**
1. Requests attempting to exceed `max_concurrent_requests` (Default: `20`) or `max_rpm` (Default: `100`) will degrade gracefully without locking the async event loop.
**Engineering Response:**
- If the volume is expected, adjust the limits in `AIGatewayService` initialization.
- Otherwise, investigate anomalous traffic bursts.
