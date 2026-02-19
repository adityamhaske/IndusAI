"""
Tests for StructuredIndex lookup functions.
"""
import pytest

from app.indexes.structured_index import (
    AOIIndex,
    IOIndex,
    ProjectStructuredIndex,
    RoutineIndex,
    TagIndex,
)
from app.models.project_models import AOIRecord, IORecord, RoutineRecord, TagRecord


# ── TagIndex ──────────────────────────────────────────────────────────────────

def _make_tag(name="CONV_RUN", data_type="BOOL", description="Conveyor Run"):
    return TagRecord(name=name, data_type=data_type, description=description)


def test_tag_index_exact_lookup():
    idx = TagIndex()
    idx.add(_make_tag("CONV_RUN"))
    result = idx.get("CONV_RUN")
    assert result.name == "CONV_RUN"


def test_tag_index_case_insensitive():
    idx = TagIndex()
    idx.add(_make_tag("CONV_RUN"))
    assert idx.get("conv_run").name == "CONV_RUN"
    assert idx.get("Conv_Run").name == "CONV_RUN"


def test_tag_index_missing_raises_key_error():
    idx = TagIndex()
    with pytest.raises(KeyError):
        idx.get("NONEXISTENT_TAG")


def test_tag_index_has_returns_false_for_missing():
    idx = TagIndex()
    assert not idx.has("GHOST_TAG")


def test_tag_index_add_batch():
    idx = TagIndex()
    tags = [_make_tag(f"TAG_{i}") for i in range(5)]
    idx.add_batch(tags)
    assert idx.count() == 5


def test_tag_index_partial_search():
    idx = TagIndex()
    idx.add(_make_tag("CONV_RUN"))
    idx.add(_make_tag("CONV_SPD"))
    idx.add(_make_tag("PUMP_RUN"))
    results = idx.search("CONV")
    assert len(results) == 2


# ── RoutineIndex ──────────────────────────────────────────────────────────────

def _make_routine(name="MainRoutine", program="MainProgram"):
    return RoutineRecord(name=name, program_name=program, type="LAD", rung_count=10)


def test_routine_index_lookup_by_name():
    idx = RoutineIndex()
    idx.add(_make_routine("StartupSeq", "MainProgram"))
    result = idx.get("StartupSeq")
    assert result.name == "StartupSeq"


def test_routine_index_lookup_by_program_routine():
    idx = RoutineIndex()
    idx.add(_make_routine("MainRoutine", "SafetyProgram"))
    result = idx.get("SafetyProgram.MainRoutine")
    assert result.program_name == "SafetyProgram"


def test_routine_index_missing_raises():
    idx = RoutineIndex()
    with pytest.raises(KeyError):
        idx.get("GhostRoutine")


# ── AOIIndex ──────────────────────────────────────────────────────────────────

def test_aoi_index_lookup():
    idx = AOIIndex()
    idx.add(AOIRecord(name="MOT_CTL", description="Motor Control"))
    result = idx.get("MOT_CTL")
    assert result.name == "MOT_CTL"


def test_aoi_index_case_insensitive():
    idx = AOIIndex()
    idx.add(AOIRecord(name="DriveCtrl", description="Drive"))
    assert idx.get("drivectrl").name == "DriveCtrl"


# ── IOIndex ───────────────────────────────────────────────────────────────────

def _make_io(slot="1:2:0", tag="CONV_RUN"):
    return IORecord(slot=slot, tag_name=tag, description="Conveyor Run DI")


def test_io_index_lookup_by_slot():
    idx = IOIndex()
    idx.add(_make_io("1:2:0", "CONV_RUN"))
    result = idx.get_by_slot("1:2:0")
    assert result.slot == "1:2:0"


def test_io_index_lookup_by_tag():
    idx = IOIndex()
    idx.add(_make_io("1:3:0", "PUMP_RUN"))
    result = idx.get_by_tag("PUMP_RUN")
    assert result.tag_name == "PUMP_RUN"


def test_io_index_missing_slot_raises():
    idx = IOIndex()
    with pytest.raises(KeyError):
        idx.get_by_slot("99:99:99")


# ── ProjectStructuredIndex ────────────────────────────────────────────────────

def test_project_index_get_tag_returns_none_on_miss():
    pidx = ProjectStructuredIndex("test_project")
    pidx.tags.add(_make_tag("CONV_RUN"))
    assert pidx.get_tag("GHOST") is None


def test_project_index_has_tag():
    pidx = ProjectStructuredIndex("p1")
    pidx.tags.add(_make_tag("KNOWN_TAG"))
    assert pidx.has_tag("KNOWN_TAG")
    assert not pidx.has_tag("UNKNOWN_TAG")


def test_project_index_stats():
    pidx = ProjectStructuredIndex("p1")
    pidx.tags.add_batch([_make_tag(f"T{i}") for i in range(10)])
    pidx.routines.add(_make_routine())
    stats = pidx.stats()
    assert stats["tags"] == 10
    assert stats["routines"] == 1
