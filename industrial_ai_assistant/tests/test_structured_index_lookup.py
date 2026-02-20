"""
Tests — StructuredIndex exact lookup, prefix search, memory stats.
"""
import pytest
from app.indexes.structured_index import StructuredIndex
from app.models.project_models import AOIRecord, IORecord, RoutineRecord, TagRecord


@pytest.fixture
def idx():
    s = StructuredIndex("test_struct_proj")
    s.load_tags([
        TagRecord(name="Motor_Speed", data_type="REAL", scope="Controller",
                  description="Motor speed setpoint"),
        TagRecord(name="Conv_1_Fault", data_type="BOOL", scope="Controller"),
        TagRecord(name="Conv_2_Fault", data_type="BOOL", scope="Controller"),
        TagRecord(name="Step_Counter", data_type="INT", scope="Program:Main"),
    ])
    s.load_routines([
        RoutineRecord(name="MainRoutine", program="MainProgram",
                      routine_type="RLL", rung_count=10,
                      content="XIC(Conv_1_Fault)OTE(Alarm);"),
        RoutineRecord(name="Startup", program="MainProgram", routine_type="RLL"),
    ])
    s.load_aois([
        AOIRecord(name="PhaseManager", description="Phase state machine",
                  parameters=["Phase", "Command"]),
    ])
    s.load_io([
        IORecord(slot="1", rack="0", module="1769-IF4",
                 description="Analog Speed Input", tag_name="AI_Speed"),
        IORecord(slot="2", rack="0", module="1769-OB8",
                 description="Digital Output", tag_name="DO_Run"),
    ])
    return s


# ── Tag lookup ────────────────────────────────────────────────────────────────

def test_get_tag_hit(idx):
    t = idx.get_tag("Motor_Speed")
    assert t is not None
    assert t.data_type == "REAL"
    assert "speed" in t.description.lower()


def test_get_tag_case_insensitive(idx):
    assert idx.get_tag("motor_speed") is not None
    assert idx.get_tag("MOTOR_SPEED") is not None


def test_get_tag_miss(idx):
    assert idx.get_tag("Totally_Fake_Tag") is None


def test_get_tag_program_scoped(idx):
    t = idx.get_tag("Step_Counter")
    assert t is not None
    assert "Program" in t.scope


# ── Routine lookup ────────────────────────────────────────────────────────────

def test_get_routine_hit(idx):
    r = idx.get_routine("MainRoutine")
    assert r is not None
    assert r.program == "MainProgram"
    assert "XIC" in r.content


def test_get_routine_miss(idx):
    assert idx.get_routine("NonExistentRoutine") is None


# ── IO lookup ─────────────────────────────────────────────────────────────────

def test_get_io_by_slot(idx):
    io = idx.get_io("1")
    assert io is not None
    assert "1769-IF4" in io.module


def test_get_io_miss(idx):
    assert idx.get_io("99") is None


# ── Prefix search ─────────────────────────────────────────────────────────────

def test_search_tags_prefix(idx):
    results = idx.search_tags_prefix("CONV")
    assert len(results) == 2
    names = {r.name.upper() for r in results}
    assert "CONV_1_FAULT" in names
    assert "CONV_2_FAULT" in names


def test_search_tags_prefix_limit(idx):
    results = idx.search_tags_prefix("", limit=2)
    assert len(results) <= 2


def test_all_tag_names(idx):
    names = idx.all_tag_names()
    assert "MOTOR_SPEED" in names
    assert "CONV_1_FAULT" in names
    assert len(names) == 4


# ── Stats + memory ────────────────────────────────────────────────────────────

def test_stats_counts(idx):
    s = idx.stats()
    assert s["tags"] == 4
    assert s["routines"] == 2
    assert s["aois"] == 1
    assert s["ios"] == 2


def test_stats_memory_mb(idx):
    s = idx.stats()
    assert isinstance(s["memory_mb"], float)
    assert s["memory_mb"] >= 0.0


def test_max_tags_warning():
    """Loading near MAX_TAGS should produce a warning."""
    from app.indexes.structured_index import MAX_TAGS, _WARN_AT
    s = StructuredIndex("warn_test")
    big_load = [
        TagRecord(name=f"TAG_{i:05d}", data_type="BOOL")
        for i in range(_WARN_AT + 1)
    ]
    s.load_tags(big_load)
    stats = s.stats()
    assert len(stats["warnings"]) > 0


def test_clear_purges_index(idx):
    idx.clear()
    assert idx.get_tag("Motor_Speed") is None
    s = idx.stats()
    assert s["tags"] == 0
