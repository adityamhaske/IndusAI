"""
test_hallucination_guard.py

Tests:
  - Real tags → pass (not flagged)
  - Invented UPPER_SNAKE tokens → detected
  - Invented scoped tag (Prog:Tag) → detected
  - Invented dotted tag (Motor.Fictitious) → detected
  - Invented CamelCase → detected
  - Fuzzy near-miss at 0.85 threshold → NOT flagged (close enough)
  - Empty known_tags → nothing flagged (can't validate)
  - Short tokens below min length → not inspected
"""
import pytest
from app.services.query_orchestrator import _detect_hallucinated_tags


@pytest.fixture()
def known():
    """Simulated known tags — the frozenset all_tag_names_lower() would return."""
    return frozenset([
        "motor_speed", "fault_active", "conv_run", "e_stop",
        "drive_enable", "pallet_lifted", "inf_110",
    ])


class TestPassCases:
    def test_real_tag_not_flagged(self, known):
        text = "The tag MOTOR_SPEED is set to 150 RPM."
        result = _detect_hallucinated_tags(text, known)
        assert "MOTOR_SPEED" not in result

    def test_multiple_real_tags(self, known):
        text = "FAULT_ACTIVE triggers when CONV_RUN is active."
        result = _detect_hallucinated_tags(text, known)
        assert len(result) == 0

    def test_empty_known_never_flags(self):
        """If no tags indexed, guard must not block anything."""
        text = "INVENTED_TAG_XYZ and ANOTHER_FAKE"
        result = _detect_hallucinated_tags(text, frozenset())
        assert result == []


class TestHallucinationDetection:
    def test_invented_upper_token(self, known):
        text = "The system uses TOTALLY_INVENTED_TAG_XYZ for control."
        result = _detect_hallucinated_tags(text, known)
        assert "TOTALLY_INVENTED_TAG_XYZ" in result

    def test_invented_scoped_tag(self, known):
        text = "MainProgram:FakeTag is referenced here."
        result = _detect_hallucinated_tags(text, known)
        # scoped pattern detected — FakeTag not in known
        assert any("FakeTag" in r or "MainProgram" in r for r in result)

    def test_invented_dotted_tag(self, known):
        text = "Use Motor.FictionalSpeed for this."
        result = _detect_hallucinated_tags(text, known)
        assert any("Motor" in r or "Fictional" in r for r in result)

    def test_multiple_invented_in_single_response(self, known):
        text = "Tags ALPHA_BETA, GAMMA_DELTA, EPSILON_ZETA are required."
        result = _detect_hallucinated_tags(text, known)
        assert len(result) >= 2

    def test_invented_tag_mixed_with_real(self, known):
        text = "MOTOR_SPEED is correct but INVENTED_ALPHA is not."
        result = _detect_hallucinated_tags(text, known)
        assert "MOTOR_SPEED" not in result
        assert "INVENTED_ALPHA" in result


class TestFuzzyThreshold:
    def test_near_miss_not_flagged(self, known):
        """'MOTOR_SPEEDD' is close enough (0.91 ratio) → should NOT be flagged."""
        text = "MOTOR_SPEEDD is nearly correct."
        result = _detect_hallucinated_tags(text, known)
        assert "MOTOR_SPEEDD" not in result

    def test_distant_token_flagged(self, known):
        """'XYZABC_UNKNOWN' is too far from any known tag → should be flagged."""
        text = "XYZABC_UNKNOWN is referenced."
        result = _detect_hallucinated_tags(text, known)
        assert "XYZABC_UNKNOWN" in result


class TestEdgeCases:
    def test_short_tokens_not_inspected(self, known):
        """Tokens shorter than min length (3) should not be inspected."""
        text = "AB CD EF are not PLC tags."
        result = _detect_hallucinated_tags(text, known)
        assert result == []

    def test_normal_english_not_flagged(self, known):
        """Normal English words should not be falsely flagged."""
        text = "The system operates normally without any faults."
        result = _detect_hallucinated_tags(text, known)
        assert len(result) == 0
