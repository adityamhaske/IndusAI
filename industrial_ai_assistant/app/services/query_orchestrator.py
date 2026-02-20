"""
QueryOrchestrator — 9-step pipeline from question to validated response.

Pipeline:
  1. require_ready()           — fail-fast if project not indexed / stale
  2. classify(query)           — multi-label QueryIntent
  3. structured_lookup()       — exact hits from StructuredIndex
  4. hybrid_search()           — BM25+vector from SemanticIndex
  5. merge contexts
  6. PromptBuilder.build()     — token-capped prompt
  7. LLM.generate()            — Mistral 7B via Ollama
  8. Parse/validate JSON        — ProjectQueryResponse schema
  9. HallucinationGuard()      — reject invented PLC tags

Hallucination guard patterns:
  - UPPER_CASE tokens (e.g. MOTOR_SPEED)
  - Program:Tag scoped (e.g. MainProgram:MotorSpeed)
  - Dotted member (e.g. Drive.Speed)
  - CamelCase (e.g. MotorSpeed)
  Fuzzy threshold: 0.85 (SequenceMatcher ratio)
"""
from __future__ import annotations

import json
import logging
import re
import time
from difflib import SequenceMatcher

from app.core.project_exceptions import HallucinatedTagError
from app.indexes.semantic_index import get_semantic_index
from app.indexes.structured_index import get_structured_index
from app.models.project_models import (
    ProjectQueryRequest,
    ProjectQueryResponse,
    ScoredChunk,
    StructuredHit,
    QueryType,
)
from app.services import query_classifier
from app.services.project_context_manager import get_project_context_manager
from app.services.prompt_builder import PROMPT_VERSION, build as build_prompt

logger = logging.getLogger(__name__)

# Tag candidate extraction patterns
_TAG_PATTERNS = [
    re.compile(r'\b[A-Z][A-Z0-9_]{2,}\b'),         # UPPER_SNAKE_CASE
    re.compile(r'\b[A-Z][a-z]+(?:[A-Z][a-zA-Z0-9]+)+\b'),  # CamelCase
    re.compile(r'\b\w+:\w[\w.]*\b'),                # Program:Tag scoped
    re.compile(r'\b[A-Za-z]\w+\.[A-Za-z]\w+\b'),   # Dotted.Member
]

# Minimum character length for a token to be inspected
_MIN_TAG_LEN = 4
_FUZZY_THRESHOLD = 0.85


class QueryOrchestrator:
    """Executes the full 9-step query pipeline."""

    def query(self, request: ProjectQueryRequest) -> ProjectQueryResponse:
        t_start = time.perf_counter()
        project_id = request.project_id

        # ── Step 1: Fail-fast ──────────────────────────────────────────────────
        ctx = get_project_context_manager()
        ctx.require_ready(project_id)

        # ── Step 2: Classify ──────────────────────────────────────────────────
        intent = query_classifier.classify(request.question)
        logger.info("[%s] Query intent: %s", project_id, intent.labels)

        # ── Step 3: Structured lookup ─────────────────────────────────────────
        si = get_structured_index(project_id)
        structured_hits = _structured_lookup(request.question, intent, si)

        # ── Step 4: Semantic retrieval (hybrid) ───────────────────────────────
        sem = get_semantic_index()
        semantic_hits: list[ScoredChunk] = []
        if intent.semantic_required:
            try:
                semantic_hits = sem.hybrid_search(
                    query=request.question,
                    project_id=project_id,
                    top_k=request.top_k,
                )
            except Exception as exc:
                logger.warning("Semantic retrieval failed: %s", exc)

        # ── Step 5: Merge contexts (already ordered: structured first) ─────────
        # (both lists are passed separately to PromptBuilder)

        # ── Step 6: Build prompt ──────────────────────────────────────────────
        prompt = build_prompt(
            question=request.question,
            intent_labels=[l.value for l in intent.labels],
            structured_hits=structured_hits,
            semantic_chunks=semantic_hits,
        )

        # ── Step 7: LLM call ──────────────────────────────────────────────────
        t_llm = time.perf_counter()
        raw_response = _call_llm(prompt)
        llm_ms = (time.perf_counter() - t_llm) * 1000

        # ── Step 8: Parse + validate schema ──────────────────────────────────
        answer, confidence, reasoning = _parse_llm_output(raw_response)

        # ── Step 9: Hallucination guard ───────────────────────────────────────
        known_tags = si.all_tag_names_lower()
        hallucinated = _detect_hallucinated_tags(answer, known_tags)

        if hallucinated:
            logger.warning(
                "[%s] Hallucinated tags detected: %s — stripping from answer.",
                project_id, hallucinated,
            )
            # Strip hallucinated tokens from answer (replace with [REDACTED])
            for tag in hallucinated:
                # case-insensitive replacement
                answer = re.sub(re.escape(tag), "[REDACTED]", answer, flags=re.IGNORECASE)

        total_ms = (time.perf_counter() - t_start) * 1000
        warnings: list[str] = []
        if hallucinated:
            warnings.append(
                f"LLM invented {len(hallucinated)} PLC tag(s) — they have been redacted."
            )

        return ProjectQueryResponse(
            question=request.question,
            project_id=project_id,
            query_intent=intent,
            structured_hits=structured_hits,
            semantic_sources=[sc.chunk.source_file for sc in semantic_hits],
            answer=answer,
            confidence=confidence,
            hallucinated_tags_removed=hallucinated,
            prompt_version=PROMPT_VERSION,
            llm_latency_ms=round(llm_ms, 1),
            total_latency_ms=round(total_ms, 1),
            warnings=warnings,
        )


# ── Structured lookup ──────────────────────────────────────────────────────────

def _structured_lookup(query: str, intent, si) -> list[StructuredHit]:
    hits: list[StructuredHit] = []
    q_lower = query.lower()

    if QueryType.TAG_LOOKUP in intent.labels:
        # Extract candidate tag names from query (word-level)
        candidates = re.findall(r'\b[A-Za-z_][A-Za-z0-9_]{2,}\b', query)
        for cand in candidates:
            tag = si.get_tag(cand)
            if tag:
                hits.append(StructuredHit(hit_type="tag", data=tag.model_dump()))
            # Also prefix search for shorter tokens
            prefix_hits = si.search_tags_prefix(cand, limit=3)
            for t in prefix_hits:
                if not any(h.data.get("name") == t.name for h in hits):
                    hits.append(StructuredHit(hit_type="tag", data=t.model_dump()))

    if QueryType.IO_LOOKUP in intent.labels:
        # Extract slot/rack patterns like "1:2" or "RIO 3"
        slot_matches = re.findall(r'\d+[:/]\d+', query) + re.findall(r'slot\s+(\d+)', q_lower)
        for slot in slot_matches:
            io = si.get_io(slot)
            if io:
                hits.append(StructuredHit(hit_type="io", data=io.model_dump()))
        # Keyword search on description
        kw_hits = si.search_io_description(query[:30], limit=3)
        for io in kw_hits:
            if not any(h.data.get("slot") == io.slot for h in hits):
                hits.append(StructuredHit(hit_type="io", data=io.model_dump()))

    if QueryType.ROUTINE_FLOW in intent.labels:
        candidates = re.findall(r'\b[A-Za-z_][A-Za-z0-9_]{2,}\b', query)
        for cand in candidates:
            rtn = si.get_routine(cand)
            if rtn:
                hits.append(StructuredHit(hit_type="routine", data=rtn.model_dump()))

    return hits[:20]   # cap hits per response


# ── LLM call ─────────────────────────────────────────────────────────────────

def _call_llm(prompt: str) -> str:
    """Call OllamaLLM.generate(). Raises LLMConnectionError if unreachable."""
    from app.llm.ollama_llm import OllamaLLM
    from app.config.settings import settings
    llm = OllamaLLM(base_url=settings.OLLAMA_BASE_URL, model=settings.OLLAMA_MODEL)
    return llm.generate(prompt)


def _parse_llm_output(raw: str) -> tuple[str, str, str]:
    """Extract answer/confidence/reasoning from JSON or plain text."""
    # Try JSON parse
    try:
        # Find JSON block (may be wrapped in markdown code fences)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            answer = data.get("answer", raw)
            confidence = str(data.get("confidence", "LOW")).upper()
            if confidence not in ("LOW", "MEDIUM", "HIGH"):
                confidence = "LOW"
            reasoning = data.get("reasoning", "")
            return answer, confidence, reasoning
    except Exception:
        pass

    # Fallback: use full text as answer
    return raw, "LOW", ""


# ── Hallucination guard ────────────────────────────────────────────────────────

def _detect_hallucinated_tags(text: str, known_tags_lower: frozenset[str]) -> list[str]:
    """
    Extract PLC tag candidates from LLM output.
    Compare against known tag names (case-insensitive).
    Use fuzzy match at 0.85 threshold before declaring hallucination.
    Returns list of hallucinated tag strings.
    """
    if not known_tags_lower:
        return []   # No tags indexed → can't validate, don't flag anything

    candidates: set[str] = set()
    for pattern in _TAG_PATTERNS:
        for match in pattern.finditer(text):
            token = match.group()
            if len(token) >= _MIN_TAG_LEN:
                candidates.add(token)

    hallucinated: list[str] = []
    for cand in candidates:
        cand_lower = cand.lower()
        if cand_lower in known_tags_lower:
            continue   # exact match — OK
        if _fuzzy_match(cand_lower, known_tags_lower):
            continue   # close enough — OK
        hallucinated.append(cand)

    return hallucinated


def _fuzzy_match(candidate: str, known: frozenset[str], threshold: float = _FUZZY_THRESHOLD) -> bool:
    """Return True if any known tag is within fuzzy threshold of candidate."""
    for known_tag in known:
        ratio = SequenceMatcher(None, candidate, known_tag).ratio()
        if ratio >= threshold:
            return True
    return False


# ── Singleton ─────────────────────────────────────────────────────────────────

_orchestrator: QueryOrchestrator | None = None


def get_query_orchestrator() -> QueryOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = QueryOrchestrator()
    return _orchestrator
