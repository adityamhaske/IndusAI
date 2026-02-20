"""
test_query_classification.py

Tests 25 sample queries against expected QueryIntent structure.
All rule-based — no LLM calls.
"""
import pytest
from app.services.query_classifier import classify
from app.models.project_models import QueryType


def _labels(query: str) -> list[QueryType]:
    return classify(query).labels


def _intent(query: str):
    return classify(query)


class TestTagLookup:
    def test_what_is_tag(self):
        assert QueryType.TAG_LOOKUP in _labels("What is tag Motor_Speed?")

    def test_find_tag(self):
        assert QueryType.TAG_LOOKUP in _labels("Find tag Fault_Active in the program")

    def test_tag_value(self):
        assert QueryType.TAG_LOOKUP in _labels("What is the current tag value?")

    def test_controller_tag(self):
        assert QueryType.TAG_LOOKUP in _labels("Show me all controller tags for the drive")


class TestIOLookup:
    def test_slot_query(self):
        assert QueryType.IO_LOOKUP in _labels("What is in slot 1:2?")

    def test_rio_query(self):
        assert QueryType.IO_LOOKUP in _labels("What RIO modules are connected?")

    def test_srio_query(self):
        assert QueryType.IO_LOOKUP in _labels("Which SRIO rack contains the safety PE?")

    def test_rack_query(self):
        assert QueryType.IO_LOOKUP in _labels("List all modules in rack 3")


class TestRoutineFlow:
    def test_routine_query(self):
        assert QueryType.ROUTINE_FLOW in _labels("Explain the MainRoutine logic")

    def test_rung_query(self):
        assert QueryType.ROUTINE_FLOW in _labels("What does rung 12 do?")

    def test_aoi_query(self):
        assert QueryType.ROUTINE_FLOW in _labels("How is the AOI Drive_Ctrl defined?")


class TestSystemFlow:
    def test_how_does(self):
        assert QueryType.SYSTEM_FLOW in _labels("How does the conveyor system start up?")

    def test_explain(self):
        assert QueryType.SYSTEM_FLOW in _labels("Explain the interlock logic for E-Stop")

    def test_why_does(self):
        assert QueryType.SYSTEM_FLOW in _labels("Why does the pallet lift trigger a fault?")


class TestDocumentation:
    def test_manual(self):
        assert QueryType.DOCUMENTATION in _labels("According to the manual, what is the safe speed?")

    def test_spec(self):
        assert QueryType.DOCUMENTATION in _labels("What does the specification say about RIO wiring?")


class TestCommissionProgress:
    def test_commissioned(self):
        assert QueryType.COMMISSION_PROGRESS in _labels("Which stations are commissioned?")

    def test_pending(self):
        assert QueryType.COMMISSION_PROGRESS in _labels("What subsystems are still pending sign-off?")

    def test_fat(self):
        assert QueryType.COMMISSION_PROGRESS in _labels("Is the FAT checklist complete?")


class TestMixedQuery:
    def test_motor_speed_rio_fault(self):
        """Mixed: TAG_LOOKUP + SYSTEM_FLOW"""
        intent = _intent("Why does Motor_Speed oscillate when RIO 3 faults?")
        assert QueryType.TAG_LOOKUP in intent.labels
        assert QueryType.SYSTEM_FLOW in intent.labels
        assert intent.structured_required is True
        assert intent.semantic_required is True

    def test_routine_how_does(self):
        """Mixed: ROUTINE_FLOW + SYSTEM_FLOW"""
        intent = _intent("How does the MainRoutine control the drive?")
        assert QueryType.ROUTINE_FLOW in intent.labels
        assert QueryType.SYSTEM_FLOW in intent.labels

    def test_tag_and_manual(self):
        """Mixed: TAG_LOOKUP + DOCUMENTATION"""
        intent = _intent("According to the manual, what should tag Motor_Speed be at idle?")
        assert QueryType.TAG_LOOKUP in intent.labels
        assert QueryType.DOCUMENTATION in intent.labels


class TestUnknown:
    def test_gibberish(self):
        intent = _intent("xyzzy frobulate the quux")
        assert QueryType.UNKNOWN in intent.labels
        assert intent.semantic_required is True   # UNKNOWN always uses semantic

    def test_empty_like(self):
        intent = _intent("hello")
        assert QueryType.UNKNOWN in intent.labels
