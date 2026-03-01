"""
QueryClassifier — rule-based multi-label query intent classification.

Returns QueryIntent with potentially multiple labels.
No LLM call — deterministic, fast, testable.

Multi-label example:
  "Why does Motor_Speed oscillate when RIO 3 faults?"
  → labels=[TAG_LOOKUP, SYSTEM_FLOW]
  → structured_required=True, semantic_required=True
"""
from __future__ import annotations

import re

from app.models.project_models import QueryIntent, QueryType, IntentType

# ── Rule patterns —————————————————————————————————————————————————————————────
# Each entry: (QueryType, list_of_patterns_any_of_which_triggers_the_label)

_RULES: list[tuple[QueryType, list[str]]] = [
    (
        QueryType.TAG_LOOKUP,
        [
            r"\btag\b", r"\btags\b", r"\bwhat is\s+\w+\b", r"\bfind tag\b",
            r"\btag value\b", r"\bvariable\b", r"\bglobal variable\b",
            r"\bdata type\b", r"\bplc tag\b", r"\bplc variable\b",
            r"\bcontroller tag\b", r"\bcontroller tags\b",
        ],
    ),
    (
        QueryType.IO_LOOKUP,
        [
            r"\bslot\b", r"\brack\b", r"\bmodule\b", r"\brio\b", r"\bsrio\b",
            r"\bio map\b", r"\bio card\b", r"\bdigital input\b", r"\bdigital output\b",
            r"\banalog input\b", r"\banalog output\b", r"\bflex io\b", r"\bpointio\b",
            r"\bremote io\b", r"\bsafety pe\b", r"\bsafety io\b",
        ],
    ),
    (
        QueryType.ROUTINE_FLOW,
        [
            r"\broutine\b", r"\broutines\b", r"\brung\b", r"\bladder\b",
            r"\bprogram\b", r"\bst code\b", r"\bstructured text\b",
            r"\bfbd\b", r"\bsfc\b", r"\baoi\b",
            r"\badd-on instruction\b", r"\bsequence\b", r"\bstate machine\b",
            r"\blogic\b",
        ],
    ),
    (
        QueryType.SYSTEM_FLOW,
        [
            r"\bhow does\b", r"\bexplain\b", r"\bwhat does\b", r"\bwhy does\b",
            r"\bflow\b", r"\bprocess\b", r"\boperation\b", r"\binterlock\b",
            r"\bsystem\b", r"\barchitecture\b", r"\bcontrol logic\b",
            r"\bwhen does\b", r"\btrigger\b", r"\bcondition\b",
        ],
    ),
    (
        QueryType.DOCUMENTATION,
        [
            r"\bmanual\b", r"\bspec\b", r"\bspecification\b", r"\bdocument\b",
            r"\baccording to\b", r"\bstandard\b", r"\breference\b", r"\bpdf\b",
            r"\bdata sheet\b", r"\bdatasheet\b", r"\bwiring diagram\b",
        ],
    ),
    (
        QueryType.COMMISSION_PROGRESS,
        [
            r"\bcommission\b", r"\bcommissioning\b", r"\bcommissioned\b",
            r"\bcomplete\b", r"\bpending\b", r"\bchecklist\b", r"\bprogress\b",
            r"\bsigned off\b", r"\bfat\b", r"\bsat\b",
            r"\bsite acceptance\b", r"\bfactory acceptance\b",
            r"\bpunch list\b", r"\bsnag\b",
        ],
    ),
]


def classify(query: str) -> QueryIntent:
    """
    Apply all rules. Accumulate matched labels.
    Returns multi-label QueryIntent — never raises.
    """
    q = query.lower()
    matched: list[QueryType] = []

    for qtype, patterns in _RULES:
        for pattern in patterns:
            if re.search(pattern, q):
                if qtype not in matched:
                    matched.append(qtype)
                break   # one match per rule group is enough

    # ── Token-based supplemental detection ────────────────────────────────────
    # Detect PLC-style identifiers even without explicit keyword context.

    # UPPER/mixed snake_case (Motor_Speed, CONV_RUN) → TAG_LOOKUP hint
    if re.search(r'\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b', query):
        if QueryType.TAG_LOOKUP not in matched:
            matched.append(QueryType.TAG_LOOKUP)

    # CamelCase multi-word identifiers (MainRoutine, DriveCtrl) → ROUTINE_FLOW hint
    if re.search(r'\b[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+\b', query):
        if QueryType.ROUTINE_FLOW not in matched:
            matched.append(QueryType.ROUTINE_FLOW)

    if not matched:
        matched = [QueryType.UNKNOWN]

    structured_required = any(
        lbl in matched
        for lbl in (QueryType.TAG_LOOKUP, QueryType.IO_LOOKUP, QueryType.ROUTINE_FLOW)
    )
    semantic_required = any(
        lbl in matched
        for lbl in (QueryType.SYSTEM_FLOW, QueryType.DOCUMENTATION, QueryType.UNKNOWN)
    )
    progress_required = QueryType.COMMISSION_PROGRESS in matched

    # Always use semantic when UNKNOWN — better to over-retrieve
    if QueryType.UNKNOWN in matched:
        semantic_required = True

    # ── Strict Intent Hierarchy Selection ─────────────────────────────────────
    intent_type = IntentType.GENERAL_QUERY.value
    
    # Phase 21: Expanded intent classification (order matters — most specific first)
    if re.search(r"\b(summarize|overview|explain document|summary of|describe the document)\b", q):
        intent_type = IntentType.DOCUMENT_SUMMARY.value
    elif re.search(r"\b(root cause|investigate|deep dive|why does.*fail|why did.*fail|fundamental|underlying)\b", q):
        intent_type = IntentType.ROOT_CAUSE_DEEP_DIVE.value
    elif re.search(r"\b(trend|pattern|increasing|decreasing|over time|weekly|daily|recurring|frequency|how often)\b", q):
        intent_type = IntentType.TREND_ANALYSIS.value
    elif re.search(r"\b(explain|describe|summarize).*(file|document)\b|\.[a-zA-Z0-9]{2,4}\b", q):
        intent_type = IntentType.FILE_EXPLANATION.value
    elif re.search(r"\b(fault|alarm|error|diagnostic|issue|failed|alm_\d+|err_\d+|trip|why did)\b", q):
        intent_type = IntentType.FAULT_ANALYSIS.value
    elif re.search(r"\b(flow|routine|sequence|ladder|sfc|state machine|architecture|process|how does|what does)\b", q):
        intent_type = IntentType.SYSTEM_FLOW.value


    return QueryIntent(
        labels=matched,
        structured_required=structured_required,
        semantic_required=semantic_required,
        progress_required=progress_required,
        raw_query=query,
        intent_type=intent_type,
    )
