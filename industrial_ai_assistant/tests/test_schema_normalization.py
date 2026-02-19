"""Tests for schema normalizer."""
import pandas as pd
import pytest
from app.utils.schema_normalizer import normalize
from app.core.fault_exceptions import FaultSchemaError


@pytest.fixture
def base_df():
    return pd.DataFrame({
        "fault_code": ["E001", "E002"],
        "timestamp": ["2024-01-01 10:00:00", "2024-01-01 11:00:00"],
        "device": ["PLC-A", "PLC-B"],
        "message": ["Overvoltage", "Undervoltage"],
    })


def test_synonym_mapping_error_code(base_df):
    base_df = base_df.rename(columns={"fault_code": "error_code"})
    df, warnings = normalize(base_df)
    assert "fault_code" in df.columns


def test_synonym_mapping_time(base_df):
    base_df = base_df.rename(columns={"timestamp": "time"})
    df, _ = normalize(base_df)
    assert "timestamp" in df.columns


def test_synonym_mapping_tag_to_device(base_df):
    base_df = base_df.rename(columns={"device": "tag"})
    df, _ = normalize(base_df)
    assert "device" in df.columns


def test_missing_required_fault_code(base_df):
    base_df = base_df.drop(columns=["fault_code"])
    with pytest.raises(FaultSchemaError) as exc_info:
        normalize(base_df)
    assert "fault_code" in str(exc_info.value)


def test_missing_required_timestamp(base_df):
    base_df = base_df.drop(columns=["timestamp"])
    with pytest.raises(FaultSchemaError):
        normalize(base_df)


def test_missing_device_defaults_to_unknown(base_df):
    base_df = base_df.drop(columns=["device"])
    df, warnings = normalize(base_df)
    assert (df["device"] == "UNKNOWN").all()
    assert any("device" in w for w in warnings)


def test_row_id_injected_and_sorted(base_df):
    # Reverse order — normalizer must sort
    base_df = base_df.iloc[::-1].reset_index(drop=True)
    df, _ = normalize(base_df)
    assert list(df["row_id"]) == list(range(len(df)))
    assert df["timestamp"].is_monotonic_increasing


def test_unparseable_timestamp_dropped():
    df = pd.DataFrame({
        "fault_code": ["E001", "E002"],
        "timestamp": ["CORRUPT", "2024-01-01 10:00:00"],
        "message": ["msg1", "msg2"],
    })
    result, warnings = normalize(df)
    assert len(result) == 1
    assert any("unparseable" in w for w in warnings)


def test_duplicate_columns_handled():
    import io as _io
    # Build a raw df with a manually duplicated column to trigger our dedupe logic
    df = pd.DataFrame({
        "fault_code": ["E001"],
        "timestamp": ["2024-01-01 10:00:00"],
        "message": ["Msg"],
    })
    # Manually inject a duplicate column at the DataFrame level
    df.insert(0, "fault_code", ["E001"], allow_duplicates=True)
    result, warnings = normalize(df)
    assert "fault_code" in result.columns
    assert any("Duplicate" in w for w in warnings)


def test_column_type_enforcement(base_df):
    base_df["fault_code"] = [123, 456]  # int, should be coerced to str-like
    df, _ = normalize(base_df)
    # pandas 2.x may use StringDtype instead of object — both are string-compatible
    assert str(df["fault_code"].dtype) in ("object", "string") or hasattr(df["fault_code"].dtype, "na_value")
