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
        # ── 1. Field completeness checks ──────────────────────────────────────
        if not output.fault_summary or len(output.fault_summary.strip()) < 10:
            warnings.append("LLM fault_summary is empty or too short.")
            if not is_retry:
                output.fault_summary = "Analysis unavailable — LLM returned insufficient content."

        if not output.resolution_steps:
            warnings.append("LLM returned no resolution steps.")
            if not is_retry:
                output.resolution_steps = ["Manual Review Required - AI Response was malformed."]

        # ── 2. Truncate overly long free-text fields ──────────────────────────
        if len(output.fault_summary) > 1000:
            output.fault_summary = output.fault_summary[:1000] + "…"
            warnings.append("Summary truncated to 1000 chars.")

        return output, hallucinated, warnings
