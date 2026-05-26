"""
FaultService — Core singleton managing the active in-memory PLC fault dataset.

Design decisions:
  - MAX_DATASETS = 1: single active dataset per server instance (v1).
  - threading.RLock protects all store mutations (upload, reset, analyze).
  - On new upload: previous DataFrame is explicitly deleted + gc.collect() runs.
  - Sampling: if rows > SAMPLE_LIMIT, keep first SAMPLE_LIMIT sorted by timestamp.
  - Stats are built ONCE at upload time and cached in FaultDataset.stats_cache.
  - LLM is never given raw CSV data — only pre-computed statistics.
"""
import gc
import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import pandas as pd

from app.core.fault_exceptions import (
    DatasetNotLoadedError,
    FaultRowNotFoundError,
    AnalysisPrerequisiteError,
    FaultTooLargeError,
    FaultParsingError,
)
from app.models.fault_models import (
    FaultRecord, FaultListResponse, FaultSummaryResponse,
    FaultDetailResponse, FaultAnalysisResponse, FaultMetricsResponse,
)
from app.utils.fault_statistics import (
    build_stats_cache,
    compute_occurrences_in_window,
    compute_cooccurrence,
    compute_previous_occurrences,
    _timestamps_for_code,
)
from app.utils.fault_confidence import compute_confidence

logger = logging.getLogger(__name__)

MAX_ROWS: int = 250_000
SAMPLE_LIMIT: int = 200_000
MAX_FILE_SIZE_MB: float = 50.0
MAX_DATASETS: int = 1  # v1: single active dataset only


@dataclass
class FaultDataset:
    dataframe: pd.DataFrame
    created_at: datetime
    source_filename: str
    dataset_hash: str
    stats_cache: Dict[str, Any]
    parse_duration_ms: float
    stats_duration_ms: float
    memory_mb: float = 0.0


class FaultService:
    """Singleton service for PLC fault log management."""

    _instance: Optional["FaultService"] = None
    _singleton_lock = threading.Lock()

    def __new__(cls):
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._store: Dict[str, FaultDataset] = {}
        self._lock = threading.RLock()
        self._initialized = True
        try:
            from app.core.firebase import get_firestore_client
            self.db = get_firestore_client()
            self.collection = self.db.collection("fault_sessions")
            self._use_firestore = True
        except Exception as e:
            logger.warning(f"Firestore unavailable: {e}")
            self._use_firestore = False

    # ── Internal helpers ──────────────────────────────────────────────────────

    def store_session(self, session_id: str, stats: Dict[str, Any]):
        """Store computed fault stats for a session in Firestore."""
        if self._use_firestore:
            from firebase_admin import firestore
            self.collection.document(session_id).set({
                "stats": stats,
                "created_at": firestore.SERVER_TIMESTAMP
            })

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """Retrieve fault stats for a session from Firestore."""
        if not self._use_firestore:
            raise ValueError("Firestore not configured")
        doc = self.collection.document(session_id).get()
        if not doc.exists:
            raise ValueError(f"Session {session_id} not found")
        return doc.to_dict().get("stats", {})

    def delete_session(self, session_id: str):
        """Clean up session data from Firestore."""
        if self._use_firestore:
            self.collection.document(session_id).delete()

    def _require_dataset(self, project_id: str) -> FaultDataset:
        ds = self._store.get(project_id)
        if ds is None:
            raise DatasetNotLoadedError()
        return ds

    def _compute_memory(self, df: pd.DataFrame) -> float:
        return df.memory_usage(deep=True).sum() / (1024 ** 2)

    def _hash_bytes(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _row_to_record(self, row: pd.Series) -> FaultRecord:
        return FaultRecord(
            row_id=int(row["row_id"]),
            fault_code=str(row["fault_code"]),
            timestamp=row["timestamp"].to_pydatetime(),
            device=str(row["device"]),
            message=str(row["message"]),
            severity=str(row["severity"]) if pd.notna(row.get("severity")) else None,
        )

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload(
        self,
        df: pd.DataFrame,
        source_filename: str,
        raw_bytes: bytes,
        project_id: str = "default",
        warnings: List[str] = None,
    ) -> Dict[str, Any]:
        """Store normalized DataFrame. Enforces MAX_DATASETS, sampling, and GC."""
        warnings = warnings or []
        t0_parse = time.perf_counter()

        with self._lock:
            # Enforce MAX_DATASETS
            if len(self._store) >= MAX_DATASETS and project_id not in self._store:
                raise FaultTooLargeError(
                    f"Only {MAX_DATASETS} dataset(s) supported per server instance. "
                    "Please reset the current dataset before uploading a new one."
                )

            # Sample if too large
            sampled = False
            if len(df) > MAX_ROWS:
                raise FaultTooLargeError(
                    f"Dataset has {len(df):,} rows which exceeds the hard limit of {MAX_ROWS:,}. "
                    "Please reduce the file size."
                )
            if len(df) > SAMPLE_LIMIT:
                sampled = True
                warnings.append(
                    f"Dataset has {len(df):,} rows. Keeping first {SAMPLE_LIMIT:,} rows "
                    "(sorted by timestamp) for performance."
                )
                df = df.head(SAMPLE_LIMIT).copy()

            # Clear previous dataset (GC)
            if project_id in self._store:
                old_mb = self._store[project_id].memory_mb
                del self._store[project_id]
                gc.collect()
                logger.info("Cleared previous dataset (%.1f MB). GC completed.", old_mb)

            parse_dur = (time.perf_counter() - t0_parse) * 1000

            # Build stats cache
            t0_stats = time.perf_counter()
            stats_cache = build_stats_cache(df)
            stats_dur = (time.perf_counter() - t0_stats) * 1000

            dataset_hash = self._hash_bytes(raw_bytes)
            mem_mb = self._compute_memory(df)

            self._store[project_id] = FaultDataset(
                dataframe=df,
                created_at=datetime.now(tz=timezone.utc),
                source_filename=source_filename,
                dataset_hash=dataset_hash,
                stats_cache=stats_cache,
                parse_duration_ms=parse_dur,
                stats_duration_ms=stats_dur,
                memory_mb=mem_mb,
            )

            logger.info(
                "Dataset uploaded: %s | rows=%d | hash=%s | mem=%.1fMB | parse=%.0fms | stats=%.0fms",
                source_filename, len(df), dataset_hash[:8], mem_mb, parse_dur, stats_dur,
            )

            preview = df.head(10).assign(
                timestamp=df["timestamp"].head(10).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            ).to_dict(orient="records")

            return {
                "total_rows": len(df),
                "sampled": sampled,
                "sample_limit": SAMPLE_LIMIT if sampled else None,
                "columns": list(df.columns),
                "preview": preview,
                "source_filename": source_filename,
                "dataset_hash": dataset_hash,
                "parse_duration_ms": round(parse_dur, 1),
                "stats_duration_ms": round(stats_dur, 1),
                "warnings": warnings,
            }

    # ── Paginated list ────────────────────────────────────────────────────────

    def get_page(self, project_id: str, page: int, size: int) -> FaultListResponse:
        with self._lock:
            ds = self._require_dataset(project_id)
            df = ds.dataframe
            total = len(df)
            total_pages = max(1, (total + size - 1) // size)
            page = max(1, min(page, total_pages))
            start = (page - 1) * size
            end = min(start + size, total)
            slice_df = df.iloc[start:end].copy()
            slice_df["timestamp"] = slice_df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            return FaultListResponse(
                total_rows=total,
                page=page,
                size=size,
                total_pages=total_pages,
                rows=slice_df.to_dict(orient="records"),
            )

    # ── Summary ───────────────────────────────────────────────────────────────

    def get_summary(self, project_id: str) -> FaultSummaryResponse:
        with self._lock:
            ds = self._require_dataset(project_id)
            c = ds.stats_cache
            freq = c["frequency_dict"]
            most_common = max(freq, key=freq.get) if freq else ""
            return FaultSummaryResponse(
                total_rows=len(ds.dataframe),
                unique_fault_codes=len(freq),
                most_common_fault=most_common,
                most_common_count=freq.get(most_common, 0),
                time_range_start=c["time_start"],
                time_range_end=c["time_end"],
                top_devices=c["top_devices"],
                fault_frequency_per_hour=c["hourly_counts"],
                burst_detected=c["burst_detected"],
                max_burst_window_description=c["burst_description"],
                dataset_hash=ds.dataset_hash,
            )

    # ── Detail ────────────────────────────────────────────────────────────────

    def get_detail(self, project_id: str, row_id: int) -> FaultDetailResponse:
        with self._lock:
            ds = self._require_dataset(project_id)
            df = ds.dataframe
            matches = df[df["row_id"] == row_id]
            if matches.empty:
                raise FaultRowNotFoundError(row_id)

            row = matches.iloc[0]
            record = self._row_to_record(row)
            ref_ts = record.timestamp
            fault_code = record.fault_code

            ts_list = _timestamps_for_code(df, fault_code)
            occ_1h = compute_occurrences_in_window(ts_list, ref_ts, hours=1)
            occ_24h = compute_occurrences_in_window(ts_list, ref_ts, hours=24)

            prev_df = compute_previous_occurrences(df, fault_code, ref_ts, limit=10)
            prev_records = [self._row_to_record(r) for _, r in prev_df.iterrows()]

            co_fault, co_count = compute_cooccurrence(df, ref_ts)

            return FaultDetailResponse(
                row=record,
                occurrences_last_hour=occ_1h,
                occurrences_last_24h=occ_24h,
                previous_occurrences=prev_records,
                top_cooccurring_fault=co_fault,
                cooccurrence_count=co_count,
            )

    # ── Analyze ───────────────────────────────────────────────────────────────

    def analyze(self, project_id: str, row_id: int, llm, dataset_hash: str) -> FaultAnalysisResponse:
        """Run deterministic stats → build LLM prompt → return structured response."""
        with self._lock:
            ds = self._require_dataset(project_id)

            # LLM safety guards
            if ds.dataset_hash != dataset_hash:
                from app.core.fault_exceptions import DatasetHashMismatchError
                raise DatasetHashMismatchError()

            df = ds.dataframe
            matches = df[df["row_id"] == row_id]
            if matches.empty:
                raise FaultRowNotFoundError(row_id)

            if not ds.stats_cache:
                raise AnalysisPrerequisiteError("Stats cache is empty.")

            row = matches.iloc[0]
            record = self._row_to_record(row)
            ref_ts = record.timestamp

            ts_list = _timestamps_for_code(df, record.fault_code)
            occ_1h = compute_occurrences_in_window(ts_list, ref_ts, hours=1)
            occ_24h = compute_occurrences_in_window(ts_list, ref_ts, hours=24)
            co_fault, co_count = compute_cooccurrence(df, ref_ts)
            burst = ds.stats_cache.get("burst_detected", False)
            burst_desc = ds.stats_cache.get("burst_description", "")
            confidence = compute_confidence(
                burst_detected=burst,
                anomaly_score=1.0,
                integrity_passed=True,
                occurrences_1h=occ_1h
            )

            prompt = _build_analysis_prompt(record, occ_1h, occ_24h, co_fault, burst_desc)

        # LLM call outside lock (may be slow)
        t0 = time.perf_counter()
        try:
            raw_response = llm.generate(prompt)
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            raw_response = f"LLM unavailable: {exc}"
        llm_ms = (time.perf_counter() - t0) * 1000

        structured = _parse_llm_response(raw_response, record)

        return FaultAnalysisResponse(
            analysis_version="v1.0",
            dataset_hash=ds.dataset_hash,
            row_id=row_id,
            fault_code=record.fault_code,
            device=record.device,
            timestamp=record.timestamp,
            confidence=confidence,
            summary=structured.get("summary", raw_response[:300]),
            likely_causes=structured.get("likely_causes", []),
            resolution_steps=structured.get("resolution_steps", []),
            related_tags=structured.get("related_tags", [record.fault_code]),
            limitations=structured.get("limitations"),
            statistics={
                "occurrences_last_hour": occ_1h,
                "occurrences_last_24h": occ_24h,
                "top_cooccurring_fault": co_fault,
                "cooccurrence_count": co_count,
                "burst_detected": burst,
                "burst_description": burst_desc,
            },
            llm_duration_ms=round(llm_ms, 1),
        )

    # ── Reset ─────────────────────────────────────────────────────────────────

    def reset(self, project_id: str) -> Dict[str, str]:
        with self._lock:
            if project_id in self._store:
                mb = self._store[project_id].memory_mb
                del self._store[project_id]
                gc.collect()
                logger.info("Dataset reset for project '%s'. Freed ~%.1f MB.", project_id, mb)
                return {"status": "cleared", "freed_mb": round(mb, 1)}
            return {"status": "no_dataset"}

    # ── Metrics ───────────────────────────────────────────────────────────────

    def get_metrics(self, project_id: str) -> FaultMetricsResponse:
        with self._lock:
            ds = self._store.get(project_id)
            if ds is None:
                return FaultMetricsResponse(dataset_loaded=False, row_count=0, memory_mb=0.0)
            return FaultMetricsResponse(
                dataset_loaded=True,
                row_count=len(ds.dataframe),
                memory_mb=round(ds.memory_mb, 2),
                source_filename=ds.source_filename,
                created_at=ds.created_at,
                parse_duration_ms=ds.parse_duration_ms,
                stats_duration_ms=ds.stats_duration_ms,
                dataset_hash=ds.dataset_hash,
            )


# ── LLM prompt builder ────────────────────────────────────────────────────────

def _build_analysis_prompt(record: FaultRecord, occ_1h: int, occ_24h: int,
                            co_fault: Optional[str], burst_desc: Optional[str]) -> str:
    return f"""You are a PLC commissioning assistant. Analyze this fault and provide a structured response.

FAULT DETAILS:
  Code: {record.fault_code}
  Device: {record.device}
  Timestamp: {record.timestamp.isoformat()}
  Severity: {record.severity or "Unknown"}
  Message: {record.message}

STATISTICS (pre-computed, deterministic):
  Occurrences last hour: {occ_1h}
  Occurrences last 24 hours: {occ_24h}
  Top co-occurring fault: {co_fault or "None"}
  Burst detected: {"Yes — " + burst_desc if burst_desc else "No"}

Respond ONLY with a JSON object matching this schema:
{{
  "summary": "...",
  "likely_causes": ["...", "..."],
  "resolution_steps": [{{"title": "...", "description": "..."}}],
  "related_tags": ["..."],
  "limitations": "..."
}}
"""


def _parse_llm_response(raw: str, record: FaultRecord) -> Dict[str, Any]:
    """Best-effort JSON parse of LLM output. Falls back to minimal structure."""
    import json, re
    try:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return {
        "summary": raw[:500],
        "likely_causes": ["Unable to parse structured response from LLM."],
        "resolution_steps": [],
        "related_tags": [record.fault_code],
        "limitations": "LLM response could not be parsed into structured format.",
    }


# ── Module-level singleton accessor ──────────────────────────────────────────
_fault_service: Optional[FaultService] = None

def get_fault_service() -> FaultService:
    global _fault_service
    if _fault_service is None:
        _fault_service = FaultService()
    return _fault_service
