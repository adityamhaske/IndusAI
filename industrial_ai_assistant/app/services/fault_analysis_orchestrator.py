"""
FaultAnalysisOrchestrator — Central coordinator for fault analysis (Phase 21).

Pipeline (v4 — Intelligence Upgrade):
  1. Preflight connectivity check
  2. Load dataset & row + deterministic stats
  3. Record into Fault Memory (persistent pattern store)
  4. RAG retrieval (hybrid: BM25 + Vector + RRF)
  5. Check Intelligent Cache → return if hit
  6. Retrieve historical pattern + past experience
  7. Build structured prompt via PromptComposerV2
  8. Call LLM via AIGateway (with retry)
  9. Compute ConfidenceV2 (numeric 0-100%%)
 10. Store experience in FaultExperienceIndex
 11. Store in Intelligent Cache
 12. Validate + return FaultAnalysisV2Response

Design principles:
  - LLM NEVER computes confidence (that's confidence_v2.py)
  - LLM NEVER receives raw CSV
  - RAG is non-blocking: empty results → continue with stats only
  - Full observability: timing breakdowns in every response
  - Self-improving: every analysis feeds the experience index
"""
import json
import logging
import os
import re
import time
from typing import List, Optional, Any

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
    FlexibleLLMOutput,
)
from app.services.query_classifier import classify
from app.models.project_models import IntentType
from app.services.fault_response_validator import FaultResponseValidator
from app.services.fault_service import FaultService, get_fault_service
from app.services.rag_service import RAGService
from app.utils.fault_confidence import compute_confidence
from app.utils.confidence_v2 import compute_confidence_v2
from app.prompts.prompt_v2 import PromptComposerV2

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

# ── Phase 21: Lazy-init singletons ────────────────────────────────────────────

_fault_memory_instance = None
_fault_experience_instance = None


def _get_fault_memory():
    global _fault_memory_instance
    if _fault_memory_instance is None:
        from app.services.fault_memory import FaultMemoryService
        from app.storage.firestore_client import get_firestore
        _fault_memory_instance = FaultMemoryService(get_firestore())
    return _fault_memory_instance


def _get_fault_experience():
    global _fault_experience_instance
    if _fault_experience_instance is None:
        from app.services.fault_experience_index import FaultExperienceIndex
        from app.storage.firestore_client import get_firestore
        _fault_experience_instance = FaultExperienceIndex(get_firestore())
    return _fault_experience_instance


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

_FLEXIBLE_JSON_SCHEMA = """{
  "summary": "<Comprehensive explanation of the topic.>",
  "key_points": ["<Point 1>", "<Point 2>"],
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

    def analyze_fault(self, request: FaultAnalysisRequest, uid: str = "") -> FaultAnalysisV2Response:
        """Full pipeline: stats → memory → RAG → LLM → validate → return."""
        t_total_start = time.perf_counter()

        # Preflight removed — BYOK provider errors are caught at LLM call time

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

        # ── Step 3: Record into Fault Memory ────────────────────────────────
        historical_pattern = None
        past_experience = None
        try:
            fault_mem = _get_fault_memory()
            fault_mem.record_fault(
                uid=uid,
                machine_id=device,
                fault_code=fault_code,
                timestamp=ref_ts,
                co_occurring_fault=co_fault,
                project_id=request.project_id,
            )
            historical_pattern = fault_mem.get_pattern_summary(uid, fault_code, machine_id=device)

            exp_idx = _get_fault_experience()
            past_experience = exp_idx.get_best_experience(uid, fault_code, machine_id=device)
        except Exception as mem_exc:
            logger.warning("Memory layer failed (non-fatal): %s", mem_exc)

        # ── Step 4: RAG retrieval (hybrid: BM25 + Vector + RRF) ──────────────
        rag_docs, rag_ms = self._rag.retrieve_for_fault(
            fault_code=fault_code,
            fault_message=message,
            device=device,
            user_question=request.question,
            project_id=request.project_id,
        )

        # ── Step 4b: Integrity Check ──────────────────────────────────────────
        if not integrity_passed:
            logger.warning("Stat integrity failed for row %d. LLM will continue but user should manually verify.", request.row_id)

        # ── Step 5: Classify Intent + Build PromptV2 ───────────────────────
        intent_val = IntentType.FAULT_ANALYSIS.value
        if request.question:
            intent_result = classify(request.question)
            intent_val = intent_result.intent_type

        is_fault_intent = intent_val in (
            IntentType.FAULT_ANALYSIS.value,
            IntentType.ROOT_CAUSE_DEEP_DIVE.value,
        )
        schema_model = StructuredLLMOutput if is_fault_intent else FlexibleLLMOutput

        # Format stats for prompt
        stats_text = (
            f"Occurrences (1h): {occ_1h}\n"
            f"Occurrences (24h): {occ_24h}\n"
            f"Co-occurring fault: {co_fault} ({co_count} times)\n"
            f"Burst detected: {burst} ({burst_desc})\n"
            f"Trend: {trend}\n"
            f"Anomaly score: {anomaly_score or 0.0:.2f}\n"
            f"Integrity: {'PASSED' if integrity_passed else 'FAILED'}"
        )

        fault_ctx = (
            f"Row ID: {request.row_id}\n"
            f"Fault Code: {fault_code}\n"
            f"Device: {device}\n"
            f"Severity: {severity}\n"
            f"Message: {message}\n"
            f"Timestamp: {ref_ts.isoformat()}"
        )

        docs_text = None
        if rag_docs:
            doc_parts = []
            for i, d in enumerate(rag_docs, 1):
                score_str = f" (relevance: {d.relevance_score:.4f})" if d.relevance_score else ""
                doc_parts.append(
                    f"--- Document {i}{score_str} ---\n"
                    f"Source: {d.source_file}\n"
                    f"Section: {d.section_title or 'N/A'}\n"
                    f"Content:\n{d.content[:2000]}"
                )
            docs_text = "\n\n".join(doc_parts)

        prompt = PromptComposerV2.compose(
            intent_type=intent_val,
            user_query=request.question or f"Analyze fault {fault_code} on {device}",
            statistical_snapshot=stats_text,
            historical_pattern=historical_pattern,
            past_experience=past_experience,
            manual_sections=docs_text,
            fault_context=fault_ctx,
        )

        if _DEBUG_LLM:
            logger.debug("[DEBUG_LLM] Full PromptV2:\n%s", prompt)

        # Telemetry
        prompt_len = len(prompt)
        doc_len = sum(len(d.content) for d in rag_docs)
        retrieval_coverage_score = (doc_len / prompt_len) if prompt_len > 0 else 0.0

        # ── Step 7: LLM call (with retry) ────────────────────────────────────
        t_llm_start = time.perf_counter()
        llm_output, is_fallback, raw_output = self._call_llm_with_retry(
            prompt, 
            schema_model=schema_model,
            retrieval_coverage_score=retrieval_coverage_score,
            retrieval_chunk_count=len(rag_docs),
            intent_type=intent_val
        )
        llm_ms = (time.perf_counter() - t_llm_start) * 1000

        # ── Step 8: Validation ────────────────────────────────────────────────
        doc_sources = [d.source_file for d in rag_docs]
        
        if llm_output is not None:
            if isinstance(llm_output, FlexibleLLMOutput):
                fault_summary = llm_output.summary
                root_cause = "General query response"
                trigger_mechanism = "See summary"
                resolution_steps = llm_output.key_points
                final_confidence = llm_output.confidence or confidence
                hallucinated = []
                val_warnings = []
            else:
                cleaned, hallucinated, val_warnings = self._validator.validate(
                    llm_output, doc_sources, known_tags=None, raw_text=raw_output
                )
                fault_summary = cleaned.fault_summary
                root_cause = cleaned.root_cause
                trigger_mechanism = cleaned.trigger_mechanism
                resolution_steps = cleaned.resolution_steps
                final_confidence = cleaned.confidence or confidence
        else:
            logger.error("JSON parsing failed entirely for row %d. Degrading to raw text.", request.row_id)
            
            # Step 1: Run FaultResponseValidator on the raw text
            _, hallucinated, val_warnings = self._validator.validate(
                raw_output, doc_sources, known_tags=None, raw_text=raw_output
            )
            
            # Step 2: Use mapping
            fault_summary = "[PARSE FAILED] " + raw_output[:500]
            root_cause = "Unable to determine — LLM output failed structured validation twice. Raw response preserved in fault_summary."
            trigger_mechanism = "Unknown — see fault_summary for raw LLM output."
            resolution_steps = [
                "Review raw LLM output in fault_summary.",
                "Re-run analysis or check your API key is valid.",
                "Contact support if issue persists."
            ]
            final_confidence = "LOW"
            val_warnings.append("LLM response was not valid JSON. Returned raw text instead.")

        # ── Step 9: Confidence V2 (numeric 0-100%) ───────────────────────────
        retrieval_scores = [d.relevance_score for d in rag_docs if d.relevance_score]
        confidence_numeric, confidence_label = compute_confidence_v2(
            retrieval_scores=retrieval_scores,
            historical_match=(historical_pattern is not None),
            context_coverage_ratio=retrieval_coverage_score,
            anomaly_score=anomaly_score,
            output_length=len(fault_summary) if fault_summary else 0,
        )
        # Use V2 label as the public-facing confidence
        final_confidence = confidence_label

        # ── Step 10: Store Experience (self-improving) ─────────────────────
        try:
            if fault_summary and not fault_summary.startswith("[") and uid:
                exp_idx = _get_fault_experience()
                exp_idx.store_experience(
                    uid=uid,
                    fault_code=fault_code,
                    explanation_text=fault_summary,
                    confidence=confidence_numeric,
                    machine_id=device,
                    project_id=request.project_id,
                    retrieval_score_avg=sum(retrieval_scores) / len(retrieval_scores) if retrieval_scores else None,
                )
        except Exception as exp_exc:
            logger.warning("Experience store failed (non-fatal): %s", exp_exc)

        total_ms = (time.perf_counter() - t_total_start) * 1000
        # Removed: intelligent cache put (cache deleted per architecture redesign)

        # ── Step 11: Build & Cache Response ───────────────────────────────────
        response = FaultAnalysisV2Response(
            analysis_version="v4.0",
            dataset_hash=ds.dataset_hash,
            row_id=request.row_id,
            fault_code=fault_code,
            device=device,
            timestamp=ref_ts,
            user_question=request.question,
            confidence=final_confidence,
            statistics=statistics,
            fault_summary=fault_summary,
            root_cause=root_cause,
            trigger_mechanism=trigger_mechanism,
            resolution_steps=resolution_steps,
            docs_used=len(rag_docs),
            sources=rag_docs,
            hallucinated_tags_removed=hallucinated,
            validation_warnings=val_warnings,
            llm_latency_ms=round(llm_ms, 1),
            rag_latency_ms=round(rag_ms, 1),
            total_latency_ms=round(total_ms, 1),
        )



        # ── Observability (Phase 21) ─────────────────────────────────────────
        logger.info(
            "Analysis v4 complete: fault=%s row=%d intent=%s confidence=%.0f%%(%s) "
            "docs=%d cache=MISS rag=%.0fms llm=%.0fms total=%.0fms "
            "historical=%s experience=%s",
            fault_code, request.row_id, intent_val,
            confidence_numeric * 100, confidence_label,
            len(rag_docs), rag_ms, llm_ms, total_ms,
            "YES" if historical_pattern else "NO",
            "YES" if past_experience else "NO",
        )

        return response

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _call_llm_with_retry(
        self, prompt: str, schema_model: Any, max_retries: int = 1, retrieval_coverage_score: Optional[float] = None, retrieval_chunk_count: int = 0, intent_type: Optional[str] = None
    ) -> tuple[Optional[Any], bool, str]:
        """
        Call LLM Gateway and parse response. Retry once on parse failure or low quality.
        Raises LLMConnectionError on timeout/connection failure.
        Returns (parsed_output, is_fallback, raw_output). parsed_output is None if validations fail.
        """
        last_exc = None
        raw_out = ""
        for attempt in range(max_retries + 1):
            t0 = time.perf_counter()
            req = AIRequest(
                prompt=prompt,
                response_format="json",
                json_schema=schema_model.schema(),
                intent_type=intent_type
            )
            res = self._llm.execute(req, retrieval_coverage_score=retrieval_coverage_score, retrieval_chunk_count=retrieval_chunk_count)
            raw_out = res.raw_output
            
            logger.debug("LLM attempt %d raw response (%.0fms): %s",
                         attempt + 1, (time.perf_counter() - t0) * 1000, res.raw_output[:120])
                         
            if res.success and res.parsed_output:
                try:
                    parsed = schema_model(**res.parsed_output)
                    
                    # Phase 13 Item 3: Low-Quality Output Detection
                    if hasattr(parsed, "diagnosis") and len(parsed.diagnosis.strip()) < 10:
                        raise ValueError("LowQualityOutput: diagnosis is anomalously short.")
                    
                    return parsed, False, raw_out
                except Exception as exc:
                    last_exc = exc
                    logger.warning("LLM attempt %d/%d validation failed: %s", attempt + 1, max_retries + 1, exc)
                    if attempt < max_retries:
                        prompt += "\n\nSYSTEM WARNING: Your previous output was malformed or generated insufficient content. Ensure you provide a comprehensive and properly formatted JSON response matching the schema exactly."
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
    confidence, docs, user_question, schema_text, is_fault_intent
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

    if is_fault_intent:
        rules = """OUTPUT RULES:
  - Return ONLY valid JSON matching this exact schema (no prose outside JSON):
  - 'diagnosis' must be a SINGLE high-impact string (max 3 lines). DO NOT use filler words or conversational phrasing ("it appears", "it may indicate").
  - Map deterministic STATISTICS directly into the nested 'metrics' JSON object. Do not hallucinate values.
  - 'primary_action' must be ONE concrete, technically targeted action. Do NOT give generic "inspect hardware" advice.
  - Do NOT invent PLC tag names not present in documentation.
  - Do NOT invent document sections."""
    else:
        rules = """OUTPUT RULES:
  - Return ONLY valid JSON matching this exact schema (no prose outside JSON):
  - The user has asked a general question or asked for document summarization. 
  - Provide a comprehensive technical answer in 'summary'.
  - Extract detailed key points into 'key_points'.
  - Do NOT invent PLC tag names not present in documentation.
  - Do NOT invent document sections."""

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

{rules}

{schema_text}
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
