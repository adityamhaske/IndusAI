"""
test_structured_index_lookup.py

Tests:
  - get_tag() hit/miss, case-insensitive
  - get_io() by slot
  - get_routine()
  - search_tags_prefix()
  - stats() returns memory_footprint_mb
  - Hard cap enforcement at MAX_TAGS
"""
import pytest
from app.indexes.structured_index import (
    MAX_TAGS,
    StructuredIndex,
    get_structured_index,
    clear_structured_index,
)
from app.models.project_models import IORecord, RoutineRecord, TagRecord


@pytest.fixture()
def si():
    idx = StructuredIndex("unit_test")
    idx.clear()
    # Seed some records
    idx.add_tag(TagRecord(name="Motor_Speed", data_type="REAL", scope="Controller",
                           description="Drive speed", source_file="test.L5X"))
    idx.add_tag(TagRecord(name="Fault_Active", data_type="BOOL", scope="Controller",
                           source_file="test.L5X"))
    idx.add_tag(TagRecord(name="Conv_Run", data_type="BOOL", scope="Program:MainProg",
                           source_file="test.L5X"))
    idx.add_routine(RoutineRecord(name="MainRoutine", program="MainProg",
                                   routine_type="LAD", rung_count=10,
                                   content_snippet="XIC(Fault_Active)OTL(Motor_Speed)",
                                   source_file="test.L5X"))
    idx.add_io(IORecord(slot="1:0", rack="1", module="1756-IB16D",
                         description="Start PB", tag_name="Conv_Start",
                         source_file="io.xlsx"))
    return idx


class TestTagLookup:
    def test_exact_match(self, si):
        tag = si.get_tag("Motor_Speed")
        assert tag is not None
        assert tag.data_type == "REAL"

    def test_case_insensitive(self, si):
        assert si.get_tag("motor_speed") is not None
        assert si.get_tag("MOTOR_SPEED") is not None

    def test_miss_returns_none(self, si):
        assert si.get_tag("NonExistentTag_XYZ") is None

    def test_scoped_tag(self, si):
        assert si.get_tag("Conv_Run") is not None

    def test_all_tag_names_is_frozenset(self, si):
        names = si.all_tag_names()
        assert isinstance(names, frozenset)
        assert "Motor_Speed" in names

    def test_all_tag_names_lower(self, si):
        lower = si.all_tag_names_lower()
        assert "motor_speed" in lower


class TestPrefixSearch:
    def test_prefix_match(self, si):
        hits = si.search_tags_prefix("Motor", limit=5)
        assert any(h.name == "Motor_Speed" for h in hits)

    def test_prefix_case_insensitive(self, si):
        hits = si.search_tags_prefix("motor", limit=5)
        assert len(hits) >= 1

    def test_prefix_no_match(self, si):
        hits = si.search_tags_prefix("ZZZ_NONEXISTENT", limit=5)
        assert hits == []


class TestIOLookup:
    def test_get_io_by_slot(self, si):
        io = si.get_io("1:0")
        assert io is not None
        assert io.tag_name == "Conv_Start"

    def test_get_io_miss(self, si):
        assert si.get_io("9:9") is None

    def test_io_description_search(self, si):
        hits = si.search_io_description("Start", limit=5)
        assert len(hits) >= 1


class TestRoutineLookup:
    def test_get_routine(self, si):
        rtn = si.get_routine("MainRoutine")
        assert rtn is not None
        assert rtn.rung_count == 10

    def test_get_routine_miss(self, si):
        assert si.get_routine("NonExistentRoutine") is None


class TestStats:
    def test_stats_counts(self, si):
        stats = si.stats()
        assert stats.tags == 3
        assert stats.routines == 1
        assert stats.io_rows == 1

    def test_memory_footprint_is_float(self, si):
        stats = si.stats()
        assert isinstance(stats.memory_footprint_mb, float)
        assert stats.memory_footprint_mb >= 0.0

    def test_at_capacity_false_for_normal(self, si):
        assert not si.stats().at_capacity

    def test_hard_cap_enforced(self):
        """Adding more than MAX_TAGS tags must not exceed cap."""
        mini_idx = StructuredIndex("cap_test")
        mini_idx._tags = {}  # fresh
        # monkeypatch MAX_TAGS locally
        import app.indexes.structured_index as m
        original = m.MAX_TAGS
        m.MAX_TAGS = 3
        try:
            for i in range(5):
                mini_idx.add_tag(TagRecord(name=f"Tag_{i}", data_type="BOOL",
                                            source_file="x.L5X"))
            assert len(mini_idx._tags) <= 3
        finally:
            m.MAX_TAGS = original
