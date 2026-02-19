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
from app.core.interfaces.llm_interface import LLMInterface
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
    compute_cooccurrence,
    compute_occurrences_in_window,
)

logger = logging.getLogger(__name__)

# Debug prompt logging — set DEBUG_LLM=true in env to log full prompts
_DEBUG_LLM = os.getenv("DEBUG_LLM", "false").lower() in ("1", "true", "yes")

_LLM_JSON_SCHEMA = """{
  "summary": "<overall explanation of the fault>",
  "likely_causes": ["<cause 1>", "<cause 2>"],
  "diagnostic_steps": ["<step 1>", "<step 2>"],
  "preventive_actions": ["<action 1>"],
  "related_plc_tags": ["<tag_name>"],
  "confidence_explanation": "<why this fault is LOW/MEDIUM/HIGH confidence>"
}"""

# Fallback OUTPUT is removed — failures now raise explicit exceptions.
# Use _FALLBACK_RESPONSE ONLY for test mocking, not in production pipeline.


class FaultAnalysisOrchestrator:
    """Orchestrates deterministic stats + RAG + LLM into a single structured response."""

    def __init__(
        self,
        llm: LLMInterface,
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

        # ── Step 2: Deterministic stats (never done by LLM) ──────────────────
        ts_list = _timestamps_for_code(df, fault_code)
        occ_1h  = compute_occurrences_in_window(ts_list, ref_ts, hours=1)
        occ_24h = compute_occurrences_in_window(ts_list, ref_ts, hours=24)
        co_fault, co_count = compute_cooccurrence(df, ref_ts)
        burst = ds.stats_cache.get("burst_detected", False)
        burst_desc = ds.stats_cache.get("burst_description", "")
        confidence = compute_confidence(occ_1h, burst, occ_24h)

        statistics = {
            "occurrences_last_hour": occ_1h,
            "occurrences_last_24h": occ_24h,
            "top_cooccurring_fault": co_fault,
            "cooccurrence_count": co_count,
            "burst_detected": burst,
            "burst_description": burst_desc,
            "confidence": confidence,
        }

        # ── Step 3: RAG retrieval ─────────────────────────────────────────────
        rag_docs, rag_ms = self._rag.retrieve_for_fault(
            fault_code=fault_code,
            fault_message=message,
            device=device,
            user_question=request.question,
            project_id=request.project_id,
        )

        # ── Step 4: Build prompt ──────────────────────────────────────────────
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
            burst_detected=burst,
            burst_desc=burst_desc,
            confidence=confidence,
            docs=rag_docs,
            user_question=request.question,
        )

        if _DEBUG_LLM:
            logger.debug("[DEBUG_LLM] Full prompt:\n%s", prompt)

        # ── Step 5: LLM call (with retry) ────────────────────────────────────
        t_llm_start = time.perf_counter()
        llm_output, is_fallback = self._call_llm_with_retry(prompt)
        llm_ms = (time.perf_counter() - t_llm_start) * 1000

        # ── Step 6: Validation ────────────────────────────────────────────────
        doc_sources = [d.source_file for d in rag_docs]
        cleaned, hallucinated, val_warnings = self._validator.validate(
            llm_output, doc_sources, known_tags=None
        )

        total_ms = (time.perf_counter() - t_total_start) * 1000

        logger.info(
            "Analysis complete: fault=%s row=%d confidence=%s docs=%d "
            "rag=%.0fms llm=%.0fms total=%.0fms",
            fault_code, request.row_id, confidence, len(rag_docs),
            rag_ms, llm_ms, total_ms,
        )

        return FaultAnalysisV2Response(
            analysis_version="v2.0",
            dataset_hash=ds.dataset_hash,
            row_id=request.row_id,
            fault_code=fault_code,
            device=device,
            timestamp=ref_ts,
            user_question=request.question,
            confidence=confidence,
            statistics=statistics,
            summary=cleaned.summary,
            likely_causes=cleaned.likely_causes,
            diagnostic_steps=cleaned.diagnostic_steps,
            preventive_actions=cleaned.preventive_actions,
            related_plc_tags=cleaned.related_plc_tags,
            confidence_explanation=cleaned.confidence_explanation,
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
        self, prompt: str, max_retries: int = 1
    ) -> tuple[StructuredLLMOutput, bool]:
        """
        Call LLM and parse response. Retry once on parse failure.
        Raises LLMConnectionError / LLMResponseParseError — no silent fallback.
        """
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                t0 = time.perf_counter()
                raw = self._llm.generate(prompt)
                logger.debug("LLM attempt %d raw response (%.0fms): %s",
                             attempt + 1, (time.perf_counter() - t0) * 1000, raw[:120])
                parsed = _parse_llm_json(raw)
                return parsed, False
            except LLMConnectionError:
                raise   # propagate immediately — no retry
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "LLM attempt %d/%d parse failed: %s",
                    attempt + 1, max_retries + 1, exc,
                    exc_info=(attempt == max_retries)   # full trace only on last attempt
                )

        raise LLMResponseParseError(
            f"LLM failed to return valid structured JSON after {max_retries + 1} attempt(s). "
            f"Last error: {last_exc}"
        )


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(
    row_id, fault_code, device, ref_ts, severity, message,
    occ_1h, occ_24h, co_fault, burst_detected, burst_desc,
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

STATISTICS (deterministic — do NOT recompute):
  Occurrences last hour: {occ_1h}
  Occurrences last 24 hours: {occ_24h}
  Top co-occurring fault: {co_fault or "None"}
  Burst detected: {"Yes — " + burst_desc if burst_desc else "No"}
  Confidence level (determined externally): {confidence}{doc_section}{question_section}

OUTPUT RULES:
  - Return ONLY valid JSON matching this exact schema (no prose outside JSON):
  - Do NOT invent PLC tag names not present in documentation
  - Do NOT invent document sections
  - Confidence explanation must reference the statistics above

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
