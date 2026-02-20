"""
Tests — Hallucination guard in QueryOrchestrator.

Validates that:
  - Real tags pass through
  - Invented tags are rejected with HallucinatedTagError
  - Scoped tags (Program:Tag) are recognized
  - Dotted references (Tag.Member) are recognized
  - Near-matches (fuzzy ratio ≥ 0.85) are accepted
  - Empty tag index skips validation (graceful degradation)
"""
import pytest
from app.services.query_orchestrator import _validate_tags
from app.core.project_exceptions import HallucinatedTagError


# Known tag set used across tests
KNOWN_TAGS = frozenset([
    "MOTOR_SPEED", "CONV_1_FAULT", "CONV_2_FAULT",
    "STEP_COUNTER", "AI_SPEED", "DO_RUN", "PHASE_MANAGER",
])


def test_real_tag_passes():
    result = _validate_tags("The tag MOTOR_SPEED is set to 1200 RPM.", KNOWN_TAGS)
    assert result == []


def test_multiple_real_tags_pass():
    result = _validate_tags(
        "CONV_1_FAULT clears when MOTOR_SPEED returns to setpoint.", KNOWN_TAGS
    )
    assert result == []


def test_invented_tag_rejected():
    result = _validate_tags("Maybe PHANTOM_TAG is causing the issue.", KNOWN_TAGS)
    assert "PHANTOM_TAG" in result


def test_multiple_invented_tags_rejected():
    result = _validate_tags("FAKE_TAG_X and INVENTED_SIGNAL are involved.", KNOWN_TAGS)
    assert len(result) >= 1


def test_scoped_tag_passes():
    """Program:TagName references should be resolved."""
    result = _validate_tags("In routine, Program:MOTOR_SPEED is used.", KNOWN_TAGS)
    assert result == []


def test_dotted_tag_member_passes():
    """Tag.Member references should be resolved to the base tag."""
    result = _validate_tags("CONV_1_FAULT.0 indicates sensor fault.", KNOWN_TAGS)
    assert result == []


def test_near_match_passes():
    """MOTOR_SPEEED (typo with ratio ~0.93) should pass fuzzy threshold."""
    result = _validate_tags("Set MOTOR_SPEEED to 1200 RPM.", KNOWN_TAGS)
    # Should NOT be rejected — close enough to MOTOR_SPEED
    assert "MOTOR_SPEEED" not in result


def test_completely_different_rejected():
    """ZZZZ_XXXX has no close match — must be rejected."""
    result = _validate_tags("ZZZZ_XXXX is undefined.", KNOWN_TAGS)
    assert "ZZZZ_XXXX" in result


def test_empty_known_tags_skips_validation():
    """If no tags are indexed, skip guard (graceful degradation)."""
    result = _validate_tags("ANY_TAG_HERE references something.", frozenset())
    assert result == []


def test_noise_words_ignored():
    """Common noise words like TRUE, FALSE, JSON should not trigger validation."""
    result = _validate_tags("Returns TRUE when condition is met. Format is JSON.", KNOWN_TAGS)
    assert result == []


def test_short_words_ignored():
    """Words shorter than 3 chars should be ignored."""
    result = _validate_tags("IO PLC CPU", KNOWN_TAGS)
    # These are in NOISE_WORDS or too short
    assert result == []


def test_valid_tags_with_invented_mix():
    """Mix of real and invented — only invented is rejected."""
    result = _validate_tags(
        "MOTOR_SPEED is real. GHOST_TAG_404 is invented.", KNOWN_TAGS
    )
    assert "MOTOR_SPEED" not in result
    assert "GHOST_TAG_404" in result


def test_lowercase_tags_ignored():
    """Guard should not flag lowercase words (not PLC tag pattern)."""
    result = _validate_tags("the motor speed is increasing slowly", KNOWN_TAGS)
    assert result == []
