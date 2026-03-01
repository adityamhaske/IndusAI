"""
ConfidenceV2 — Numeric confidence scoring (Phase 21).

Replaces static HIGH/MEDIUM/LOW with a weighted 0-100% score.
Factors:
  - Retrieval quality (30%)
  - Historical match (25%)
  - Context coverage (20%)
  - Anomaly signal strength (15%)
  - Output consistency (10%)
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Weight configuration
W_RETRIEVAL = 0.30
W_HISTORICAL = 0.25
W_COVERAGE = 0.20
W_ANOMALY = 0.15
W_CONSISTENCY = 0.10


def compute_confidence_v2(
    retrieval_scores: list[float] | None = None,
    historical_match: bool = False,
    context_coverage_ratio: float = 0.0,
    anomaly_score: float = 0.0,
    output_length: int = 0,
    expected_min_length: int = 100,
) -> tuple[float, str]:
    """
    Compute numeric confidence score (0.0 – 1.0) and label.

    Returns:
        (score, label) where label is LOW/MEDIUM/HIGH/VERY_HIGH
    """
    # ── Factor 1: Retrieval quality (avg RRF/cosine score) ───────────────────
    if retrieval_scores and len(retrieval_scores) > 0:
        avg_score = sum(retrieval_scores) / len(retrieval_scores)
        # Normalize: RRF scores are typically 0.01–0.03 range
        # Cosine scores are 0.0–1.0
        if avg_score < 0.1:  # RRF range
            retrieval_factor = min(avg_score / 0.033, 1.0)  # 0.033 = ~good RRF
        else:  # Cosine range
            retrieval_factor = min(avg_score, 1.0)
    else:
        retrieval_factor = 0.0

    # ── Factor 2: Historical pattern match ───────────────────────────────────
    historical_factor = 1.0 if historical_match else 0.0

    # ── Factor 3: Context coverage (how much of query is covered by docs) ────
    coverage_factor = min(context_coverage_ratio, 1.0)

    # ── Factor 4: Anomaly signal strength ────────────────────────────────────
    # Higher anomaly score = more data to reason about = higher confidence
    anomaly_factor = min(anomaly_score / 3.0, 1.0) if anomaly_score > 0 else 0.3

    # ── Factor 5: Output consistency (length as proxy) ───────────────────────
    if output_length >= expected_min_length:
        consistency_factor = min(output_length / (expected_min_length * 3), 1.0)
    else:
        consistency_factor = output_length / expected_min_length if expected_min_length > 0 else 0.0

    # ── Weighted combination ─────────────────────────────────────────────────
    score = (
        W_RETRIEVAL * retrieval_factor
        + W_HISTORICAL * historical_factor
        + W_COVERAGE * coverage_factor
        + W_ANOMALY * anomaly_factor
        + W_CONSISTENCY * consistency_factor
    )

    score = round(min(max(score, 0.0), 1.0), 3)

    # ── Label mapping ────────────────────────────────────────────────────────
    if score >= 0.75:
        label = "VERY_HIGH"
    elif score >= 0.55:
        label = "HIGH"
    elif score >= 0.35:
        label = "MEDIUM"
    else:
        label = "LOW"

    logger.debug(
        "ConfidenceV2: score=%.1f%% label=%s | retrieval=%.2f historical=%.2f coverage=%.2f anomaly=%.2f consistency=%.2f",
        score * 100, label,
        retrieval_factor, historical_factor, coverage_factor, anomaly_factor, consistency_factor,
    )

    return score, label
