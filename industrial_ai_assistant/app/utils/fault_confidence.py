"""
Deterministic confidence engine for PLC fault analysis.
LLM never decides confidence — this module does.

Thresholds (tuned for PLC commissioning context):
  HIGH   : occurrences_1h >= 10 AND burst detected
  MEDIUM : occurrences_1h >= 3
  LOW    : anything else
"""
from typing import Literal

ConfidenceLevel = Literal["LOW", "MEDIUM", "HIGH"]


def compute_confidence(
    occurrences_1h: int,
    burst_detected: bool,
    occurrences_24h: int = 0,
) -> ConfidenceLevel:
    """
    Deterministic confidence based on fault frequency and burst intensity.

    Args:
        occurrences_1h:  Count of same fault in the trailing 1 hour.
        burst_detected:  Whether a fault burst was detected globally.
        occurrences_24h: Count in trailing 24 hours (reserved for future refinement).

    Returns:
        "HIGH" | "MEDIUM" | "LOW"
    """
    if occurrences_1h >= 10 and burst_detected:
        return "HIGH"
    elif occurrences_1h >= 3:
        return "MEDIUM"
    else:
        return "LOW"
