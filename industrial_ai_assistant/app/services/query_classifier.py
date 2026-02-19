"""
QueryClassifier — pure rule-based query type classification.

No LLM involved. Classifies in < 1ms.

Priority:
  1. TAG_LOOKUP     — explicit PLC-tag-like tokens (UPPER_SNAKE tokens)
  2. IO_LOOKUP      — slot / rack / RIO / SRIO keywords
  3. ROUTINE_FLOW   — routine / rung / ladder / logic
  4. SYSTEM_FLOW    — flow / sequence / interlock / system overview
  5. COMMISSION_PROGRESS — commissioning / progress / punch list
  6. DOCUMENTATION  — catch-all for doc questions
  7. UNKNOWN        — fallback
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class QueryType(str, Enum):
    TAG_LOOKUP = "TAG_LOOKUP"
    IO_LOOKUP = "IO_LOOKUP"
    ROUTINE_FLOW = "ROUTINE_FLOW"
    SYSTEM_FLOW = "SYSTEM_FLOW"
    DOCUMENTATION = "DOCUMENTATION"
    COMMISSION_PROGRESS = "COMMISSION_PROGRESS"
    UNKNOWN = "UNKNOWN"


# ── Compiled patterns ─────────────────────────────────────────────────────────

# PLC tag-like token: starts with letter, uppercase+underscores, min 3 chars
# Deliberately excludes common English words (all-cap acronyms handled by stopwords)
_TAG_PATTERN = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")

_TAG_STOPWORDS = frozenset({
    "PLC", "HMI", "SCADA", "IO", "RIO", "SRIO", "AOI", "LAD", "FBD",
    "PDF", "TXT", "CSV", "XML", "AND", "NOT", "THE", "FOR", "FROM",
    "WHAT", "HOW", "WHY", "WHEN", "WHERE", "WHO", "DOES", "CAN", "IS",
    "ARE", "HAS", "HAVE", "DOES", "DID", "WILL", "SHOULD", "WOULD",
    "TAG", "TAGS", "SLOT", "RACK", "ALL", "NEW",
})

_IO_KEYWORDS = frozenset({
    "slot", "rack", "module", "rio", "srio", "enet", "remote io",
    "remote i/o", "i/o", "io map", "io list", "io sheet", "io assignment",
    "channel", "point", "analog input", "digital output", "digital input",
    "analog output",
})

_ROUTINE_KEYWORDS = frozenset({
    "routine", "rung", "ladder", "logic", "function block", "structured text",
    "sequential", "fbr", "aoi", "instruction", "interlocking rung",
})

_SYSTEM_KEYWORDS = frozenset({
    "system flow", "system overview", "interlock", "safety", "pe", "safet pe",
    "sequence", "sequence of operations", "permissive", "machine state",
    "state machine", "overall", "architecture", "flow", "shutdown", "startup",
})

_COMMISSION_KEYWORDS = frozenset({
    "commissioning", "commission", "progress", "complete", "incomplete",
    "punch list", "punch", "tested", "verified", "not tested",
    "outstanding", "remaining",
})


def classify(query: str) -> QueryType:
    """
    Classify a query string into a QueryType.
    Pure function — stateless, no side effects.
    """
    q_lower = query.lower()
    q_words = set(q_lower.split())

    # ── 1. IO_LOOKUP (before tag so "slot" queries go here) ───────────────────
    if _IO_KEYWORDS & q_words or any(kw in q_lower for kw in _IO_KEYWORDS if " " in kw):
        return QueryType.IO_LOOKUP

    # ── 2. TAG_LOOKUP — requires ≥1 non-stopword TAG-like token ──────────────
    tag_tokens = _TAG_PATTERN.findall(query)
    meaningful_tags = [t for t in tag_tokens if t not in _TAG_STOPWORDS]
    if meaningful_tags:
        return QueryType.TAG_LOOKUP

    # ── 3. ROUTINE_FLOW ────────────────────────────────────────────────────────
    if _ROUTINE_KEYWORDS & q_words or any(kw in q_lower for kw in _ROUTINE_KEYWORDS if " " in kw):
        return QueryType.ROUTINE_FLOW

    # ── 4. COMMISSION_PROGRESS ────────────────────────────────────────────────
    if _COMMISSION_KEYWORDS & q_words or any(kw in q_lower for kw in _COMMISSION_KEYWORDS if " " in kw):
        return QueryType.COMMISSION_PROGRESS

    # ── 5. SYSTEM_FLOW ────────────────────────────────────────────────────────
    if _SYSTEM_KEYWORDS & q_words or any(kw in q_lower for kw in _SYSTEM_KEYWORDS if " " in kw):
        return QueryType.SYSTEM_FLOW

    # ── 6. DOCUMENTATION (catch-all for how/what/explain) ───────────────────
    if any(kw in q_lower for kw in ("how", "what", "explain", "describe", "why", "summarize")):
        return QueryType.DOCUMENTATION

    return QueryType.UNKNOWN


def extract_tag_tokens(text: str) -> list[str]:
    """
    Extract all candidate PLC tag tokens from arbitrary text.
    Used by the hallucination guard to find tags LLM claims to reference.
    """
    tokens = _TAG_PATTERN.findall(text)
    return [t for t in tokens if t not in _TAG_STOPWORDS]
