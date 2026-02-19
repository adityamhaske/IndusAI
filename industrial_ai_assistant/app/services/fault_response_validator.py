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
        if not output.summary or len(output.summary.strip()) < 10:
            warnings.append("LLM summary is empty or too short.")
            if not is_retry:
                output.summary = "Analysis summary unavailable — LLM returned insufficient content."

        if not output.likely_causes:
            warnings.append("LLM returned no likely causes.")

        if not output.diagnostic_steps:
            warnings.append("LLM returned no diagnostic steps.")

        # ── 2. Hallucination check: PLC tags ─────────────────────────────────
        if known_tags and output.related_plc_tags:
            clean_tags = []
            for tag in output.related_plc_tags:
                if tag in known_tags:
                    clean_tags.append(tag)
                else:
                    hallucinated.append(tag)
                    logger.warning("Hallucinated PLC tag removed: %s", tag)
            output.related_plc_tags = clean_tags
            if hallucinated:
                warnings.append(
                    f"Removed {len(hallucinated)} hallucinated tag(s): {hallucinated}"
                )

        # ── 3. Truncate overly long free-text fields ──────────────────────────
        if len(output.summary) > 2000:
            output.summary = output.summary[:2000] + "…"
            warnings.append("Summary truncated to 2000 chars.")

        return output, hallucinated, warnings
