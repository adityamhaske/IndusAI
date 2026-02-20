"""
Tests — QueryClassifier multi-label intent classification.
"""
import pytest
from app.services.query_classifier import classify
from app.models.project_models import QueryIntent


def _labels(q: str):
    return classify(q).labels


def test_tag_lookup_basic():
    intent = classify("What is tag Motor_Speed?")
    assert "TAG_LOOKUP" in intent.labels
    assert intent.structured_required is True


def test_tag_lookup_find():
    assert "TAG_LOOKUP" in _labels("find tag Conv_1_Fault")


def test_io_lookup_slot():
    assert "IO_LOOKUP" in _labels("what module is in slot 3?")


def test_io_lookup_rio():
    assert "IO_LOOKUP" in _labels("show me the RIO mapping for rack 2")


def test_io_lookup_srio():
    assert "IO_LOOKUP" in _labels("SRIO 4 module configuration")


def test_routine_flow():
    intent = classify("explain the MainRoutine ladder logic")
    assert "ROUTINE_FLOW" in intent.labels
    assert intent.structured_required is True


def test_system_flow_how_does():
    intent = classify("how does the conveyor interlock work?")
    assert "SYSTEM_FLOW" in intent.labels
    assert intent.semantic_required is True


def test_system_flow_why():
    assert "SYSTEM_FLOW" in _labels("why does the system fault on startup?")


def test_documentation():
    intent = classify("what does the safety PE manual say about SIL2?")
    assert "DOCUMENTATION" in intent.labels
    assert intent.semantic_required is True


def test_commission_progress():
    intent = classify("what commissioning steps are still pending?")
    assert "COMMISSION_PROGRESS" in intent.labels
    assert intent.progress_required is True


def test_commission_checklist():
    assert "COMMISSION_PROGRESS" in _labels("show the loop test checklist progress")


def test_multi_label_mixed_query():
    """Mixed query: 'Why does Motor_Speed oscillate when RIO 3 faults?' → multiple labels."""
    intent = classify("Why does Motor_Speed oscillate when RIO 3 faults?")
    assert "SYSTEM_FLOW" in intent.labels           # 'why does'
    assert "IO_LOOKUP" in intent.labels             # 'RIO'
    assert intent.structured_required is True       # IO match
    assert intent.semantic_required is True         # system_flow


def test_multi_label_tag_and_routine():
    intent = classify("find tag Step_Counter and show me the routine that uses it")
    assert "TAG_LOOKUP" in intent.labels
    assert "ROUTINE_FLOW" in intent.labels


def test_unknown_catch_all():
    intent = classify("hello world")
    assert "UNKNOWN" in intent.labels
    assert intent.semantic_required is True   # UNKNOWN → prompt semantic


def test_no_labels_becomes_unknown():
    intent = classify("xyz abc 123")
    assert len(intent.labels) > 0
    assert "UNKNOWN" in intent.labels


def test_commission_sign_off():
    assert "COMMISSION_PROGRESS" in _labels("has loop test been signed off?")


def test_io_lookup_flex():
    assert "IO_LOOKUP" in _labels("flex io module at slot 4")


def test_system_flow_describe():
    assert "SYSTEM_FLOW" in _labels("describe the startup sequence")


def test_documentation_spec():
    assert "DOCUMENTATION" in _labels("according to the datasheet, what is the max current?")


def test_routine_fbd():
    assert "ROUTINE_FLOW" in _labels("show the function block diagram for the drive")


def test_returns_query_intent_model():
    result = classify("any question")
    assert isinstance(result, QueryIntent)
    assert isinstance(result.structured_required, bool)
    assert isinstance(result.semantic_required, bool)
    assert isinstance(result.labels, list)
