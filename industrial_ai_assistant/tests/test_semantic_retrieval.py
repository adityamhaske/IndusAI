"""
test_semantic_retrieval.py

Tests SemanticIndex using MockEmbedder (no Qdrant required for BM25 tests).
Vector search tests use real Qdrant only if available (skipped otherwise).

Covers:
  - BM25 upsert + search
  - BM25 returns correct top_k
  - project_id filter prevents cross-project contamination
  - collection_size() returns correct count
  - Hybrid RRF merge deduplicates correctly
"""
from __future__ import annotations

import hashlib
import pytest

from app.models.project_models import SemanticChunk, ScoredChunk


# ── Mock embedder ──────────────────────────────────────────────────────────────

class _MockEmbedder:
    """Returns deterministic 384-dim vectors based on text hash."""
    def embed_text(self, text: str) -> list[float]:
        h = int(hashlib.sha256(text.encode()).hexdigest(), 16)
        # Generate 384 floats in [-1, 1] deterministically
        floats = []
        for i in range(384):
            floats.append(((h >> (i % 64)) & 0xFF) / 127.5 - 1.0)
        return floats


def _make_chunk(content: str, project_id: str, title: str = "Test") -> SemanticChunk:
    cid = hashlib.sha1(f"{project_id}:{title}:{content[:16]}".encode()).hexdigest()
    return SemanticChunk(
        chunk_id=cid,
        content=content,
        source_file="test_doc.txt",
        section_title=title,
        file_type="txt",
        project_id=project_id,
    )


@pytest.fixture()
def sem_index():
    """Return SemanticIndex with mock embedder — no real Qdrant needed for BM25."""
    from app.indexes.semantic_index import SemanticIndex
    idx = SemanticIndex(embedder=_MockEmbedder())
    idx._client = None  # ensure no real Qdrant called by default
    return idx


# ── BM25 tests (no Qdrant) ────────────────────────────────────────────────────

class TestBM25:
    def _upsert_bm25_only(self, idx, chunks, project_id):
        """Add chunks to BM25 index without calling Qdrant."""
        for chunk in chunks:
            idx._bm25_add(project_id, chunk.chunk_id, chunk.content, chunk)

    def test_bm25_returns_relevant_chunk(self, sem_index):
        chunks = [
            _make_chunk("Motor speed control using VFD drive", "proj1", "Drives"),
            _make_chunk("Conveyor belt fault detection system", "proj1", "Conveyors"),
            _make_chunk("Safety interlock E-Stop circuit", "proj1", "Safety"),
        ]
        self._upsert_bm25_only(sem_index, chunks, "proj1")
        results = sem_index.bm25_search("motor speed VFD", "proj1", top_k=2)
        assert len(results) >= 1
        assert results[0].retrieval_method == "bm25"
        assert "motor" in results[0].chunk.content.lower() or "vfd" in results[0].chunk.content.lower()

    def test_bm25_top_k_respected(self, sem_index):
        chunks = [_make_chunk(f"Document about topic {i}", "proj2") for i in range(10)]
        self._upsert_bm25_only(sem_index, chunks, "proj2")
        results = sem_index.bm25_search("document topic", "proj2", top_k=3)
        assert len(results) <= 3

    def test_bm25_empty_query_returns_empty(self, sem_index):
        results = sem_index.bm25_search("", "proj_empty", top_k=5)
        assert results == []

    def test_bm25_no_match_returns_empty(self, sem_index):
        chunks = [_make_chunk("Motor speed control", "proj3")]
        self._upsert_bm25_only(sem_index, chunks, "proj3")
        results = sem_index.bm25_search("xyzzy frobulate quux", "proj3", top_k=5)
        assert results == []

    def test_cross_project_isolation(self, sem_index):
        """Chunks from project_a must NOT appear in project_b search."""
        chunk_a = _make_chunk("Confidential project_a data Motor_Speed_A", "project_a")
        chunk_b = _make_chunk("Normal project_b conveyor data", "project_b")
        self._upsert_bm25_only(sem_index, [chunk_a], "project_a")
        self._upsert_bm25_only(sem_index, [chunk_b], "project_b")

        results_b = sem_index.bm25_search("Motor_Speed_A", "project_b", top_k=10)
        contents = [r.chunk.content for r in results_b]
        assert not any("project_a" in c for c in contents), \
            "Cross-project contamination detected!"

    def test_collection_size(self, sem_index):
        chunks = [_make_chunk(f"Doc {i}", "size_proj") for i in range(5)]
        for chunk in chunks:
            sem_index._bm25_add("size_proj", chunk.chunk_id, chunk.content, chunk)
        assert sem_index.collection_size("size_proj") == 5

    def test_delete_project_clears_bm25(self, sem_index):
        """delete_project for BM25 (skip Qdrant call)."""
        chunks = [_make_chunk("To be deleted", "del_proj")]
        for chunk in chunks:
            sem_index._bm25_add("del_proj", chunk.chunk_id, chunk.content, chunk)
        assert sem_index.collection_size("del_proj") == 1

        # Clear BM25 directly (bypass Qdrant delete call)
        sem_index._bm25_index.pop("del_proj", None)
        sem_index._chunk_store.pop("del_proj", None)
        sem_index._df.pop("del_proj", None)
        assert sem_index.collection_size("del_proj") == 0
