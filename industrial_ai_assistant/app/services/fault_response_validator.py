"""
FaultResponseValidator — strict structural validation for LLM output.

Rules:
  1. Output must parse as StructuredLLMOutput (Pydantic validates schema).
  2. related_plc_tags must not contain invented tags not in known_tags set.
  3. Hallucinated tags are removed and logged (not hard-rejected by default).
  4. If retry_count > 0, this is a retry — be more lenient on empty fields.
"""
import logging
from typing import List, Optional, Tuple

from app.models.fault_analysis_models import StructuredLLMOutput

logger = logging.getLogger(__name__)


class FaultResponseValidator:
    """Validates and cleans LLM structured output."""

    def validate(
        self,
        output: StructuredLLMOutput,
        retrieved_doc_sources: List[str],
        known_tags: Optional[List[str]] = None,
        is_retry: bool = False,
    ) -> Tuple[StructuredLLMOutput, List[str], List[str]]:
        """
        Validate and clean the LLM output.

        Returns:
            (cleaned_output, hallucinated_tags_removed, validation_warnings)
        """
        warnings: List[str] = []
        hallucinated: List[str] = []

        # ── 1. Field completeness checks ──────────────────────────────────────
        if not output.diagnosis or len(output.diagnosis.strip()) < 10:
            warnings.append("LLM diagnosis is empty or too short.")
            if not is_retry:
                output.diagnosis = "Analysis unavailable — LLM returned insufficient content."

        if not output.primary_action:
            warnings.append("LLM returned no primary action.")

        # ── 2. Tag hallucination check ─────────────────
        if known_tags and "related_plc_tags" in output.metrics:
            raw_tags = output.metrics["related_plc_tags"]
            valid_tags = []
            for tag in raw_tags:
                if tag in known_tags:
                    valid_tags.append(tag)
                else:
                    hallucinated.append(tag)
            output.metrics["related_plc_tags"] = valid_tags

        # ── 3. Truncate overly long free-text fields ──────────────────────────
        if len(output.diagnosis) > 1000:
            output.diagnosis = output.diagnosis[:1000] + "…"
            warnings.append("Diagnosis truncated to 1000 chars.")

        return output, hallucinated, warnings
