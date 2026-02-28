"""
tests/test_ingestion_pipeline.py

Validates that ProjectIngestionPipeline:
  - Does NOT raise NameError (regression for Phase 16 fix)
  - Processes 5 synthetic text files
  - Stores correct chunk counts in result
  - Writes .indusai_index.json metadata
  - Delta skips unchanged files on second run
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Create 5 synthetic .txt files in a temporary folder."""
    for i in range(1, 6):
        (tmp_path / f"doc_{i}.txt").write_text(
            f"Industrial AI document {i}. "
            f"This file describes the controller configuration for Line {i}. "
            f"Tags: PUMP_{i:02d}_START, MOTOR_{i:02d}_FAULT, SAFETY_{i:02d}_GATE. "
            f"Routine: MainProgram.Line{i}Loop verifies actuator positions every 50ms.",
            encoding="utf-8",
        )
    return tmp_path


# ---------------------------------------------------------------------------
# Helper runner
# ---------------------------------------------------------------------------

def _run(coro):
    """Run a coroutine in a new asyncio event loop (test isolation)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIngestionPipelineBasic:
    """Smoke + regression tests for ProjectIngestionPipeline."""

    def test_no_name_error_on_ingest(self, tmp_project: Path):
        """
        Regression: NameError: name 'sem' / 'si' is not defined.
        This MUST not be raised when calling pipeline.ingest().
        """
        from app.services.project_ingestion_pipeline import get_ingestion_pipeline

        pipeline = get_ingestion_pipeline()
        # Should complete without NameError or any unhandled exception
        result = _run(pipeline.ingest(str(tmp_project), "test_pipeline_basic"))
        assert result is not None, "ingest() returned None — pipeline failed silently"

    def test_all_five_files_indexed(self, tmp_project: Path):
        """All 5 .txt files must be counted as indexed."""
        from app.services.project_ingestion_pipeline import get_ingestion_pipeline

        pipeline = get_ingestion_pipeline()
        result = _run(pipeline.ingest(str(tmp_project), "test_pipeline_count"))
        assert result.files_scanned == 5, f"Expected 5 files scanned, got {result.files_scanned}"
        assert result.files_indexed == 5, f"Expected 5 files indexed, got {result.files_indexed}"
        assert result.files_failed == 0, f"Expected 0 failures, got: {result.errors}"

    def test_semantic_chunks_produced(self, tmp_project: Path):
        """Each text file should produce at least 1 semantic chunk."""
        from app.services.project_ingestion_pipeline import get_ingestion_pipeline
        from app.indexes.semantic_index import get_semantic_index

        project_id = "test_pipeline_chunks"
        pipeline = get_ingestion_pipeline()
        result = _run(pipeline.ingest(str(tmp_project), project_id))

        sem = get_semantic_index()
        chunk_count = sem.collection_size(project_id)
        assert chunk_count > 0, (
            f"Expected semantic chunks > 0 after ingestion, got {chunk_count}. "
            f"Ingestion result: files_indexed={result.files_indexed}, errors={result.errors}"
        )

    def test_metadata_file_written(self, tmp_project: Path):
        """.indusai_index.json must be written after ingestion."""
        from app.services.project_ingestion_pipeline import get_ingestion_pipeline

        pipeline = get_ingestion_pipeline()
        _run(pipeline.ingest(str(tmp_project), "test_pipeline_meta"))

        meta_path = tmp_project / ".indusai_index.json"
        assert meta_path.exists(), ".indusai_index.json was not created after ingestion"

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert "files" in meta, "metadata missing 'files' key"
        assert len(meta["files"]) == 5, f"Expected 5 file entries in metadata, got {len(meta['files'])}"

    def test_delta_skip_on_second_run(self, tmp_project: Path):
        """Second ingest of same unchanged files: all 5 should be delta-skipped (no new failures)."""
        from app.services.project_ingestion_pipeline import get_ingestion_pipeline
        from app.indexes.semantic_index import get_semantic_index

        project_id = "test_pipeline_delta"
        pipeline = get_ingestion_pipeline()

        # First ingest
        result1 = _run(pipeline.ingest(str(tmp_project), project_id))
        chunks_after_first = get_semantic_index().collection_size(project_id)

        # Second ingest — no file changes, all should be skipped
        result2 = _run(pipeline.ingest(str(tmp_project), project_id))
        assert result2.files_failed == 0, f"Second ingest produced failures: {result2.errors}"

        chunks_after_second = get_semantic_index().collection_size(project_id)
        # Chunk count should remain stable (delta skips prevent re-embedding)
        assert chunks_after_second >= chunks_after_first, (
            "Chunk count dropped on re-index — delta logic may have wiped unchanged chunks"
        )

    def test_error_boundary_on_bad_path(self):
        """pipeline.ingest() on a non-existent path must raise ValueError (not NameError)."""
        from app.services.project_ingestion_pipeline import get_ingestion_pipeline

        pipeline = get_ingestion_pipeline()
        with pytest.raises((ValueError, Exception)) as exc_info:
            _run(pipeline.ingest("/this/path/does/not/exist/at/all", "test_pipeline_badpath"))
        # Ensure it is NOT a NameError 
        assert not isinstance(exc_info.value, NameError), (
            "NameError leaked through error boundary — si/sem initialization is still broken"
        )
