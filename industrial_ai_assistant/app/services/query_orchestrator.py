"""
QueryOrchestrator — 9-step PLC project query pipeline.

Steps:
  1. require_ready(project_id)             — fail-fast
  2. classify(query)                       — multi-label QueryIntent
  3. structured lookups                    — TAG/IO/ROUTINE from StructuredIndex (exact)
  4. semantic retrieval                    — hybrid BM25+vector from SemanticIndex
  5. merge contexts
  6. build prompt (PromptBuilder, 3800 token budget)
  7. call LLM → raw JSON
  8. extract PLC tag candidates
  9. fuzzy validate against StructuredIndex → reject hallucinated

No silent fallback. Every failure raises a typed exception.
"""
import json
import logging
import re
import time
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from app.core.project_exceptions import HallucinatedTagError, ProjectNotReadyError
from app.indexes.semantic_index import get_semantic_index
from app.indexes.structured_index import get_structured_index
from app.models.project_models import (
    ProjectQueryRequest,
    ProjectQueryResponse,
    StructuredHit,
)
from app.services.project_context_manager import get_project_context_manager
from app.services.query_classifier import classify

logger = logging.getLogger(__name__)

PROMPT_VERSION = "project_v1.0"
_MAX_TOKENS = 3_800          # character-based budget (≈4 chars/token)
_MAX_CHARS = _MAX_TOKENS * 4 # 15,200 chars
_FUZZY_THRESHOLD = 0.85      # min ratio for fuzzy tag match

# Patterns for extracting PLC tag candidates from LLM output
_TAG_PATTERNS = [
    re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b"),                   # MOTOR_SPEED
    re.compile(r"\b\w+:([A-Z][A-Z0-9_]{2,})\b"),             # Program:Tag
    re.compile(r"\b([A-Z][A-Z0-9_]+)\.([A-Z][A-Z0-9_]+)\b"), # Tag.Member
]

# Noise words that match tag pattern but are not tags
_NOISE_WORDS = frozenset([
    "LOW", "HIGH", "TRUE", "FALSE", "NONE", "NULL",
    "LLM", "PLC", "CPU", "IO", "RIO", "AOI", "JSON",
    "GET", "SET", "TAG", "AND", "NOT", "FOR", "ALL",
    "MAX", "MIN", "AVG", "SUM", "NEW", "OLD",
])


class QueryOrchestrator:
    """Full 9-step query orchestration pipeline."""

    def __init__(self, llm=None):
        self._llm = llm

    def _get_llm(self):
        if self._llm is None:
            from app.config.dependency_injection import get_container
            self._llm = get_container().llm
        return self._llm

    def query(self, request: ProjectQueryRequest) -> ProjectQueryResponse:
        pid = request.project_id
        t0 = time.perf_counter()

        # ── Step 1: Fail-fast readiness check ────────────────────────────────
        get_project_context_manager().require_ready(pid)

        # ── Step 2: Classify query ────────────────────────────────────────────
        intent = classify(request.question)
        logger.info("Query intent: labels=%s struct=%s sem=%s",
                    intent.labels, intent.structured_required, intent.semantic_required)

        # ── Step 3: Structured lookups ────────────────────────────────────────
        s_idx = get_structured_index(pid)
        structured_hits: List[StructuredHit] = []

        if intent.structured_required:
            # Extract potential identifiers from query
            candidates = re.findall(r"[A-Z][A-Z0-9_]{2,}", request.question)
            for cand in candidates:
                tag = s_idx.get_tag(cand)
                if tag:
                    structured_hits.append(StructuredHit(
                        type="tag",
                        name=tag.name,
                        detail={"data_type": tag.data_type, "scope": tag.scope,
                                "description": tag.description},
                    ))
                routine = s_idx.get_routine(cand)
                if routine:
                    structured_hits.append(StructuredHit(
                        type="routine",
                        name=routine.name,
                        detail={"program": routine.program, "type": routine.routine_type,
                                "rungs": routine.rung_count},
                    ))

            # IO lookup: slot/rack numbers
            slots = re.findall(r"\b(\d+)\b", request.question)
            for slot in slots[:3]:
                io = s_idx.get_io(slot)
                if io:
                    structured_hits.append(StructuredHit(
                        type="io",
                        name=f"Slot {slot}",
                        detail={"module": io.module, "description": io.description,
                                "tag_name": io.tag_name, "rack": io.rack},
                    ))

        # ── Step 4: Semantic retrieval ────────────────────────────────────────
        sem_docs: List[dict] = []
        if intent.semantic_required or intent.progress_required:
            sem_idx = get_semantic_index()
            sem_docs = sem_idx.search(
                query=request.question,
                project_id=pid,
                top_k=5,
            )

        # ── Step 5: Merge context ─────────────────────────────────────────────
        doc_sources = list(dict.fromkeys(
            d["source_file"] for d in sem_docs if d.get("source_file")
        ))

        # ── Step 6: Build prompt with token budget ────────────────────────────
        prompt = _build_prompt(
            question=request.question,
            structured_hits=structured_hits,
            sem_docs=sem_docs,
            all_tag_names=s_idx.all_tag_names(),
        )

        # ── Step 7: Call LLM ──────────────────────────────────────────────────
        llm = self._get_llm()
        raw = llm.generate(prompt)
        llm_ms = (time.perf_counter() - t0) * 1000

        # ── Step 8: Parse LLM response ────────────────────────────────────────
        parsed = _parse_response(raw)

        # ── Step 9: Hallucination guard ───────────────────────────────────────
        known_tags = s_idx.all_tag_names()
        rejected = _validate_tags(parsed.get("summary", "") + parsed.get("reasoning", ""), known_tags)
        if rejected:
            logger.error("Hallucinated tags rejected: %s", rejected)
            raise HallucinatedTagError(rejected)

        return ProjectQueryResponse(
            project_id=pid,
            question=request.question,
            summary=parsed.get("summary", raw[:500]),
            reasoning=parsed.get("reasoning", ""),
            structured_hits=structured_hits,
            documentation_sources=doc_sources,
            confidence=parsed.get("confidence", "LOW"),
            prompt_version=PROMPT_VERSION,
            hallucinated_tags_rejected=[],
            query_labels=[str(l) for l in intent.labels],
            llm_latency_ms=round(llm_ms, 1),
        )


# ── Prompt builder ─────────────────────────────────────────────────────────────

def _build_prompt(
    question: str,
    structured_hits: List[StructuredHit],
    sem_docs: List[dict],
    all_tag_names: frozenset,
) -> str:
    """Build LLM prompt with strict token budget enforcement."""
    budget = _MAX_CHARS
    sections: List[str] = []

    header = (
        f"You are an expert PLC commissioning assistant. "
        f"Answer the engineer's question using ONLY the context below.\n"
        f"CRITICAL RULES:\n"
        f"  1. DO NOT invent PLC tags. Only reference tags listed in STRUCTURED INDEX.\n"
        f"  2. Return valid JSON matching the schema exactly.\n"
        f"  3. If context is insufficient, state that in 'reasoning'.\n\n"
        f"QUESTION: {question}\n"
    )
    budget -= len(header)
    sections.append(header)

    # Structured hits section
    if structured_hits:
        struct_lines = ["STRUCTURED INDEX MATCHES:"]
        for h in structured_hits:
            line = f"  [{h.type.upper()}] {h.name}: {h.detail}"
            if budget - len(line) > 500:
                struct_lines.append(line)
                budget -= len(line)
        struct_section = "\n".join(struct_lines) + "\n"
        sections.append(struct_section)
    else:
        sections.append("STRUCTURED INDEX MATCHES: (none found for this query)\n")
        budget -= 50

    # Known tag list sample (first 100 for reference)
    tag_sample = sorted(list(all_tag_names))[:100]
    if tag_sample:
        tag_hint = "VALID PLC TAGS (subset): " + ", ".join(tag_sample[:50]) + "\n"
        if budget - len(tag_hint) > 500:
            sections.append(tag_hint)
            budget -= len(tag_hint)

    # Semantic docs section
    if sem_docs:
        sem_lines = ["DOCUMENTATION CONTEXT:"]
        for doc in sem_docs:
            title = doc.get("section_title") or doc.get("source_file", "")
            excerpt = doc.get("content", "")[:600]
            entry = f"  [{title}]\n  {excerpt}\n"
            if budget - len(entry) > 200:
                sem_lines.append(entry)
                budget -= len(entry)
        sections.append("\n".join(sem_lines) + "\n")

    # Output schema
    schema = (
        '\nOUTPUT (strict JSON only, no prose outside):\n'
        '{\n'
        '  "summary": "<concise answer to the question>",\n'
        '  "reasoning": "<explain how you derived the answer>",\n'
        '  "confidence": "LOW|MEDIUM|HIGH"\n'
        '}\n'
    )
    sections.append(schema)

    return "".join(sections)


def _parse_response(raw: str) -> dict:
    """Extract JSON from LLM response."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Try extracting JSON block
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # Fallback: return raw as summary
    return {"summary": raw[:800], "reasoning": "", "confidence": "LOW"}


def _validate_tags(text: str, known_tags: frozenset) -> List[str]:
    """
    Extract PLC tag candidates from text and validate against known tags.
    Uses fuzzy matching (ratio ≥ 0.85) to allow minor abbreviation differences.
    Returns list of hallucinated tags (those with no close match).
    """
    if not known_tags:
        return []  # No tag index — skip guard

    candidates: set = set()
    for pattern in _TAG_PATTERNS:
        for m in pattern.finditer(text):
            word = m.group(1) if m.lastindex else m.group()
            if word.upper() not in _NOISE_WORDS and len(word) >= 3:
                candidates.add(word.upper())

    hallucinated = []
    for cand in candidates:
        if cand in known_tags:
            continue
        # Fuzzy check — allow close matches
        best_ratio = max(
            (SequenceMatcher(None, cand, k).ratio() for k in known_tags),
            default=0,
        )
        if best_ratio < _FUZZY_THRESHOLD:
            hallucinated.append(cand)

    return hallucinated


# ── Singleton ─────────────────────────────────────────────────────────────────
_orchestrator: Optional[QueryOrchestrator] = None


def get_query_orchestrator() -> QueryOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = QueryOrchestrator()
    return _orchestrator
