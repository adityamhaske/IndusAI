"""
Tests — SemanticIndex: upsert, BM25 search, cross-project isolation.
Qdrant is mocked; only the in-process BM25 layer is tested here.
"""
import pytest
from app.indexes.semantic_index import SemanticIndex
from app.models.project_models import SemanticChunk


@pytest.fixture
def sem():
    """SemanticIndex with no Qdrant (embedder=None → keyword-only mode)."""
    idx = SemanticIndex(qdrant_host="localhost", qdrant_port=6333, embedder=None)
    # Prevent Qdrant connection
    idx._qdrant = _QDRANT_DISABLED
    return idx


class _QdrantDisabled:
    """Stub that always returns empty results."""
    def search(self, *a, **kw):
        return []
    def upsert(self, *a, **kw):
        pass
    def get_collections(self):
        class _C:
            collections = []
        return _C()
    def delete(self, *a, **kw):
        pass


_QDRANT_DISABLED = _QdrantDisabled()

PROJ_A = "project_alpha"
PROJ_B = "project_beta"

CHUNKS_A = [
    SemanticChunk(chunk_id="a1", project_id=PROJ_A, content="Motor speed control in conveyor line 1",
                  source_file="plc_a.l5x", section_title="Conveyor1", file_type="l5x"),
    SemanticChunk(chunk_id="a2", project_id=PROJ_A, content="Safety interlock for pallet lift station",
                  source_file="safety.pdf", section_title="Safety", file_type="pdf"),
    SemanticChunk(chunk_id="a3", project_id=PROJ_A, content="RIO rack configuration slot assignments",
                  source_file="io.xlsx", section_title="IO Config", file_type="excel"),
]
CHUNKS_B = [
    SemanticChunk(chunk_id="b1", project_id=PROJ_B, content="Pump motor fault detection algorithm",
                  source_file="plc_b.l5x", section_title="Pump", file_type="l5x"),
]


# ── Upsert ────────────────────────────────────────────────────────────────────

def test_upsert_returns_count(sem):
    n = sem.upsert_chunks(PROJ_A, CHUNKS_A)
    assert n == len(CHUNKS_A)


def test_upsert_populates_bm25(sem):
    sem.upsert_chunks(PROJ_A, CHUNKS_A)
    assert sem.chunk_count(PROJ_A) == len(CHUNKS_A)


def test_upsert_empty_list(sem):
    n = sem.upsert_chunks(PROJ_A, [])
    assert n == 0


# ── BM25 keyword search ───────────────────────────────────────────────────────

def test_bm25_finds_exact_keyword(sem):
    sem.upsert_chunks(PROJ_A, CHUNKS_A)
    results = sem.search("motor speed conveyor", PROJ_A, top_k=3)
    assert len(results) >= 1
    top = results[0]
    assert "motor" in top["content"].lower() or "conveyor" in top["content"].lower()


def test_bm25_finds_fault(sem):
    sem.upsert_chunks(PROJ_A, CHUNKS_A)
    results = sem.search("safety interlock", PROJ_A, top_k=3)
    assert any("interlock" in r["content"].lower() for r in results)


def test_bm25_rio_search(sem):
    sem.upsert_chunks(PROJ_A, CHUNKS_A)
    results = sem.search("RIO rack slot", PROJ_A, top_k=3)
    assert any("rio" in r["content"].lower() or "rack" in r["content"].lower() for r in results)


def test_bm25_returns_scores(sem):
    sem.upsert_chunks(PROJ_A, CHUNKS_A)
    results = sem.search("conveyor", PROJ_A, top_k=3)
    for r in results:
        assert "score" in r
        assert isinstance(r["score"], float)


def test_top_k_respected(sem):
    sem.upsert_chunks(PROJ_A, CHUNKS_A)
    results = sem.search("any query", PROJ_A, top_k=2)
    assert len(results) <= 2


# ── Cross-project isolation ───────────────────────────────────────────────────

def test_cross_project_isolation(sem):
    """Project A query must NEVER return Project B results."""
    sem.upsert_chunks(PROJ_A, CHUNKS_A)
    sem.upsert_chunks(PROJ_B, CHUNKS_B)

    results_a = sem.search("pump motor fault", PROJ_A, top_k=5)
    chunk_ids = {r["chunk_id"] for r in results_a}
    assert "b1" not in chunk_ids, "Project B chunk leaked into Project A results!"


def test_project_b_finds_own_chunks(sem):
    sem.upsert_chunks(PROJ_A, CHUNKS_A)
    sem.upsert_chunks(PROJ_B, CHUNKS_B)
    results_b = sem.search("pump fault", PROJ_B, top_k=5)
    # b1 is the only B chunk
    assert any(r["chunk_id"] == "b1" for r in results_b)


# ── Delete project ────────────────────────────────────────────────────────────

def test_delete_project_clears_bm25(sem):
    sem.upsert_chunks(PROJ_A, CHUNKS_A)
    sem.delete_project(PROJ_A)
    assert sem.chunk_count(PROJ_A) == 0


def test_delete_project_does_not_affect_other(sem):
    sem.upsert_chunks(PROJ_A, CHUNKS_A)
    sem.upsert_chunks(PROJ_B, CHUNKS_B)
    sem.delete_project(PROJ_A)
    assert sem.chunk_count(PROJ_B) == 1
