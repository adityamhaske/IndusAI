"""Tests for RAG + Orchestration integration."""
import pytest
from unittest.mock import MagicMock, patch
import json
import pandas as pd
from datetime import datetime, timezone

from app.services.fault_analysis_orchestrator import FaultAnalysisOrchestrator, _parse_llm_json
from app.services.rag_service import RAGService
from app.services.fault_response_validator import FaultResponseValidator
from app.services.fault_service import FaultService
from app.models.fault_analysis_models import FaultAnalysisRequest, StructuredLLMOutput, RetrievedDoc
from app.core.schemas import DocumentChunk, ChunkMetadata

SEED = 42

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_loaded_service(n=100) -> FaultService:
    svc = FaultService()
    svc.reset("default")
    df = pd.DataFrame({
        "row_id": list(range(n)),
        "fault_code": [f"E{i % 3:03d}" for i in range(n)],
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC"),
        "device": ["PLC-A"] * n,
        "message": ["Test msg"] * n,
        "severity": ["LOW"] * n,
    })
    svc.upload(df, "test.csv", b"raw", project_id="default")
    return svc


class _GoodMockLLM:
    def generate(self, prompt):
        return json.dumps({
            "summary": "Fault caused by sensor mismatch during pallet lift cycle.",
            "likely_causes": ["Sensor threshold mismatch", "Timing issue in PLC rung"],
            "diagnostic_steps": ["Check sensor status in I/O monitor", "Review timing rung sequence"],
            "preventive_actions": ["Calibrate sensor annually", "Add hysteresis to threshold"],
            "related_plc_tags": [],
            "confidence_explanation": "MEDIUM confidence — moderate occurrence frequency.",
        })


class _BadMockLLM:
    """Returns unparseable garbage."""
    def generate(self, prompt): return "This is plain text, not JSON at all!!!"


class _TimeoutMockLLM:
    """Raises on generate — simulates timeout."""
    def generate(self, prompt): raise RuntimeError("LLM connection timeout")


class _HallucinationLLM:
    """Returns valid JSON but with invented PLC tags."""
    def generate(self, prompt):
        return json.dumps({
            "summary": "Fault analysis",
            "likely_causes": ["Tag mismatch"],
            "diagnostic_steps": ["Check"],
            "preventive_actions": [],
            "related_plc_tags": ["FAKE_TAG_XYZ", "INVENTED_DB99_VAR"],
            "confidence_explanation": "HIGH",
        })


@pytest.fixture(autouse=True)
def reset_svc():
    FaultService().reset("default")
    yield
    FaultService().reset("default")


def _mock_rag() -> RAGService:
    """RAG service returning 2 synthetic docs."""
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = [
        DocumentChunk(
            content="When fault E000 occurs during pallet lift, check encoder alignment.",
            metadata=ChunkMetadata(source_file="encoder_setup.pdf", section_title="Encoder Setup", chunk_id="c1"),
        ),
        DocumentChunk(
            content="Cycle complete faults (INF) indicate normal sequence completion.",
            metadata=ChunkMetadata(source_file="cycle_manual.pdf", section_title="Conveyor Cycle", chunk_id="c2"),
        ),
    ]
    return RAGService(retriever=mock_retriever)


# ── Test 1: RAG returns relevant docs ────────────────────────────────────────

def test_rag_returns_docs():
    rag = _mock_rag()
    docs, ms = rag.retrieve_for_fault("E001", "Overcurrent", "PLC-A")
    assert len(docs) == 2
    assert docs[0].source_file == "encoder_setup.pdf"


# ── Test 2: Prompt includes deterministic stats ───────────────────────────────

def test_prompt_includes_stats():
    from app.services.fault_analysis_orchestrator import _build_prompt
    prompt = _build_prompt(
        row_id=0, fault_code="E001", device="PLC-A",
        ref_ts=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        severity="HIGH", message="Test msg",
        occ_1h=5, occ_24h=30, co_fault="E002",
        burst_detected=True, burst_desc="5 faults in 10 min",
        confidence="MEDIUM", docs=[], user_question=None,
    )
    assert "Occurrences last hour: 5" in prompt
    assert "Occurrences last 24 hours: 30" in prompt
    assert "Burst detected: Yes" in prompt
    assert "co-occurring fault: E002" in prompt
    assert "deterministic" in prompt.lower()


# ── Test 3: LLM output parsed correctly ──────────────────────────────────────

def test_llm_output_parsed():
    svc = _make_loaded_service()
    orch = FaultAnalysisOrchestrator(
        llm=_GoodMockLLM(),
        rag_service=_mock_rag(),
        validator=FaultResponseValidator(),
        fault_service=svc,
    )
    result = orch.analyze_fault(FaultAnalysisRequest(row_id=0, project_id="default"))
    assert result.analysis_version == "v2.0"
    assert "sensor" in result.summary.lower()
    assert len(result.likely_causes) >= 1
    assert len(result.diagnostic_steps) >= 1


# ── Test 4: Hallucinated tag rejected ────────────────────────────────────────

def test_hallucinated_tags_removed():
    svc = _make_loaded_service()
    known_tags = ["GOOD_TAG_A", "GOOD_TAG_B"]

    class ValidatorWithKnownTags(FaultResponseValidator):
        def validate(self, output, doc_sources, known_tags=None, is_retry=False):
            return super().validate(output, doc_sources, known_tags=["GOOD_TAG_A", "GOOD_TAG_B"], is_retry=is_retry)

    orch = FaultAnalysisOrchestrator(
        llm=_HallucinationLLM(),
        rag_service=_mock_rag(),
        validator=ValidatorWithKnownTags(),
        fault_service=svc,
    )
    result = orch.analyze_fault(FaultAnalysisRequest(row_id=0, project_id="default"))
    for tag in result.related_plc_tags:
        assert tag in known_tags, f"Hallucinated tag not removed: {tag}"
    assert len(result.hallucinated_tags_removed) == 2  # FAKE_TAG_XYZ, INVENTED_DB99_VAR


# ── Test 5: Custom question routed to prompt ──────────────────────────────────

def test_custom_question_in_prompt():
    """Verify user question appears in constructed prompt."""
    from app.services.fault_analysis_orchestrator import _build_prompt
    question = "Why does this happen after pallet is lifted?"
    prompt = _build_prompt(
        row_id=4, fault_code="INF_120", device="CONVEYOR-03",
        ref_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
        severity="LOW", message="Cycle Complete",
        occ_1h=2, occ_24h=18, co_fault="INF_110",
        burst_detected=False, burst_desc="",
        confidence="MEDIUM", docs=[], user_question=question,
    )
    assert "USER QUESTION" in prompt
    assert question in prompt


# ── Test 6: LLM timeout fallback ─────────────────────────────────────────────

def test_llm_timeout_uses_fallback():
    """
    When LLM raises a RuntimeError (e.g. timeout), the orchestrator now raises
    LLMResponseParseError instead of silently falling back.
    No silent fallback is allowed per the design spec.
    """
    svc = _make_loaded_service()

    # Inject a mock health service that reports LLM as ok so the preflight passes,
    # letting us test the LLM generate() failure path specifically.
    class _AlwaysOkHealth:
        def check_llm(self, **kw):
            return {"ok": True, "provider": "mock", "url": "mock://", "reason": None}

    orch = FaultAnalysisOrchestrator(
        llm=_TimeoutMockLLM(),
        rag_service=_mock_rag(),
        validator=FaultResponseValidator(),
        fault_service=svc,
        health_service=_AlwaysOkHealth(),
    )

    with pytest.raises(Exception) as exc_info:
        orch.analyze_fault(FaultAnalysisRequest(row_id=0, project_id="default"))

    # Must raise LLMResponseParseError, not silently return mock data
    from app.core.llm_exceptions import LLMResponseParseError
    assert isinstance(exc_info.value, LLMResponseParseError), (
        f"Expected LLMResponseParseError, got {type(exc_info.value).__name__}: {exc_info.value}"
    )


# ── Test 7: RAG empty → still gets stats-only response ───────────────────────

def test_empty_rag_still_returns_result():
    svc = _make_loaded_service()
    empty_retriever = MagicMock()
    empty_retriever.retrieve.return_value = []
    rag_empty = RAGService(retriever=empty_retriever)
    orch = FaultAnalysisOrchestrator(
        llm=_GoodMockLLM(),
        rag_service=rag_empty,
        validator=FaultResponseValidator(),
        fault_service=svc,
    )
    result = orch.analyze_fault(FaultAnalysisRequest(row_id=0, project_id="default"))
    assert result.docs_used == 0
    assert result.summary  # must still have a summary


# ── Test 8: Determinism — confidence not in LLM response ─────────────────────

def test_confidence_computed_deterministically():
    svc = _make_loaded_service()
    orch = FaultAnalysisOrchestrator(
        llm=_GoodMockLLM(),
        rag_service=_mock_rag(),
        validator=FaultResponseValidator(),
        fault_service=svc,
    )
    r1 = orch.analyze_fault(FaultAnalysisRequest(row_id=0, project_id="default"))
    r2 = orch.analyze_fault(FaultAnalysisRequest(row_id=0, project_id="default"))
    assert r1.confidence == r2.confidence   # Always deterministic


# ── Test 9: Response includes source list ────────────────────────────────────

def test_response_includes_sources():
    svc = _make_loaded_service()
    orch = FaultAnalysisOrchestrator(
        llm=_GoodMockLLM(),
        rag_service=_mock_rag(),
        validator=FaultResponseValidator(),
        fault_service=svc,
    )
    result = orch.analyze_fault(FaultAnalysisRequest(row_id=0, project_id="default"))
    assert result.docs_used == 2
    assert any("encoder" in s.source_file for s in result.sources)
