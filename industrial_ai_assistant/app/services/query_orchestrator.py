"""
QueryOrchestrator — 9-step pipeline for project knowledge queries.

Steps:
  1. Validate project is loaded (ProjectContextManager.require_ready)
  2. Classify query (QueryClassifier)
  3. Structured lookup — exact tag / IO / routine matches
  4. Semantic search — top_k doc chunks filtered to project_id
  5. Merge contexts (structured first, semantic second)
  6. Build deterministic prompt with explicit anti-hallucination instruction
  7. Call OllamaLLM.generate()
  8. Hallucination guard — extract tag tokens, verify vs StructuredIndex
  9. Return ProjectQueryResponse

Strict rules:
  - No silent fallback: raise TagHallucinationError on invented tags
  - No cross-project data: SemanticIndex filters by project_id
  - LLM never receives raw CSV or raw L5X
"""
from __future__ import annotations

import logging
import re
import time
from typing import List

from app.core.project_exceptions import TagHallucinationError
from app.indexes.semantic_index import SemanticIndex
from app.indexes.structured_index import ProjectStructuredIndex
from app.models.project_models import (
    ProjectQueryRequest,
    ProjectQueryResponse,
    StructuredMatch,
)
from app.services.project_context_manager import ProjectContextManager
from app.services.query_classifier import QueryType, classify, extract_tag_tokens

logger = logging.getLogger(__name__)

_MAX_STRUCT_MATCHES = 5
_MAX_SEMANTIC_CHUNKS = 5
_MAX_CONTEXT_CHARS = 3000


class QueryOrchestrator:
    """Stateless orchestrator — all state lives in injected services."""

    def __init__(
        self,
        context_manager: ProjectContextManager,
        struct_idx: ProjectStructuredIndex,
        semantic_index: SemanticIndex,
        llm,
    ):
        self._ctx = context_manager
        self._struct = struct_idx
        self._sem = semantic_index
        self._llm = llm

    def query(self, request: ProjectQueryRequest) -> ProjectQueryResponse:
        project_id = request.project_id
        q = request.query.strip()

        # ── Step 1: Readiness gate ────────────────────────────────────────────
        self._ctx.require_ready(project_id)

        # ── Step 2: Classify ──────────────────────────────────────────────────
        q_type = classify(q)
        logger.info("Query classified as %s (project=%s)", q_type, project_id)

        # ── Step 3: Structured lookup ────────────────────────────────────────
        structured_matches = self._structured_lookup(q, q_type)

        # ── Step 4: Semantic search ───────────────────────────────────────────
        sem_chunks = self._sem.search(project_id, q, top_k=request.top_k_semantic)
        sem_sources = list({c.metadata.source_file for c in sem_chunks})

        # ── Step 5: Build context ─────────────────────────────────────────────
        struct_block = _render_structured_block(structured_matches)
        sem_block = _render_semantic_block(sem_chunks)

        # ── Step 6: Build prompt ──────────────────────────────────────────────
        all_tag_names = self._struct.all_tag_names()
        prompt = _build_prompt(q, q_type, struct_block, sem_block, all_tag_names)

        # ── Step 7: LLM call ──────────────────────────────────────────────────
        t0 = time.perf_counter()
        raw_answer = self._llm.generate(prompt)
        llm_ms = (time.perf_counter() - t0) * 1000
        logger.debug("LLM responded in %.0fms", llm_ms)

        # ── Step 8: Hallucination guard ───────────────────────────────────────
        referenced_tags = self._hallucination_guard(raw_answer)

        # ── Step 9: Assemble response ─────────────────────────────────────────
        confidence = _estimate_confidence(structured_matches, sem_chunks)

        return ProjectQueryResponse(
            project_id=project_id,
            query=q,
            query_type=q_type.value,
            structured_matches=structured_matches,
            semantic_sources=sem_sources,
            answer=raw_answer,
            tags_referenced=referenced_tags,
            confidence=confidence,
            llm_latency_ms=round(llm_ms, 1),
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _structured_lookup(self, query: str, q_type: QueryType) -> List[StructuredMatch]:
        matches: List[StructuredMatch] = []

        if q_type == QueryType.TAG_LOOKUP:
            tokens = extract_tag_tokens(query)
            for token in tokens[:_MAX_STRUCT_MATCHES]:
                record = self._struct.get_tag(token)
                if record:
                    matches.append(StructuredMatch(
                        match_type="tag",
                        data=record.model_dump(),
                    ))
            # Also do a partial search if no exact matches
            if not matches and tokens:
                partial = self._struct.search_tags(tokens[0], limit=3)
                matches = [StructuredMatch(match_type="tag", data=t.model_dump()) for t in partial]

        elif q_type == QueryType.IO_LOOKUP:
            # Extract slot-like tokens: digits with colons e.g. "1:2:3"
            slots = re.findall(r"\d+:\d+(?::\d+)*", query)
            for slot in slots[:_MAX_STRUCT_MATCHES]:
                record = self._struct.get_io(slot)
                if record:
                    matches.append(StructuredMatch(match_type="io", data=record.model_dump()))
            # Also look for tag names in IO context
            if not matches:
                tokens = extract_tag_tokens(query)
                for t in tokens[:3]:
                    try:
                        rec = self._struct.io.get_by_tag(t)
                        matches.append(StructuredMatch(match_type="io", data=rec.model_dump()))
                    except KeyError:
                        pass

        elif q_type == QueryType.ROUTINE_FLOW:
            # Try to find routine names in query
            # Routines are typically CamelCase or UPPERCASE words
            for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_]{2,}\b", query):
                record = self._struct.get_routine(token)
                if record:
                    matches.append(StructuredMatch(match_type="routine", data=record.model_dump()))
                    if len(matches) >= _MAX_STRUCT_MATCHES:
                        break

        return matches

    def _hallucination_guard(self, llm_output: str) -> List[str]:
        """
        Extract all PLC-tag-like tokens from LLM output.
        Verify each exists in the StructuredIndex.
        Raise TagHallucinationError if any invented tags found.
        Returns list of validated referenced tags.
        """
        tokens = extract_tag_tokens(llm_output)
        invented = [t for t in tokens if not self._struct.has_tag(t)]

        if invented:
            logger.error(
                "Hallucination guard triggered: invented tags=%s", invented
            )
            raise TagHallucinationError(invented_tags=invented)

        return tokens


# ── Prompt building ───────────────────────────────────────────────────────────

def _build_prompt(
    query: str,
    q_type: QueryType,
    struct_block: str,
    sem_block: str,
    all_tag_names: List[str],
) -> str:
    tag_list_hint = ""
    if all_tag_names:
        sample = ", ".join(all_tag_names[:30])
        tag_list_hint = f"\nKnown PLC tags (sample of {len(all_tag_names)}): {sample}...\n"

    return f"""You are a production PLC commissioning assistant.

STRICT RULES:
1. You MUST NOT invent PLC tags. Only reference tags explicitly listed in the STRUCTURED INDEX below.
2. If a tag is not in the structured index, state that it was not found in the project.
3. Answer using only the context provided. Do not fabricate field values.
4. Be precise and concise. This is an industrial engineering context.
{tag_list_hint}
QUERY TYPE: {q_type.value}
QUERY: {query}

STRUCTURED INDEX MATCHES:
{struct_block or "(no exact structured match found)"}

DOCUMENTATION CONTEXT:
{sem_block or "(no documentation retrieved)"}

Answer the query using the structured matches and documentation context above.
If the answer cannot be determined from the provided context, say so explicitly.
"""


def _render_structured_block(matches: List[StructuredMatch]) -> str:
    if not matches:
        return ""
    lines = []
    for m in matches:
        lines.append(f"[{m.match_type.upper()}]")
        for k, v in m.data.items():
            if v:
                lines.append(f"  {k}: {v}")
    return "\n".join(lines)[:_MAX_CONTEXT_CHARS]


def _render_semantic_block(chunks) -> str:
    if not chunks:
        return ""
    parts = []
    for chunk in chunks:
        title = chunk.metadata.section_title or chunk.metadata.source_file
        parts.append(f"[{title}]\n{chunk.content[:600]}")
    return "\n\n".join(parts)[:_MAX_CONTEXT_CHARS]


def _estimate_confidence(structured_matches, sem_chunks) -> str:
    if structured_matches and sem_chunks:
        return "HIGH"
    if structured_matches or sem_chunks:
        return "MEDIUM"
    return "LOW"
