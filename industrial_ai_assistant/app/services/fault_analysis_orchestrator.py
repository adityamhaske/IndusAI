"""
FaultAnalysisOrchestrator — Central coordinator for fault analysis.

Pipeline:
  1. Get FaultRecord + deterministic stats from FaultService
  2. Call RAGService to retrieve relevant documentation
  3. Build structured prompt (fault context + stats + docs + question)
  4. Call LLM via LLMInterface
  5. Parse structured JSON output into StructuredLLMOutput
  6. Retry once if parsing fails
  7. Validate with FaultResponseValidator (hallucination check, schema)
  8. Return FaultAnalysisV2Response

Design principles:
  - LLM NEVER computes confidence (that's fault_confidence.py)
  - LLM NEVER receives raw CSV
  - RAG is non-blocking: empty results → continue with stats only
  - Full observability: timing breakdowns in every response
"""
import json
import logging
import os
import re
import time
from typing import List, Optional

from app.core.fault_exceptions import (
    AnalysisPrerequisiteError,
    DatasetHashMismatchError,
    DatasetNotLoadedError,
    FaultRowNotFoundError,
)
from app.services.ai_gateway import AIGatewayService
from app.models.ai_models import AIRequest
from app.core.llm_exceptions import LLMConnectionError, LLMResponseParseError
from app.models.fault_analysis_models import (
    FaultAnalysisRequest,
    FaultAnalysisV2Response,
    RetrievedDoc,
    StructuredLLMOutput,
)
from app.services.fault_response_validator import FaultResponseValidator
from app.services.fault_service import FaultService, get_fault_service
from app.services.rag_service import RAGService
from app.utils.fault_confidence import compute_confidence
from app.utils.fault_statistics import (
    _timestamps_for_code,
    check_metric_integrity,
    compute_cooccurrence,
    compute_occurrences_in_window,
    compute_rolling_metrics,
    compute_trend,
)

logger = logging.getLogger(__name__)

# Debug prompt logging — set DEBUG_LLM=true in env to log full prompts
_DEBUG_LLM = os.getenv("DEBUG_LLM", "false").lower() in ("1", "true", "yes")

_LLM_JSON_SCHEMA = """{
  "diagnosis": "<Max 3 lines. Concise. No filler. No speculations.>",
  "metrics": {
    "occurrences_1h": <int>,
    "occurrences_24h": <int>,
    "burst_detected": <bool>,
    "burst_window_minutes": <float>,
    "burst_count": <int>,
    "co_occurrence": [{"fault": "<str>", "count": <int>}],
    "trend": "<RISING | STABLE | DECLINING>"
  },
  "primary_action": "<Single concrete, targeted technical action.>",
  "confidence": "<LOW | MEDIUM | HIGH>"
}"""

# Fallback OUTPUT is removed — failures now raise explicit exceptions.
# Use _FALLBACK_RESPONSE ONLY for test mocking, not in production pipeline.


class FaultAnalysisOrchestrator:
    """Orchestrates deterministic stats + RAG + AIGateway LLM into a single structured response."""

    def __init__(
        self,
        llm: AIGatewayService,
        rag_service: RAGService,
        validator: FaultResponseValidator,
        fault_service: Optional[FaultService] = None,
        health_service=None,   # Optional injection for testing
    ):
        self._llm = llm
        self._rag = rag_service
        self._validator = validator
        self._fault_svc = fault_service or get_fault_service()
        self._health = health_service  # lazy-init on first use

    def _get_health_service(self):
        if self._health is None:
            from app.services.system_health_service import get_health_service
            self._health = get_health_service()
        return self._health

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze_fault(self, request: FaultAnalysisRequest) -> FaultAnalysisV2Response:
        """Full pipeline: preflight → stats → RAG → LLM → validate → return."""
        t_total_start = time.perf_counter()

        # ── Step 0: Preflight connectivity check ─────────────────────────────
        hs = self._get_health_service()
        llm_status = hs.check_llm()
        if not llm_status["ok"]:
            reason = llm_status.get("reason", "Unknown reason")
            logger.error(
                "LLM pre-flight failed (provider=%s url=%s): %s",
                llm_status.get("provider"), llm_status.get("url"), reason
            )
            raise LLMConnectionError(
                f"Local LLM ({llm_status.get('provider', 'unknown')}) is not reachable: {reason}. "
                f"Please start Ollama: `ollama serve`"
            )

        # ── Step 1: Load dataset & row ────────────────────────────────────────
        ds = self._fault_svc._store.get(request.project_id)
        if ds is None:
            raise DatasetNotLoadedError()

        df = ds.dataframe
        matches = df[df["row_id"] == request.row_id]
        if matches.empty:
            raise FaultRowNotFoundError(request.row_id)
        if not ds.stats_cache:
            raise AnalysisPrerequisiteError("Stats cache empty — re-upload dataset.")

        row = matches.iloc[0]
        fault_code = str(row["fault_code"])
        device = str(row["device"])
        message = str(row["message"])
        severity = str(row.get("severity", "")) if row.get("severity") else "Unknown"
        ref_ts = row["timestamp"].to_pydatetime()

        # ── Step 2: Deterministic stats & Advanced Metrics (v3) ──────────────────
        ts_list = _timestamps_for_code(df, fault_code)
        
        # Original metrics
        occ_1h  = compute_occurrences_in_window(ts_list, ref_ts, hours=1)
        occ_24h = compute_occurrences_in_window(ts_list, ref_ts, hours=24)
        co_fault, co_count = compute_cooccurrence(df, ref_ts)
        burst = ds.stats_cache.get("burst_detected", False)
        burst_desc = ds.stats_cache.get("burst_description", "")
        burst_count = ds.stats_cache.get("burst_count", 0)
        
        # Advanced v3 metrics
        rolling_avg_5m, rolling_avg_1h, delta_last_30m, anomaly_score = compute_rolling_metrics(ts_list, ref_ts)
        trend = compute_trend(delta_last_30m, rolling_avg_1h)
        
        # Integrity validation
        integrity_passed = check_metric_integrity(burst, burst_count, occ_1h, anomaly_score)
        
        confidence = compute_confidence(
            burst_detected=burst,
            anomaly_score=anomaly_score,
            integrity_passed=integrity_passed,
            occurrences_1h=occ_1h
        )

        statistics = {
            "occurrences_last_hour": occ_1h,
            "occurrences_last_24h": occ_24h,
            "top_cooccurring_fault": co_fault,
            "cooccurrence_count": co_count,
            "burst_detected": burst,
            "burst_description": burst_desc,
            "burst_count": burst_count,
            "confidence": confidence,
            "rolling_avg_5m": rolling_avg_5m,
            "rolling_avg_1h": rolling_avg_1h,
            "delta_last_30m": delta_last_30m,
            "anomaly_score": anomaly_score,
            "trend": trend,
            "integrity_passed": integrity_passed
        }

        # ── Step 3: RAG retrieval ─────────────────────────────────────────────
        rag_docs, rag_ms = self._rag.retrieve_for_fault(
            fault_code=fault_code,
            fault_message=message,
            device=device,
            user_question=request.question,
            project_id=request.project_id,
        )

        # ── Step 4: Build prompt & Check Integrity ────────────────────────────
        if not integrity_passed:
            logger.warning("Stat integrity failed or sample-size trace too small for row %d. Bypassing LLM.", request.row_id)
            total_ms = (time.perf_counter() - t_total_start) * 1000
            
            # Construct a synthetic successful response masking the LLM output
            synthetic_evidence = {
                "occurrences_1h": occ_1h,
                "occurrences_24h": occ_24h,
                "burst_detected": burst,
                "burst_window_minutes": ds.stats_cache.get("burst_window_minutes", 10.0), # Defaulting from stats engine
                "burst_count": burst_count,
                "co_occurrence": [{"fault": co_fault, "count": co_count}] if co_fault else [],
                "trend": trend
            }

            return FaultAnalysisV2Response(
                analysis_version="v3.0",
                dataset_hash=ds.dataset_hash,
                row_id=request.row_id,
                fault_code=fault_code,
                device=device,
                timestamp=ref_ts,
                user_question=request.question,
                confidence="LOW",
                statistics=statistics,
                evidence=synthetic_evidence,
                diagnosis="DATA INTEGRITY WARNING / INSUFFICIENT SAMPLE. Statistical inconsistency detected. LLM explanation suppressed.",
                primary_action="Verify telemetry sensor logs and re-index dataset constraints.",
                docs_used=0,
                sources=[],
                hallucinated_tags_removed=[],
                validation_warnings=["Metric validation blocked LLM inference."],
                llm_latency_ms=0.0,
                rag_latency_ms=round(rag_ms, 1),
                total_latency_ms=round(total_ms, 1),
            )

        prompt = _build_prompt(
            row_id=request.row_id,
            fault_code=fault_code,
            device=device,
            ref_ts=ref_ts,
            severity=severity,
            message=message,
            occ_1h=occ_1h,
            occ_24h=occ_24h,
            co_fault=co_fault,
            co_count=co_count,
            burst_detected=burst,
            burst_desc=burst_desc,
            burst_count=burst_count,
            trend=trend,
            confidence=confidence,
            docs=rag_docs,
            user_question=request.question,
        )

        if _DEBUG_LLM:
            logger.debug("[DEBUG_LLM] Full prompt:\n%s", prompt)

        # Telemetry calculation for L9 review:
        prompt_len = len(prompt)
        doc_len = sum(len(d.content) for d in rag_docs)
        retrieval_coverage_score = (doc_len / prompt_len) if prompt_len > 0 else 0.0

        # ── Step 5: LLM call (with retry) ────────────────────────────────────
        t_llm_start = time.perf_counter()
        llm_output, is_fallback, raw_output = self._call_llm_with_retry(prompt, retrieval_coverage_score=retrieval_coverage_score)
        llm_ms = (time.perf_counter() - t_llm_start) * 1000

        # ── Step 6: Validation ────────────────────────────────────────────────
        doc_sources = [d.source_file for d in rag_docs]
        
        if llm_output is not None:
            cleaned, hallucinated, val_warnings = self._validator.validate(
                llm_output, doc_sources, known_tags=None
            )
            diagnosis_text = cleaned.diagnosis
            action_text = cleaned.primary_action
            evidence_data = cleaned.metrics
            final_confidence = cleaned.confidence or confidence
        else:
            # L9 JSON Resiliency fallback
            logger.error("JSON parsing failed entirely for row %d. Degrading to raw text display.", request.row_id)
            diagnosis_text = f"[STRUCTURED PARSE FAILED - RAW OUTPUT]\n{raw_output}"
            action_text = "Manual Review Required - AI Response was malformed."
            evidence_data = statistics # Fallback to deterministic stats
            final_confidence = "LOW"
            hallucinated = []
            val_warnings = ["LLM response was not valid JSON. Returned raw text instead."]

        total_ms = (time.perf_counter() - t_total_start) * 1000

        logger.info(
            "Analysis complete: fault=%s row=%d confidence=%s docs=%d "
            "rag=%.0fms llm=%.0fms total=%.0fms",
            fault_code, request.row_id, confidence, len(rag_docs),
            rag_ms, llm_ms, total_ms,
        )

        return FaultAnalysisV2Response(
            analysis_version="v3.0",
            dataset_hash=ds.dataset_hash,
            row_id=request.row_id,
            fault_code=fault_code,
            device=device,
            timestamp=ref_ts,
            user_question=request.question,
            confidence=final_confidence,
            statistics=statistics,
            evidence=evidence_data,  # Maps clean nested v3 metrics structure
            diagnosis=diagnosis_text,
            primary_action=action_text,
            docs_used=len(rag_docs),
            sources=rag_docs,
            hallucinated_tags_removed=hallucinated,
            validation_warnings=val_warnings,
            llm_latency_ms=round(llm_ms, 1),
            rag_latency_ms=round(rag_ms, 1),
            total_latency_ms=round(total_ms, 1),
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _call_llm_with_retry(
        self, prompt: str, max_retries: int = 1, retrieval_coverage_score: Optional[float] = None
    ) -> tuple[Optional[StructuredLLMOutput], bool, str]:
        """
        Call LLM Gateway and parse response. Retry once on parse failure.
        Raises LLMConnectionError on timeout/connection failure.
        Returns (parsed_output, is_fallback, raw_output). parsed_output is None if schema validations fail.
        """
        last_exc = None
        raw_out = ""
        for attempt in range(max_retries + 1):
            t0 = time.perf_counter()
            req = AIRequest(
                prompt=prompt,
                response_format="json",
                json_schema=StructuredLLMOutput.schema()
            )
            res = self._llm.execute(req, retrieval_coverage_score=retrieval_coverage_score)
            raw_out = res.raw_output
            
            logger.debug("LLM attempt %d raw response (%.0fms): %s",
                         attempt + 1, (time.perf_counter() - t0) * 1000, res.raw_output[:120])
                         
            if res.success and res.parsed_output:
                try:
                    parsed = StructuredLLMOutput(**res.parsed_output)
                    return parsed, False, raw_out
                except Exception as exc:
                    last_exc = exc
                    logger.warning("LLM attempt %d/%d pydantic schema validation failed: %s", attempt + 1, max_retries + 1, exc)
            else:
                if res.error_type in ["CONNECTION", "TIMEOUT"]:
                    raise LLMConnectionError(f"Gateway Error: {res.error}")
                last_exc = res.error
                logger.warning("LLM attempt %d/%d execute failed: %s", attempt + 1, max_retries + 1, res.error)

        logger.error("LLM failed to return valid JSON. Degrading to raw text. Last Error: %s", last_exc)
        return None, False, raw_out


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(
    row_id, fault_code, device, ref_ts, severity, message,
    occ_1h, occ_24h, co_fault, co_count, burst_detected, burst_desc, burst_count, trend,
    confidence, docs, user_question,
) -> str:
    doc_section = ""
    if docs:
        doc_parts = []
        for i, doc in enumerate(docs, 1):
            title = doc.section_title or doc.source_file
            doc_parts.append(f"[Doc {i} — {title}]\n{doc.content[:600]}")
        doc_section = "\n\nDOCUMENTATION CONTEXT:\n" + "\n\n".join(doc_parts)
    else:
        doc_section = "\n\nDOCUMENTATION CONTEXT:\n(No documents retrieved — respond from statistics only)"

    question_section = ""
    if user_question:
        question_section = f"\n\nUSER QUESTION:\n{user_question}"

    return f"""You are a PLC commissioning assistant. Analyze the fault using the provided statistics and documentation context.

FAULT DETAILS:
  Row ID: {row_id}
  Code: {fault_code}
  Device: {device}
  Timestamp: {ref_ts.isoformat()}
  Severity: {severity}
  Message: {message}

STATISTICS (deterministic — do NOT recompute, map exactly into JSON output):
  Occurrences_1h: {occ_1h}
  Occurrences_24h: {occ_24h}
  Co_occurrence Fault: {co_fault or "None"}
  Co_occurrence Count: {co_count}
  Burst detected: {"true" if burst_detected else "false"}
  Burst count: {burst_count}
  Trend: {trend}
  Confidence level (determined externally): {confidence}{doc_section}{question_section}

OUTPUT RULES:
  - Return ONLY valid JSON matching this exact schema (no prose outside JSON):
  - 'diagnosis' must be a SINGLE high-impact string (max 3 lines). DO NOT use filler words or conversational phrasing ("it appears", "it may indicate").
  - Map deterministic STATISTICS directly into the nested 'metrics' JSON object. Do not hallucinate values.
  - 'primary_action' must be ONE concrete, technically targeted action. Do NOT give generic "inspect hardware" advice.
  - Do NOT invent PLC tag names not present in documentation.
  - Do NOT invent document sections.

{_LLM_JSON_SCHEMA}
"""


def _parse_llm_json(raw: str) -> StructuredLLMOutput:
    """Extract JSON from LLM output and parse into StructuredLLMOutput."""
    # Try full parse first
    try:
        data = json.loads(raw.strip())
        return StructuredLLMOutput(**data)
    except Exception:
        pass

    # Try regex extraction of JSON block
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return StructuredLLMOutput(**data)
        except Exception:
            pass

    raise ValueError(f"LLM output could not be parsed as StructuredLLMOutput. Raw: {raw[:200]}")
