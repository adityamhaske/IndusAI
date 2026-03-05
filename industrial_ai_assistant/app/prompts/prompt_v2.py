"""
PromptComposerV2 — Structured, per-intent prompt templates (Phase 21).

Replaces flat prompt building with modular section injection.
Each intent type gets a specialized template with structured sections:
  [Role] → [Statistical Snapshot] → [Historical Pattern] →
  [Past Similar Cases] → [Relevant Manual Sections] → [User Query]
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ── Per-Intent System Role Descriptions ───────────────────────────────────────

_ROLES = {
    "FAULT_ANALYSIS": (
        "You are an expert industrial diagnostic AI specializing in PLC fault analysis. "
        "You provide structured root-cause analysis with concrete troubleshooting steps. "
        "Always reference specific data points from the statistical context when available."
    ),
    "ROOT_CAUSE_DEEP_DIVE": (
        "You are a senior controls engineer performing deep root-cause investigation. "
        "Go beyond surface symptoms. Analyze underlying systemic causes, cascading failures, "
        "and chronic equipment degradation patterns. Reference historical data to support conclusions."
    ),
    "TREND_ANALYSIS": (
        "You are an industrial data analyst specializing in temporal fault pattern analysis. "
        "Focus on trends, recurring patterns, time-based correlations, and predictive indicators. "
        "Quantify observations with specific numbers from the provided data."
    ),
    "DOCUMENT_SUMMARY": (
        "You are a technical documentation specialist for industrial systems. "
        "Provide clear, structured summaries of equipment documentation. "
        "Highlight safety-critical information, maintenance procedures, and operating limits."
    ),
    "SYSTEM_FLOW": (
        "You are an automation engineer explaining control system architecture and logic flow. "
        "Describe signal paths, interlocks, sequences, and program structure clearly."
    ),
    "FILE_EXPLANATION": (
        "You are a PLC programming specialist. Explain the contents, structure, "
        "and purpose of automation project files. Reference specific tags, routines, and data types."
    ),
    "GENERAL_QUERY": (
        "You are an industrial AI assistant with deep knowledge of PLC systems, "
        "SCADA, process automation, and manufacturing equipment. "
        "Provide accurate, helpful responses grounded in the available documentation."
    ),
}

# ── JSON output schemas per intent ────────────────────────────────────────────

_FAULT_SCHEMA = """{
  "fault_summary": "<Summary of fault>",
  "root_cause": "<Cause of Fault>",
  "trigger_mechanism": "<Why fault triggered>",
  "resolution_steps": ["<Step 1>", "<Step 2>"],
  "confidence": "<LOW | MEDIUM | HIGH>"
}"""

_TREND_SCHEMA = """{
  "summary": "<Trend analysis summary>",
  "patterns_identified": ["<Pattern 1>", "<Pattern 2>"],
  "temporal_correlations": ["<Correlation 1>"],
  "risk_assessment": "<Current risk level and trajectory>",
  "recommended_actions": ["<Action 1>"],
  "confidence": "<LOW | MEDIUM | HIGH>"
}"""

_GENERAL_SCHEMA = """{
  "summary": "<Comprehensive explanation>",
  "key_points": ["<Point 1>", "<Point 2>"],
  "confidence": "<LOW | MEDIUM | HIGH>"
}"""


def _get_schema(intent_type: str) -> str:
    if intent_type in ("FAULT_ANALYSIS", "ROOT_CAUSE_DEEP_DIVE"):
        return _FAULT_SCHEMA
    elif intent_type == "TREND_ANALYSIS":
        return _TREND_SCHEMA
    return _GENERAL_SCHEMA


class PromptComposerV2:
    """Builds structured prompts with per-intent templates and context sections."""

    @staticmethod
    def compose(
        intent_type: str,
        user_query: str,
        *,
        statistical_snapshot: Optional[str] = None,
        historical_pattern: Optional[str] = None,
        past_experience: Optional[str] = None,
        manual_sections: Optional[str] = None,
        fault_context: Optional[str] = None,
        extra_instructions: Optional[str] = None,
    ) -> str:
        """
        Build a structured prompt from context blocks.
        Only non-empty sections are included.
        """
        role = _ROLES.get(intent_type, _ROLES["GENERAL_QUERY"])
        schema = _get_schema(intent_type)

        sections = [f"[Role]\n{role}"]

        if fault_context:
            sections.append(f"[Fault Context]\n{fault_context}")

        if statistical_snapshot:
            sections.append(f"[Statistical Snapshot]\n{statistical_snapshot}")

        if historical_pattern:
            sections.append(f"[Historical Pattern Memory]\n{historical_pattern}")

        if past_experience:
            sections.append(f"[Past Similar Analysis]\n{past_experience}")

        if manual_sections:
            sections.append(f"[Relevant Documentation]\n{manual_sections}")

        if extra_instructions:
            sections.append(f"[Additional Instructions]\n{extra_instructions}")

        sections.append(f"[User Query]\n{user_query}")

        sections.append(
            f"[Output Format]\n"
            f"Respond ONLY with valid JSON matching this schema:\n{schema}\n"
            f"Do not include any text outside the JSON object."
        )

        prompt = "\n\n".join(sections)

        logger.debug(
            "PromptComposerV2: intent=%s sections=%d chars=%d",
            intent_type, len(sections), len(prompt)
        )
        return prompt
