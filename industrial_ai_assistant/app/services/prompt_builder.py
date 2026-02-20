"""
PromptBuilder — constructs the LLM prompt with strict token budget enforcement.

Design:
  1. Structured hits section (brief, always included if available)
  2. Semantic chunks section (truncated first when budget exceeded)
  3. Hard rules section — always last, always present
  4. Token estimation: len(text) // 4 (conservative 4 chars/token)

MAX_TOKENS = 3500 (Mistral 7B safe context limit for this use case)
PROMPT_VERSION = "project_v1.0"
"""
from __future__ import annotations

from app.models.project_models import ScoredChunk, StructuredHit

PROMPT_VERSION = "project_v1.0"
MAX_TOKENS = 3500
_CHARS_PER_TOKEN = 4    # conservative estimate

_SYSTEM_RULES = """
STRICT RULES — you MUST follow these:
1. You MUST NOT invent PLC tag names. Only reference tags explicitly listed in the STRUCTURED DATA section above.
2. You MUST NOT reference any document not listed in the DOCUMENTATION CONTEXT section.
3. If you are uncertain, state that explicitly — do not guess tag names or IO addresses.
4. Return your answer as a JSON object matching this schema exactly:
{
  "answer": "<detailed technical response>",
  "confidence": "<LOW|MEDIUM|HIGH>",
  "reasoning": "<brief explanation of how you arrived at this answer>"
}
"""


def build(
    question: str,
    intent_labels: list[str],
    structured_hits: list[StructuredHit],
    semantic_chunks: list[ScoredChunk],
) -> str:
    """
    Build the LLM prompt. Enforces token budget.
    Semantic chunks are truncated from the bottom if budget is exceeded.
    """
    sections: list[str] = [
        f"# PLC Engineering Query\n**Prompt version: {PROMPT_VERSION}**\n",
        f"**Question:** {question}\n",
        f"**Query type:** {', '.join(intent_labels)}\n",
    ]

    # ── Structured data section ───────────────────────────────────────────────
    if structured_hits:
        lines = ["## STRUCTURED DATA (exact — do not modify or invent additions)\n"]
        for hit in structured_hits:
            lines.append(f"[{hit.hit_type.upper()}]")
            for k, v in hit.data.items():
                if v:
                    lines.append(f"  {k}: {v}")
            lines.append("")
        sections.append("\n".join(lines))
    else:
        sections.append(
            "## STRUCTURED DATA\n(No exact structured matches found for this query)\n"
        )

    # ── Semantic documentation section ────────────────────────────────────────
    # Enforce token budget: structured + rules are fixed cost; semantic is variable
    fixed_text = "\n".join(sections) + _SYSTEM_RULES
    fixed_tokens = _estimate_tokens(fixed_text)
    budget_for_semantic = MAX_TOKENS - fixed_tokens - 50  # 50 token safety margin

    sem_lines: list[str] = ["## DOCUMENTATION CONTEXT\n"]
    used_tokens = _estimate_tokens("## DOCUMENTATION CONTEXT\n")

    for i, scored in enumerate(semantic_chunks, 1):
        chunk = scored.chunk
        title = chunk.section_title or chunk.source_file
        snippet = (
            f"[Source {i}: {title} | file={chunk.source_file} | "
            f"score={scored.score:.2f} | method={scored.retrieval_method}]\n"
            f"{chunk.content}\n"
        )
        snippet_tokens = _estimate_tokens(snippet)
        if used_tokens + snippet_tokens > budget_for_semantic:
            sem_lines.append(
                f"(Truncated: {len(semantic_chunks) - i + 1} more sources not shown — token budget reached)\n"
            )
            break
        sem_lines.append(snippet)
        used_tokens += snippet_tokens

    if len(sem_lines) == 1:  # only header added
        sem_lines.append("(No documentation context retrieved)\n")
    sections.append("\n".join(sem_lines))

    # ── Rules — always last ───────────────────────────────────────────────────
    sections.append(_SYSTEM_RULES)

    prompt = "\n".join(sections)
    total_tokens = _estimate_tokens(prompt)
    if total_tokens > MAX_TOKENS:
        # Hard trim as last resort
        prompt = prompt[:MAX_TOKENS * _CHARS_PER_TOKEN]

    return prompt


def _estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN
