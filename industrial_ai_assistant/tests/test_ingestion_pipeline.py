"""
tests/test_ingestion_pipeline.py

Validates that ProjectIngestionPipeline processes files from storage.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

@pytest.fixture(autouse=True)
def mock_embedder(monkeypatch):
    def mock_embed(text):
        return [0.1] * 768
    monkeypatch.setattr("app.embeddings.gemini_embedder.GeminiEmbedder.embed_text", lambda self, t: mock_embed(t))
    monkeypatch.setattr("app.embeddings.gemini_embedder.GeminiEmbedder.embed_batch", lambda self, t: [[0.1] * 768 for _ in t])

@pytest.fixture(autouse=True)
def mock_encryption(monkeypatch):
    monkeypatch.setattr("app.services.user_settings_service.decrypt", lambda x: x)

@pytest.fixture(autouse=True)
def mock_infrastructure(monkeypatch):
    from app.config.dependency_injection import get_container
    get_container.cache_clear()
    monkeypatch.setattr("app.config.settings.settings.QDRANT_URL", "http://mock-qdrant:6333")
    monkeypatch.setattr("app.config.settings.settings.QDRANT_API_KEY", "mock-key")
    with patch("app.config.dependency_injection.QdrantStore") as mock_qdrant:
        mock_qdrant_instance = MagicMock()
        mock_qdrant.return_value = mock_qdrant_instance
        
        with patch("app.services.user_settings_service.get_firestore") as mock_get:
            mock_db = MagicMock()
            mock_db.get_document = MagicMock(return_value={
                "llm_provider": "gemini",
                "embedding_provider": "gemini",
                "llm_api_key_enc": "<test-encrypted-key>",
                "embedding_api_key_enc": "<test-encrypted-key>",
                "ollama_url": None
            })
            mock_get.return_value = mock_db
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            original_run = loop.run_in_executor
            async def mock_run_in_executor(executor, func, *args):
                return func(*args)
            monkeypatch.setattr(asyncio.get_event_loop(), "run_in_executor", mock_run_in_executor)
            
            with patch("app.services.project_ingestion_pipeline.get_storage_bucket") as mock_bucket:
                bucket = MagicMock()
                def mock_blob(path):
                    b = MagicMock()
                    b.download_as_bytes.return_value = b"Synthetic file content for testing"
                    return b
                bucket.blob = mock_blob
                mock_bucket.return_value = bucket
                yield mock_get

def _run(coro):
    """Run a coroutine in a new asyncio event loop (test isolation)."""
    return asyncio.get_event_loop().run_until_complete(coro)

class TestIngestionPipelineBasic:
    def test_no_name_error_on_ingest(self):
        from app.services.project_ingestion_pipeline import get_ingestion_pipeline
        pipeline = get_ingestion_pipeline()
        result = _run(pipeline.ingest(["doc_1.txt"], "test_pipeline_basic", "test_uid"))
        assert result is not None, "ingest() returned None"

    def test_all_five_files_indexed(self):
        from app.services.project_ingestion_pipeline import get_ingestion_pipeline
        pipeline = get_ingestion_pipeline()
        paths = [f"doc_{i}.txt" for i in range(1, 6)]
        result = _run(pipeline.ingest(paths, "test_pipeline_count", "test_uid"))
        assert result.files_indexed == 5, f"Expected 5 files indexed, got {result.files_indexed}"
        assert result.files_failed == 0, f"Expected 0 failures, got: {result.errors}"

    def test_semantic_chunks_produced(self):
        from app.services.project_ingestion_pipeline import get_ingestion_pipeline
        pipeline = get_ingestion_pipeline()
        result = _run(pipeline.ingest(["doc_1.txt"], "test_pipeline_chunks", "test_uid"))
        assert result.semantic_chunks_indexed > 0, "Expected semantic chunks > 0"

    def test_error_boundary_on_bad_path(self):
        # We test that the pipeline handles exceptions inside blob download
        from app.services.project_ingestion_pipeline import get_ingestion_pipeline
        pipeline = get_ingestion_pipeline()
        
        with patch("app.services.project_ingestion_pipeline.get_storage_bucket") as mock_bucket:
            bucket = MagicMock()
            def mock_blob(path):
                b = MagicMock()
                b.download_as_bytes.side_effect = Exception("Storage error")
                return b
            bucket.blob = mock_blob
            mock_bucket.return_value = bucket
            
            result = _run(pipeline.ingest(["bad_path.txt"], "test_pipeline_badpath", "test_uid"))
            assert result.files_failed == 1
            assert len(result.errors) == 1
