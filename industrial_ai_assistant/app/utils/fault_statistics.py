"""
Fault Statistics Engine — separated for modularity and testability.
All functions operate on a pre-sorted (by timestamp) DataFrame.
All results are computed once at upload time and cached in FaultDataset.stats_cache.

Complexity Summary:
  compute_hourly_counts:       O(n)
  compute_daily_counts:        O(n)
  compute_top_faults:          O(n)
  compute_fault_frequency:     O(n)
  compute_occurrences_last_Xh: O(log n) via bisect
  compute_cooccurrence:        O(n log n) — sort + sliding window
  compute_fault_burst:         O(n)
"""
import bisect
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


# ── Time-series helpers ───────────────────────────────────────────────────────

def _timestamps_for_code(df: pd.DataFrame, fault_code: str) -> List[datetime]:
    """Return sorted list of datetime objects for a given fault_code. O(n)."""
    series = df.loc[df["fault_code"] == fault_code, "timestamp"]
    return series.dt.to_pydatetime().tolist()


def compute_hourly_counts(df: pd.DataFrame) -> Dict[str, int]:
    """Fault counts grouped by hour-of-day string 'HH:00'. O(n)."""
    if df.empty:
        return {}
    hourly = df["timestamp"].dt.hour.value_counts().sort_index()
    return {f"{h:02d}:00": int(c) for h, c in hourly.items()}


def compute_daily_counts(df: pd.DataFrame) -> Dict[str, int]:
    """Fault counts grouped by date string 'YYYY-MM-DD'. O(n)."""
    if df.empty:
        return {}
    daily = df["timestamp"].dt.date.value_counts().sort_index()
    return {str(d): int(c) for d, c in daily.items()}


def compute_top_faults(df: pd.DataFrame, n: int = 5) -> List[Dict]:
    """Top-n most common fault codes. O(n)."""
    if df.empty:
        return []
    counts = df["fault_code"].value_counts().head(n)
    return [{"fault_code": code, "count": int(cnt)} for code, cnt in counts.items()]


def compute_fault_frequency(df: pd.DataFrame) -> Dict[str, int]:
    """Complete fault_code → count dict. O(n). Cached for O(1) lookup."""
    if df.empty:
        return {}
    return df["fault_code"].value_counts().to_dict()


def compute_top_devices(df: pd.DataFrame, n: int = 5) -> List[Dict]:
    """Top-n devices by fault count. O(n)."""
    if df.empty:
        return []
    counts = df["device"].value_counts().head(n)
    return [{"device": dev, "count": int(cnt)} for dev, cnt in counts.items()]


# ── Per-fault time-window queries ─────────────────────────────────────────────

def compute_occurrences_in_window(
    timestamps: List[datetime], reference_ts: datetime, hours: int
) -> int:
    """
    Count occurrences of same fault within a trailing time window.
    Uses binary search (bisect) for O(log n).
    timestamps must be sorted ascending.
    """
    if not timestamps:
        return 0
    window_start = reference_ts - timedelta(hours=hours)
    lo = bisect.bisect_left(timestamps, window_start)
    hi = bisect.bisect_right(timestamps, reference_ts)
    return max(0, hi - lo - 1)  # exclude self


# ── Co-occurrence (different fault codes, ±5 min window) ─────────────────────

def compute_cooccurrence(
    df: pd.DataFrame, reference_ts: datetime, window_min: int = 5
) -> Tuple[Optional[str], int]:
    """
    Find the most common *different* fault code within ±window_min minutes
    of reference_ts using a sliding window on sorted timestamps.

    Algorithm: O(n log n) — DataFrame already sorted; use searchsorted.
    Definition: other fault codes occurring in [reference_ts - W, reference_ts + W].
    """
    delta = timedelta(minutes=window_min)
    lo_ts = reference_ts - delta
    hi_ts = reference_ts + delta

    ts_array = df["timestamp"].values
    lo_idx = df["timestamp"].searchsorted(pd.Timestamp(lo_ts))
    hi_idx = df["timestamp"].searchsorted(pd.Timestamp(hi_ts), side="right")

    window_df = df.iloc[lo_idx:hi_idx]
    # Exclude the reference fault code itself
    ref_row = df[df["timestamp"] == pd.Timestamp(reference_ts)]
    ref_code = ref_row["fault_code"].iloc[0] if not ref_row.empty else None

    others = window_df[window_df["fault_code"] != ref_code]["fault_code"]
    if others.empty:
        return None, 0
    top = others.value_counts().idxmax()
    return str(top), int(others.value_counts().max())


# ── Previous occurrences ──────────────────────────────────────────────────────

def compute_previous_occurrences(
    df: pd.DataFrame, fault_code: str, reference_ts: datetime, limit: int = 10
) -> pd.DataFrame:
    """Return up to `limit` rows of same fault_code before reference_ts. O(n)."""
    mask = (df["fault_code"] == fault_code) & (df["timestamp"] < pd.Timestamp(reference_ts))
    return df[mask].tail(limit)


# ── Burst detection ───────────────────────────────────────────────────────────

def compute_fault_burst(
    df: pd.DataFrame, threshold: int = 5, window_min: int = 10
) -> Tuple[bool, Optional[str]]:
    """
    Detect fault bursts: >= threshold occurrences in any rolling window_min window.
    Sliding window over sorted timestamps. O(n).

    Returns:
        (burst_detected: bool, description: str | None)
        e.g. (True, "7 faults in 8 minutes")
    """
    if len(df) < threshold:
        return False, None

    timestamps = df["timestamp"].dt.to_pydatetime().tolist()
    window = timedelta(minutes=window_min)
    max_count = 0
    max_duration_min = 0.0
    left = 0

    for right in range(len(timestamps)):
        while timestamps[right] - timestamps[left] > window:
            left += 1
        count = right - left + 1
        if count > max_count:
            max_count = count
            duration_s = (timestamps[right] - timestamps[left]).total_seconds()
            max_duration_min = duration_s / 60.0

    burst = max_count >= threshold
    description = (
        f"{max_count} faults in {max_duration_min:.1f} minutes" if burst else None
    )
    return burst, description


# ── Pre-compute all stats (called once at upload) ─────────────────────────────

def build_stats_cache(df: pd.DataFrame) -> Dict:
    """
    Compute and cache all statistics once at upload time.
    Subsequent requests read from cache — no recomputation.
    """
    logger.info("Building stats cache for %d rows…", len(df))

    burst_detected, burst_desc = compute_fault_burst(df)

    cache = {
        "hourly_counts":      compute_hourly_counts(df),
        "daily_counts":       compute_daily_counts(df),
        "frequency_dict":     compute_fault_frequency(df),
        "top_faults":         compute_top_faults(df),
        "top_devices":        compute_top_devices(df),
        "burst_detected":     burst_detected,
        "burst_description":  burst_desc,
        "time_start":         df["timestamp"].min() if not df.empty else None,
        "time_end":           df["timestamp"].max() if not df.empty else None,
    }
    logger.info("Stats cache built. Burst: %s", burst_detected)
    return cache
