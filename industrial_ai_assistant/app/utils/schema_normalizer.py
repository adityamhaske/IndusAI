"""
Schema Normalizer for PLC Fault CSV files.

Handles:
  - Column synonym mapping (20+ aliases)
  - Column type enforcement
  - UTC timestamp normalization (warns if naive)
  - Sort by timestamp ascending (guarantee for sliding window)
  - row_id injection
  - Structured error responses via FaultSchemaError

Complexity: O(n log n) due to sort step.
"""
import logging
from datetime import timezone, datetime
from typing import Tuple, List
import pandas as pd

from app.core.fault_exceptions import FaultSchemaError, FaultParsingError

logger = logging.getLogger(__name__)

# ── Column synonym mapping ────────────────────────────────────────────────────
COLUMN_MAP: dict[str, str] = {
    # fault_code
    "fault_code":  "fault_code",
    "error_code":  "fault_code",
    "code":        "fault_code",
    "alarm_code":  "fault_code",
    "error":       "fault_code",
    "fault":       "fault_code",
    "faultcode":   "fault_code",

    # timestamp
    "timestamp":   "timestamp",
    "time":        "timestamp",
    "date_time":   "timestamp",
    "datetime":    "timestamp",
    "event_time":  "timestamp",
    "occurred_at": "timestamp",
    "log_time":    "timestamp",
    "date":        "timestamp",

    # device
    "device":      "device",
    "tag":         "device",
    "source":      "device",
    "station":     "device",
    "plc":         "device",
    "unit":        "device",
    "asset":       "device",
    "machine":     "device",

    # message
    "message":     "message",
    "description": "message",
    "msg":         "message",
    "detail":      "message",
    "error_msg":   "message",
    "fault_desc":  "message",
    "text":        "message",

    # severity
    "severity":    "severity",
    "level":       "severity",
    "priority":    "severity",
    "alarm_level": "severity",
    "criticality": "severity",
}

REQUIRED_COLUMNS = {"fault_code", "timestamp", "message"}
OPTIONAL_COLUMNS = {"device": "UNKNOWN", "severity": None}


def normalize(df: pd.DataFrame, source_filename: str = "") -> Tuple[pd.DataFrame, List[str]]:
    """
    Normalize a raw CSV DataFrame into the canonical fault schema.

    Returns:
        (normalized_df, warnings)

    Raises:
        FaultSchemaError if required columns are missing or timestamps are unparseable.
    """
    warnings: List[str] = []

    # ── 1. Normalize column names ─────────────────────────────────────────────
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Check for duplicates BEFORE mapping
    dupes = [c for c in df.columns if list(df.columns).count(c) > 1]
    if dupes:
        warnings.append(f"Duplicate columns detected and dropped: {list(set(dupes))}")
        df = df.loc[:, ~df.columns.duplicated()]

    # Apply synonym map
    rename_map = {}
    for col in df.columns:
        if col in COLUMN_MAP:
            rename_map[col] = COLUMN_MAP[col]
    df = df.rename(columns=rename_map)

    # ── 2. Validate required columns ──────────────────────────────────────────
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise FaultSchemaError(
            f"Required columns missing: {sorted(missing)}",
            details={"missing": sorted(missing), "found": list(df.columns)}
        )

    # ── 3. Fill optional columns ──────────────────────────────────────────────
    for col, default in OPTIONAL_COLUMNS.items():
        if col not in df.columns:
            warnings.append(f"Optional column '{col}' not found — defaulting to '{default}'.")
            df[col] = default

    # ── 4. Type enforcement ───────────────────────────────────────────────────
    df["fault_code"] = df["fault_code"].astype(str).str.strip()
    df["device"]     = df["device"].fillna("UNKNOWN").astype(str).str.strip()
    df["message"]    = df["message"].fillna("").astype(str).str.strip()
    df["severity"]   = df["severity"].astype(str).str.strip() if "severity" in df.columns else None

    # ── 5. Timestamp normalization → UTC ─────────────────────────────────────
    raw_ts = df["timestamp"]
    try:
        parsed = pd.to_datetime(raw_ts, utc=False, errors="coerce")
    except Exception as exc:
        raise FaultParsingError(f"Timestamp column could not be parsed: {exc}")

    unparseable_count = parsed.isna().sum()
    if unparseable_count > 0:
        warnings.append(f"{unparseable_count} rows had unparseable timestamps and were dropped.")
        df = df[~parsed.isna()].copy()
        parsed = parsed.dropna()

    # Detect mixed timezones or naive datetimes
    if hasattr(parsed.dt, "tz") and parsed.dt.tz is None:
        warnings.append(
            "Timestamps are timezone-naive — assuming UTC. "
            "(Install tzdata package to use local machine timezone.)"
        )
        parsed = parsed.dt.tz_localize("UTC")
    else:
        parsed = parsed.dt.tz_convert("UTC")

    df["timestamp"] = parsed

    # ── 6. Drop NaT rows ─────────────────────────────────────────────────────
    df = df.dropna(subset=["timestamp"])

    # ── 7. Sort by timestamp ascending (REQUIRED before row_id assignment) ───
    df = df.sort_values("timestamp", ascending=True).reset_index(drop=True)

    # ── 8. Inject deterministic row_id ───────────────────────────────────────
    df.insert(0, "row_id", range(len(df)))

    # ── 9. Keep only canonical columns ───────────────────────────────────────
    keep = ["row_id", "fault_code", "timestamp", "device", "message", "severity"]
    df = df[keep]

    logger.info(
        "Schema normalization complete: %d rows, %d warnings. Source: %s",
        len(df), len(warnings), source_filename
    )
    return df, warnings
