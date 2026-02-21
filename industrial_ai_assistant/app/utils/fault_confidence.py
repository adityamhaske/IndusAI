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
    burst_detected: bool,
    anomaly_score: float,
    integrity_passed: bool,
    occurrences_1h: int
) -> ConfidenceLevel:
    """
    Deterministic confidence based on fault frequency, burst intensity, and data integrity.

    Args:
        burst_detected:   Whether a fault burst was detected globally.
        anomaly_score:    Ratio of recent occurrences vs historical average.
        integrity_passed: Whether the metrics conceptually align (e.g. no 0 counts during a burst).
        occurrences_1h:   Count of same fault in the trailing 1 hour.

    Returns:
        "HIGH" | "MEDIUM" | "LOW"
    """
    if not integrity_passed:
        # If the data contradicts itself, we cannot have high confidence in any diagnosis.
        return "LOW"

    if burst_detected and anomaly_score > 3.0:
        return "HIGH"
    
    if occurrences_1h >= 3 or anomaly_score > 1.5:
        return "MEDIUM"
        
    return "LOW"
