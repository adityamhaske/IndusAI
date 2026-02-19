"""
Tests for the hallucination guard in QueryOrchestrator.

Tests the guard in isolation without needing a live LLM or Qdrant.
"""
import pytest

from app.core.project_exceptions import TagHallucinationError, ProjectNotReadyError
from app.indexes.structured_index import ProjectStructuredIndex
from app.models.project_models import (
    IngestionStatus,
    ProjectQueryRequest,
    TagRecord,
)
from app.services.project_context_manager import ProjectContextManager
from app.services.query_orchestrator import QueryOrchestrator


# ── Test doubles ──────────────────────────────────────────────────────────────

class _MockLLM:
    """LLM that returns a pre-configured response."""
    def __init__(self, response: str):
        self._response = response

    def generate(self, prompt: str) -> str:
        return self._response


class _NoopSemanticIndex:
    def search(self, project_id, query, top_k=5): return []
    def index_chunks(self, *a, **k): return 0
    def delete_project(self, *a): pass


def _make_ready_project(project_id="p_test") -> tuple[ProjectContextManager, ProjectStructuredIndex]:
    ctx = ProjectContextManager()
    # Set an arbitrary existing folder (use /tmp)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        ctx.set_project(project_id, d)
    ctx.mark_running(project_id)
    ctx.mark_complete(project_id, {
        "files_indexed": 1, "tags_indexed": 5,
        "routines_indexed": 2, "aois_indexed": 1,
        "io_rows_indexed": 0, "semantic_chunks": 10,
    })

    struct_idx = ProjectStructuredIndex(project_id)
    struct_idx.tags.add(TagRecord(name="CONV_RUN", data_type="BOOL", description="Conveyor Running"))
    struct_idx.tags.add(TagRecord(name="PUMP_SPD", data_type="REAL", description="Pump Speed"))
    struct_idx.tags.add(TagRecord(name="MOTOR_FLT", data_type="BOOL", description="Motor Fault"))
    return ctx, struct_idx


# ── Hallucination detection ────────────────────────────────────────────────────

def test_real_tags_pass_guard():
    ctx, struct_idx = _make_ready_project("p1")
    # LLM returns only known tags
    llm = _MockLLM("The tag CONV_RUN is active when the conveyor is running. PUMP_SPD controls speed.")
    orch = QueryOrchestrator(ctx, struct_idx, _NoopSemanticIndex(), llm)
    result = orch.query(ProjectQueryRequest(project_id="p1", query="What does CONV_RUN do?"))
    assert "CONV_RUN" in result.tags_referenced


def test_invented_tag_raises_hallucination_error():
    ctx, struct_idx = _make_ready_project("p2")
    # LLM invents a tag not in the index
    llm = _MockLLM("The tag GHOST_SENSOR_XYZ triggers when pressure exceeds limit.")
    orch = QueryOrchestrator(ctx, struct_idx, _NoopSemanticIndex(), llm)
    with pytest.raises(TagHallucinationError) as exc_info:
        orch.query(ProjectQueryRequest(project_id="p2", query="What sensors do we have?"))
    assert "GHOST_SENSOR_XYZ" in exc_info.value.invented_tags


def test_multiple_invented_tags_all_reported():
    ctx, struct_idx = _make_ready_project("p3")
    llm = _MockLLM("Tags FAKE_TAG_A and GHOST_TAG_B are used for monitoring.")
    orch = QueryOrchestrator(ctx, struct_idx, _NoopSemanticIndex(), llm)
    with pytest.raises(TagHallucinationError) as exc_info:
        orch.query(ProjectQueryRequest(project_id="p3", query="List all tags"))
    invented = exc_info.value.invented_tags
    assert "FAKE_TAG_A" in invented
    assert "GHOST_TAG_B" in invented


def test_mixed_real_and_invented_triggers_guard():
    ctx, struct_idx = _make_ready_project("p4")
    # CONV_RUN is real, PHANTOM_VAL is invented
    llm = _MockLLM("CONV_RUN is active. Also check PHANTOM_VAL for status.")
    orch = QueryOrchestrator(ctx, struct_idx, _NoopSemanticIndex(), llm)
    with pytest.raises(TagHallucinationError) as exc_info:
        orch.query(ProjectQueryRequest(project_id="p4", query="What is running?"))
    assert "PHANTOM_VAL" in exc_info.value.invented_tags
    # Real tag should NOT be in invented list
    assert "CONV_RUN" not in exc_info.value.invented_tags


def test_no_tags_in_answer_passes_guard():
    ctx, struct_idx = _make_ready_project("p5")
    # LLM answer with no tag-like tokens
    llm = _MockLLM("The conveyor is controlled by the sequence logic described in the docs.")
    orch = QueryOrchestrator(ctx, struct_idx, _NoopSemanticIndex(), llm)
    result = orch.query(ProjectQueryRequest(project_id="p5", query="How does the conveyor work?"))
    assert result.answer is not None


# ── Project not ready gate ─────────────────────────────────────────────────────

def test_query_raises_if_project_not_ready():
    ctx = ProjectContextManager()
    struct_idx = ProjectStructuredIndex("p_unready")
    llm = _MockLLM("some answer")
    orch = QueryOrchestrator(ctx, struct_idx, _NoopSemanticIndex(), llm)
    with pytest.raises(ProjectNotReadyError):
        orch.query(ProjectQueryRequest(project_id="p_unready", query="What is CONV_RUN?"))
