"""Tests for fault summary and statistical computations."""
import pandas as pd
import pytest
from app.services.fault_service import FaultService
from app.utils.fault_statistics import (
    compute_fault_burst,
    compute_cooccurrence,
    compute_occurrences_in_window,
    _timestamps_for_code,
)

SEED = 42


def _make_full_df(n=1000) -> tuple[pd.DataFrame, bytes]:
    import hashlib
    rows = {
        "row_id": list(range(n)),
        "fault_code": [f"E{i % 5:03d}" for i in range(n)],
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC"),
        "device": ["PLC-A" if i % 3 == 0 else "PLC-B" for i in range(n)],
        "message": ["msg"] * n,
        "severity": ["LOW"] * n,
    }
    df = pd.DataFrame(rows)
    raw = b"fake_raw"
    return df, raw


@pytest.fixture(autouse=True)
def reset_service():
    svc = FaultService()
    svc.reset("default")
    yield
    svc.reset("default")


@pytest.fixture
def loaded_service():
    df, raw = _make_full_df()
    svc = FaultService()
    svc.upload(df, "test.csv", raw)
    return svc


def test_summary_total_rows(loaded_service):
    s = loaded_service.get_summary("default")
    assert s.total_rows == 1000


def test_summary_unique_fault_codes(loaded_service):
    s = loaded_service.get_summary("default")
    assert s.unique_fault_codes == 5


def test_summary_most_common_fault(loaded_service):
    s = loaded_service.get_summary("default")
    # All 5 codes appear equally (200 each). Any is valid.
    assert s.most_common_fault.startswith("E")
    assert s.most_common_count == 200


def test_summary_time_range(loaded_service):
    s = loaded_service.get_summary("default")
    assert s.time_range_start is not None
    assert s.time_range_end is not None
    assert s.time_range_end > s.time_range_start


def test_burst_detection_no_burst():
    df = pd.DataFrame({
        "fault_code": ["E001"] * 10,
        "timestamp": pd.date_range("2024-01-01", periods=10, freq="1h", tz="UTC"),
    })
    burst, desc, count = compute_fault_burst(df, threshold=5, window_min=10)
    assert burst is False


def test_burst_detection_with_burst():
    df = pd.DataFrame({
        "fault_code": ["E001"] * 10,
        "timestamp": pd.date_range("2024-01-01", periods=10, freq="1min", tz="UTC"),
    })
    burst, desc, count = compute_fault_burst(df, threshold=5, window_min=10)
    assert burst is True
    assert desc is not None


def test_occurrences_in_window():
    from datetime import datetime, timedelta, timezone
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    timestamps = [base + timedelta(minutes=i) for i in range(60)]
    ref = base + timedelta(minutes=30)
    count = compute_occurrences_in_window(timestamps, ref, hours=1)
    assert count > 0  # at least some in the 1h window


def test_cooccurrence_finds_different_code():
    df = pd.DataFrame({
        "row_id": range(10),
        "fault_code": ["E001", "E002", "E001", "E003", "E002", "E001", "E002", "E003", "E001", "E002"],
        "timestamp": pd.date_range("2024-01-01 12:00", periods=10, freq="2min", tz="UTC"),
        "device": ["PLC-A"] * 10,
        "message": ["msg"] * 10,
        "severity": ["LOW"] * 10,
    })
    ref_ts = df["timestamp"].iloc[4].to_pydatetime()
    co_fault, co_count = compute_cooccurrence(df, ref_ts, window_min=5)
    assert co_fault is not None
    assert co_count > 0


def test_summary_has_cached_frequency_dict(loaded_service):
    ds = loaded_service._store.get("default")
    assert "frequency_dict" in ds.stats_cache
    assert isinstance(ds.stats_cache["frequency_dict"], dict)
