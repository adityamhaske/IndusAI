"""
QueryClassifier — Multi-label rule-based query intent classification.

Design:
  - Pure regex + keyword matching; no LLM call, no external deps
  - Returns QueryIntent with multi-label output
  - A single query can match TAG_LOOKUP + SYSTEM_FLOW simultaneously
  - Deterministic and testable
"""
import re
from typing import List

from app.models.project_models import QueryIntent, QueryLabel

# ── Pattern definitions ────────────────────────────────────────────────────────
# Each pattern is (label, compiled_regex)
_PATTERNS: List[tuple[QueryLabel, re.Pattern]] = [
    (
        "TAG_LOOKUP",
        re.compile(
            r"\b(tag|what is tag|find tag|tag value|tag name|"
            r"what does tag|plc tag|controller tag|"
            r"[A-Z][A-Z0-9_]{2,})\b",  # bare uppercase identifier
            re.IGNORECASE,
        ),
    ),
    (
        "IO_LOOKUP",
        re.compile(
            r"\b(slot|rack|rio|srio|module|io map|io sheet|"
            r"i\/o|input|output|digital|analog|"
            r"chassis|point io|flex io|remote io|distributed io)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "ROUTINE_FLOW",
        re.compile(
            r"\b(routine|rung|ladder|ladder logic|program flow|"
            r"logic block|fbd|function block|structured text|"
            r"subroutine|jsr|call|instruction)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "SYSTEM_FLOW",
        re.compile(
            r"\b(how does|explain|describe|what does .{1,40} do|"
            r"system flow|process flow|sequence|interlock|"
            r"why does|reason for|cause of|purpose of|overview)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "DOCUMENTATION",
        re.compile(
            r"\b(manual|spec|specification|document|datasheet|"
            r"according to|refer to|reference|standard|"
            r"safety pe|sil|functional safety)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "COMMISSION_PROGRESS",
        re.compile(
            r"\b(commission|commissioning|progress|complete|completed|"
            r"pending|outstanding|checklist|status|tested|"
            r"loop test|sign off|sign-off|handover)\b",
            re.IGNORECASE,
        ),
    ),
]


def classify(query: str) -> QueryIntent:
    """
    Classify a query into a multi-label QueryIntent.

    Returns:
        QueryIntent with:
          - labels: all matching QueryLabel values
          - structured_required: True if TAG/IO/ROUTINE matched
          - semantic_required: True if SYSTEM_FLOW/DOCUMENTATION matched
          - progress_required: True if COMMISSION_PROGRESS matched
    """
    matched: List[QueryLabel] = []

    for label, pattern in _PATTERNS:
        if pattern.search(query):
            matched.append(label)

    if not matched:
        matched = ["UNKNOWN"]

    structured_required = any(l in matched for l in ("TAG_LOOKUP", "IO_LOOKUP", "ROUTINE_FLOW"))
    semantic_required   = any(l in matched for l in ("SYSTEM_FLOW", "DOCUMENTATION", "UNKNOWN"))
    progress_required   = "COMMISSION_PROGRESS" in matched

    return QueryIntent(
        structured_required=structured_required,
        semantic_required=semantic_required,
        progress_required=progress_required,
        labels=matched,
    )
