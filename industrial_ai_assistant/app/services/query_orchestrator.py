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
    SemanticChunk,
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

        # ── Scope Resolution ──────────────────────────────────────────────────
        si = get_structured_index(project_id)
        sem = get_semantic_index()

        scope_mode = request.scope_mode
        effective_scope: set[str] | None = None
        context_scope_meta = {
            "mode": scope_mode,
            "files_selected": request.selected_files + request.selected_folders,
            "files_used": [],
            "truncated": False,
            "total_candidates": 0,
            "used_chunks": 0
        }

        if scope_mode in ("STRICT", "PREFER") and context_scope_meta["files_selected"]:
            all_files = si.all_source_files()
            try:
                all_files.update(sem.all_source_files(project_id))
            except Exception:
                pass
            
            # Resolve exact files
            resolved = set(request.selected_files)
            for folder in request.selected_folders:
                prefix = folder if folder.endswith("/") else folder + "/"
                for f in all_files:
                    if f == folder or f.startswith(prefix):
                        resolved.add(f)
            effective_scope = resolved
            context_scope_meta["files_used"] = list(effective_scope)

            # STRICT mode empty-scope circuit breaker
            if scope_mode == "STRICT" and not effective_scope:
                return ProjectQueryResponse(
                    question=request.question,
                    project_id=project_id,
                    query_intent=intent,
                    answer=json.dumps({
                        "summary": "NO_RESULTS_IN_SCOPE: No valid indexed files matched your STRICT selection.",
                        "root_causes": [],
                        "recommended_actions": ["Select different files or switch to GLOBAL mode."],
                        "supporting_evidence": [],
                        "limitations": ["Search was blocked due to an empty context scope."],
                        "confidence": "LOW",
                    }),
                    confidence="LOW",
                    warnings=["STRICT mode active but no matching files found in index."],
                    context_scope=context_scope_meta,
                    prompt_version=PROMPT_VERSION,
                )

        # ── Fast-Path: File Explanation ─────────────────────────────────────────
        is_fast_path = False
        semantic_hits: list[ScoredChunk] = []
        structured_hits: list[StructuredHit] = []
        
        if scope_mode == "STRICT" and effective_scope and len(effective_scope) == 1:
            q_lower = request.question.lower()
            if any(kw in q_lower for kw in ["explain", "describe", "summariz", "what is"]):
                target_file = list(effective_scope)[0]
                import os
                if os.path.exists(target_file):
                    if (os.path.getsize(target_file) / 4) < 8000:
                        try:
                            with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                                content = f.read()
                            chunk = SemanticChunk(
                                chunk_id="fast_path",
                                content=content,
                                source_file=target_file,
                                section_title="FULL FILE CONTENT"
                            )
                            semantic_hits = [ScoredChunk(chunk=chunk, score=1.0, retrieval_method="exact_file")]
                            is_fast_path = True
                            context_scope_meta["total_candidates"] = 1
                            context_scope_meta["used_chunks"] = 1
                            logger.info("[%s] Triggered File Explanation Fast-Path for %s", project_id, target_file)
                        except Exception as e:
                            logger.warning("[%s] Fast-path failed to read file %s: %s", project_id, target_file, e)

        if not is_fast_path:
            # ── Step 3: Structured lookup ─────────────────────────────────────────
            raw_structured_hits = _structured_lookup(request.question, intent, si)
            for hit in raw_structured_hits:
                source = hit.data.get("source_file", "")
                if scope_mode == "STRICT" and effective_scope is not None:
                    if source in effective_scope:
                        structured_hits.append(hit)
                else:
                    structured_hits.append(hit)

            # ── Step 4: Semantic retrieval (hybrid) ───────────────────────────────
            if intent.semantic_required:
                try:
                    search_scope = effective_scope if scope_mode == "STRICT" else None
                    semantic_hits = sem.hybrid_search(
                        query=request.question,
                        project_id=project_id,
                        top_k=request.top_k * (3 if scope_mode == "PREFER" else 1),
                        scope_files=search_scope,
                    )
                except Exception as exc:
                    logger.warning("Semantic retrieval failed: %s", exc)

            context_scope_meta["total_candidates"] = len(semantic_hits)

            # PREFER mode boosting
            if scope_mode == "PREFER" and effective_scope:
                for hit in semantic_hits:
                    if hit.chunk.source_file in effective_scope:
                        hit.score *= 1.5
                semantic_hits.sort(key=lambda x: x.score, reverse=True)
                semantic_hits = semantic_hits[:request.top_k]

            context_scope_meta["used_chunks"] = len(semantic_hits)

        # ── Step 5: Merge contexts ───────────────────────────────────────────
        # (Lists are passed separately to PromptBuilder)

        # ── Step 6: Build prompt ──────────────────────────────────────────────
        prompt, is_truncated, used_chunks = build_prompt(
            question=request.question,
            intent_labels=[l.value for l in intent.labels],
            structured_hits=structured_hits,
            semantic_chunks=semantic_hits,
        )
        context_scope_meta["truncated"] = is_truncated
        context_scope_meta["used_chunks"] = used_chunks

        # ── Step 7: LLM call ──────────────────────────────────────────────────
        t_llm = time.perf_counter()
        raw_response = _call_llm(prompt)
        llm_ms = (time.perf_counter() - t_llm) * 1000

        # ── Step 8: Parse + validate schema ──────────────────────────────────
        parsed = _parse_llm_output(raw_response)
        confidence = parsed["confidence"]

        # ── Step 9: Hallucination guard (runs on summary + evidence) ─────────
        known_tags = si.all_tag_names_lower()
        # Combine text fields that may contain tag references
        guard_text = parsed["summary"] + " " + " ".join(parsed["supporting_evidence"])
        hallucinated = _detect_hallucinated_tags(guard_text, known_tags)

        if hallucinated:
            logger.warning(
                "[%s] Hallucinated tags detected: %s — stripping from answer.",
                project_id, hallucinated,
            )
            for tag in hallucinated:
                parsed["summary"] = re.sub(
                    re.escape(tag), "[REDACTED]", parsed["summary"], flags=re.IGNORECASE
                )

        total_ms = (time.perf_counter() - t_start) * 1000
        warnings: list[str] = []
        if hallucinated:
            warnings.append(
                f"LLM invented {len(hallucinated)} PLC tag(s) — they have been redacted."
            )
        if not parsed.get("_raw_valid"):
            warnings.append("LLM response was not valid JSON — used plain text fallback.")

        # Store full structured response as JSON string in answer field
        answer_json = json.dumps({
            "summary":             parsed["summary"],
            "root_causes":         parsed["root_causes"],
            "recommended_actions": parsed["recommended_actions"],
            "supporting_evidence": parsed["supporting_evidence"],
            "limitations":         parsed["limitations"],
        })

        return ProjectQueryResponse(
            question=request.question,
            project_id=project_id,
            query_intent=intent,
            structured_hits=structured_hits,
            semantic_sources=[sc.chunk.source_file for sc in semantic_hits],
            answer=answer_json,
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


def _parse_llm_output(raw: str) -> dict:
    """
    Parse LLM JSON response according to the v2 schema:
    {
      "summary": str,
      "root_causes": list[str],
      "recommended_actions": list[str],
      "supporting_evidence": list[str],
      "limitations": list[str],
      "confidence": LOW|MEDIUM|HIGH
    }

    Handles:
    - Clean JSON
    - JSON wrapped in markdown code fences
    - Partial/malformed JSON (best-effort extraction)
    - Plain text fallback
    """
    _REQUIRED_KEYS = {"summary", "root_causes", "recommended_actions",
                      "supporting_evidence", "limitations", "confidence"}

    try:
        # Strip markdown code fences if present
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

        # Find outermost JSON object
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group())
            # Validate + normalise keys
            confidence = str(data.get("confidence", "LOW")).upper()
            if confidence not in ("LOW", "MEDIUM", "HIGH"):
                confidence = "LOW"

            def _to_list(v):
                if isinstance(v, list):
                    return [str(i) for i in v if i]
                if isinstance(v, str) and v:
                    return [v]
                return []

            return {
                "summary":              str(data.get("summary", raw[:200])),
                "root_causes":          _to_list(data.get("root_causes", [])),
                "recommended_actions":  _to_list(data.get("recommended_actions", [])),
                "supporting_evidence":  _to_list(data.get("supporting_evidence", [])),
                "limitations":          _to_list(data.get("limitations", [])),
                "confidence":           confidence,
                "_raw_valid":           True,
            }
    except Exception:
        pass

    # Fallback: plain text response — wrap it in the schema
    return {
        "summary":             raw[:500] if raw else "No response from LLM.",
        "root_causes":         [],
        "recommended_actions": [],
        "supporting_evidence": [],
        "limitations":         ["LLM response was not in expected JSON format."],
        "confidence":          "LOW",
        "_raw_valid":          False,
    }



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
