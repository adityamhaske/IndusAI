"""Tests for fault analysis: LLM guard, confidence, deterministic stats, hash enforcement."""
import pandas as pd
import pytest
from app.services.fault_service import FaultService
from app.core.fault_exceptions import (
    DatasetNotLoadedError, FaultRowNotFoundError, DatasetHashMismatchError
)
from app.utils.fault_confidence import compute_confidence


# ── Fixtures ──────────────────────────────────────────────────────────────────

class MockLLM:
    def generate(self, prompt: str) -> str:
        return (
            '{"summary": "Test summary", "likely_causes": ["Cause A"], '
            '"resolution_steps": [{"title": "Step 1", "description": "Do X"}], '
            '"related_tags": ["E001"], "limitations": null}'
        )


def _make_df(n=200) -> tuple[pd.DataFrame, bytes]:
    df = pd.DataFrame({
        "row_id": list(range(n)),
        "fault_code": [f"E{i % 3:03d}" for i in range(n)],
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC"),
        "device": ["PLC-A"] * n,
        "message": ["msg"] * n,
        "severity": ["LOW"] * n,
    })
    return df, b"raw_bytes_for_hash"


@pytest.fixture(autouse=True)
def reset_service():
    svc = FaultService()
    svc.reset("default")
    yield
    svc.reset("default")


@pytest.fixture
def loaded_service():
    df, raw = _make_df()
    svc = FaultService()
    svc.upload(df, "analyze_test.csv", raw)
    return svc


# ── Confidence tests ───────────────────────────────────────────────────────────

def test_confidence_high():
    assert compute_confidence(occurrences_1h=12, burst_detected=True) == "HIGH"


def test_confidence_medium_freq():
    assert compute_confidence(occurrences_1h=5, burst_detected=False) == "MEDIUM"


def test_confidence_low():
    assert compute_confidence(occurrences_1h=1, burst_detected=False) == "LOW"


def test_confidence_boundary_no_burst():
    # >= 10 occurrences but no burst → MEDIUM not HIGH
    assert compute_confidence(occurrences_1h=10, burst_detected=False) == "MEDIUM"


# ── Analysis guard tests ───────────────────────────────────────────────────────

def test_analyze_no_dataset_raises():
    svc = FaultService()
    with pytest.raises(DatasetNotLoadedError):
        svc.analyze("default", 0, MockLLM(), "some_hash")


def test_analyze_row_not_found(loaded_service):
    ds = loaded_service._store["default"]
    with pytest.raises(FaultRowNotFoundError):
        loaded_service.analyze("default", 99999, MockLLM(), ds.dataset_hash)


def test_analyze_hash_mismatch(loaded_service):
    with pytest.raises(DatasetHashMismatchError):
        loaded_service.analyze("default", 0, MockLLM(), "wrong_hash")


def test_analyze_returns_correct_version(loaded_service):
    ds = loaded_service._store["default"]
    result = loaded_service.analyze("default", 0, MockLLM(), ds.dataset_hash)
    assert result.analysis_version == "v1.0"


def test_analyze_includes_statistics(loaded_service):
    ds = loaded_service._store["default"]
    result = loaded_service.analyze("default", 0, MockLLM(), ds.dataset_hash)
    assert "occurrences_last_hour" in result.statistics
    assert "occurrences_last_24h" in result.statistics
    assert "burst_detected" in result.statistics


def test_analyze_dataset_hash_in_response(loaded_service):
    ds = loaded_service._store["default"]
    result = loaded_service.analyze("default", 0, MockLLM(), ds.dataset_hash)
    assert result.dataset_hash == ds.dataset_hash


def test_analyze_confidence_is_deterministic(loaded_service):
    ds = loaded_service._store["default"]
    r1 = loaded_service.analyze("default", 0, MockLLM(), ds.dataset_hash)
    r2 = loaded_service.analyze("default", 0, MockLLM(), ds.dataset_hash)
    assert r1.confidence == r2.confidence   # Must be deterministic
