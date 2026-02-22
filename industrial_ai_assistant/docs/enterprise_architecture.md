# Enterprise Security & Deployment Architecture

## Deployment Topology
**Hybrid Edge + Cloud Structure**
1. **Air-Gapped Core:** The `FastAPI` instance, `Qdrant` vector database, and the `Ollama` language model run heavily optimized on local site-hosted hardware (e.g., Industrial IoT edge Gateways). This ensures sub-second processing of proprietary PLC L5X sequences and protects sensitive IP.
2. **Speculative Cloud Extender:** (Optional) API requests mapping to `OpenAI` or `Gemini` can be safely toggled to assist the edge node if complex diagnostics fail. 

## Immutable Versioning
The `GET /api/system/version` endpoint explicitly exports the semantic state of the engine:
- `stat_engine_version`: The math powering the `anomaly_score` and `integrity_passed` evaluations.
- `schema_version`: The precise mapping structure expected from the LLMs.
- `app_version`: The API interface version.

## Security Posture
- **API Key Secrecy**: The system utilizes environment injection (`.env`) parsed via `Pydantic BaseSettings`. Keys are instantiated precisely into the Provider classes and are violently trapped by `AIGatewayService` exception catchers. SDK tracebacks are squashed so keys are NEVER logged or exposed to the frontend.
- **Docker Hardening**: The official `Dockerfile` executes as a `non-root` `appuser`, separating build tooling into multistage blocks and retaining zero runtime development dependencies in production environments.
- **Dependency Sandboxing**: CI/CD Pipelines assert explicit automated verification using `bandit` (SAST) and `pip-audit` for dependency vulnerabilities blocking merging.

## Deterministic Guard Rails
- Any data passed into the LLM is first validated logically. E.g., if a fault sequence indicates a burst of 100 but the 1H rolling average is 0, the engine trips `integrity_passed=False`. The LLM inference is completely bypassed and marked explicitly as a Data Integrity Exception to eliminate hallucination.
- Any output from the LLM failing the pre-defined `v3.0` Pydantic models triggers an instant `SCHEMA_VALIDATION_FAILED` network drop, gracefully shifting to an alternative provider or fallback UI state.
