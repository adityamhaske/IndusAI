"""Tests for fault upload, size guardrails, and memory lifecycle."""
import io
import pandas as pd
import pytest
from app.services.fault_service import FaultService, MAX_ROWS, MAX_FILE_SIZE_MB
from app.core.fault_exceptions import FaultTooLargeError, DatasetNotLoadedError

SEED = 42


def _make_df(n: int) -> tuple[pd.DataFrame, bytes]:
    import random
    random.seed(SEED)
    rows = {
        "fault_code": [f"E{i % 10:03d}" for i in range(n)],
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC"),
        "device": ["PLC-A"] * n,
        "message": ["Test message"] * n,
    }
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return df, buf.getvalue()


@pytest.fixture(autouse=True)
def reset_service():
    """Ensure clean state before each test."""
    svc = FaultService()
    svc.reset("default")
    yield
    svc.reset("default")


def test_upload_small_dataset():
    df, raw = _make_df(100)
    svc = FaultService()
    result = svc.upload(df, "test.csv", raw)
    assert result["total_rows"] == 100
    assert len(result["preview"]) == 10
    assert result["sampled"] is False


def test_upload_sets_dataset_hash():
    df, raw = _make_df(50)
    svc = FaultService()
    result = svc.upload(df, "test.csv", raw)
    assert len(result["dataset_hash"]) == 64  # SHA256 hex


def test_upload_rejects_over_max_rows():
    svc = FaultService()
    df_too_big = pd.DataFrame({
        "fault_code": ["E001"] * (MAX_ROWS + 1),
        "timestamp": pd.date_range("2024-01-01", periods=MAX_ROWS + 1, freq="1s", tz="UTC"),
        "device": ["PLC-A"] * (MAX_ROWS + 1),
        "message": ["msg"] * (MAX_ROWS + 1),
    })
    with pytest.raises(FaultTooLargeError):
        svc.upload(df_too_big, "big.csv", b"fake")


def test_previous_dataset_cleared_on_new_upload():
    df1, raw1 = _make_df(100)
    df2, raw2 = _make_df(200)
    svc = FaultService()
    svc.upload(df1, "first.csv", raw1)
    r2 = svc.upload(df2, "second.csv", raw2)
    assert r2["total_rows"] == 200
    assert len(svc._store) == 1  # MAX_DATASETS enforced


def test_dataset_not_loaded_raises():
    svc = FaultService()
    with pytest.raises(DatasetNotLoadedError):
        svc.get_summary("nonexistent")


def test_reset_clears_dataset():
    df, raw = _make_df(50)
    svc = FaultService()
    svc.upload(df, "test.csv", raw)
    svc.reset("default")
    with pytest.raises(DatasetNotLoadedError):
        svc.get_summary("default")


def test_metrics_before_upload():
    svc = FaultService()
    m = svc.get_metrics("default")
    assert m.dataset_loaded is False
    assert m.row_count == 0


def test_metrics_after_upload():
    df, raw = _make_df(500)
    svc = FaultService()
    svc.upload(df, "metrics_test.csv", raw)
    m = svc.get_metrics("default")
    assert m.dataset_loaded is True
    assert m.row_count == 500
    assert m.memory_mb > 0
