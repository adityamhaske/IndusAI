"""
Tests for SemanticIndex project isolation and basic retrieval.

Uses an in-memory mock to avoid needing a live Qdrant instance.
"""
from __future__ import annotations

import pytest
from typing import List, Dict, Any

from app.core.schemas import ChunkMetadata, DocumentChunk
from app.indexes.semantic_index import SemanticIndex


# ── In-memory Qdrant mock ─────────────────────────────────────────────────────

class _InMemoryQdrantClient:
    """
    Minimal mock of QdrantClient that stores points in memory
    and supports project_id filtering.
    """

    def __init__(self):
        self._points: Dict[int, dict] = {}

    def upsert(self, collection_name, points):
        for p in points:
            self._points[p.id] = {
                "id": p.id,
                "vector": p.vector,
                "payload": p.payload,
            }

    def search(self, collection_name, query_vector, limit, query_filter, with_payload):
        # Apply project_id filter from Qdrant filter structure
        project_id = _extract_project_filter(query_filter)
        results = []
        for pid, point in self._points.items():
            meta = point["payload"].get("metadata", {})
            if project_id and meta.get("project_id") != project_id:
                continue
            results.append(_FakeHit(pid, point["payload"]))
        # No real similarity ranking in mock — just return first `limit` results
        return results[:limit]

    def delete(self, collection_name, points_selector):
        # Extract project_id from filter selector and delete matching
        project_id = _extract_project_filter(points_selector.filter)
        to_delete = [
            pid for pid, pt in self._points.items()
            if pt["payload"].get("metadata", {}).get("project_id") == project_id
        ]
        for pid in to_delete:
            del self._points[pid]


class _FakeHit:
    def __init__(self, id_, payload):
        self.id = id_
        self.payload = payload


def _extract_project_filter(qdrant_filter) -> str | None:
    """Pull project_id value from a Qdrant Filter object."""
    try:
        must = qdrant_filter.must
        if must:
            cond = must[0]
            return cond.match.value
    except Exception:
        pass
    return None


class _MockEmbedder:
    """Returns a fixed-length dummy embedding (no model needed)."""
    def embed_text(self, text: str) -> List[float]:
        return [0.1] * 384

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [[0.1] * 384 for _ in texts]


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_index():
    client = _InMemoryQdrantClient()
    embedder = _MockEmbedder()
    return SemanticIndex(
        qdrant_client=client,
        collection_name="test_coll",
        embedder=embedder,
    )


def _make_chunk(content: str, source: str, project_id: str, title: str = "") -> DocumentChunk:
    import hashlib
    cid = hashlib.md5(f"{source}:{content[:20]}".encode()).hexdigest()[:12]
    return DocumentChunk(
        content=content,
        metadata=ChunkMetadata(
            source_file=source,
            section_title=title or source,
            chunk_id=cid,
            project_id=project_id,
        ),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_index_and_retrieve_basic():
    idx = _make_index()
    chunk = _make_chunk("CONV_RUN controls the conveyor belt", "manual.pdf", "proj_a")
    n = idx.index_chunks("proj_a", [chunk])
    assert n == 1


def test_search_returns_indexed_chunk():
    idx = _make_index()
    chunk = _make_chunk("Pump speed is controlled by PUMP_SPD tag", "io_list.txt", "proj_a")
    idx.index_chunks("proj_a", [chunk])
    results = idx.search("proj_a", "pump speed")
    assert len(results) == 1
    assert "PUMP_SPD" in results[0].content


def test_cross_project_isolation():
    """Chunks from project_b must NOT appear in project_a searches."""
    idx = _make_index()
    chunk_a = _make_chunk("Project A tag: CONV_RUN", "a.pdf", "proj_a")
    chunk_b = _make_chunk("Project B tag: DRIVE_CMD", "b.pdf", "proj_b")
    idx.index_chunks("proj_a", [chunk_a])
    idx.index_chunks("proj_b", [chunk_b])

    results_a = idx.search("proj_a", "tag")
    sources_a = {r.metadata.project_id for r in results_a}
    assert "proj_b" not in sources_a


def test_project_b_not_in_project_a_results_and_vice_versa():
    idx = _make_index()
    for i in range(3):
        idx.index_chunks("proj_x", [_make_chunk(f"X content {i}", f"x_{i}.txt", "proj_x")])
    for i in range(3):
        idx.index_chunks("proj_y", [_make_chunk(f"Y content {i}", f"y_{i}.txt", "proj_y")])

    x_results = idx.search("proj_x", "content")
    y_results = idx.search("proj_y", "content")

    assert all(r.metadata.project_id == "proj_x" for r in x_results)
    assert all(r.metadata.project_id == "proj_y" for r in y_results)


def test_delete_project_removes_chunks():
    idx = _make_index()
    idx.index_chunks("proj_del", [_make_chunk("sensitive data", "secret.pdf", "proj_del")])
    # Verify present
    assert len(idx.search("proj_del", "sensitive")) == 1
    # Delete
    idx.delete_project("proj_del")
    # Verify gone
    assert len(idx.search("proj_del", "sensitive")) == 0


def test_empty_project_search_returns_empty():
    idx = _make_index()
    results = idx.search("proj_empty", "any query")
    assert results == []


def test_chunk_metadata_preserved_after_retrieval():
    idx = _make_index()
    chunk = _make_chunk("Commissioning note: drives tested", "commissioning.pdf", "proj_meta", "Section 3")
    idx.index_chunks("proj_meta", [chunk])
    results = idx.search("proj_meta", "drives")
    assert results[0].metadata.source_file == "commissioning.pdf"
    assert results[0].metadata.project_id == "proj_meta"
