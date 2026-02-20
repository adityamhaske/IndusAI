"""
SemanticIndex — Qdrant-backed vector store with hybrid search.

Every upsert and search MANDATES project_id in payload/filter.
No cross-project contamination is possible by design.

Hybrid search = BM25 (in-process) + Qdrant vector, merged via RRF.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from collections import defaultdict
from typing import Optional

from app.models.project_models import ScoredChunk, SemanticChunk

logger = logging.getLogger(__name__)

_QDRANT_COLLECTION = "project_knowledge"
_VECTOR_DIM = 384   # all-MiniLM-L6-v2


class SemanticIndex:
    """
    Wraps Qdrant for semantic storage and retrieval.
    BM25 index is maintained in-process over chunk texts per project.
    """

    def __init__(self, embedder, qdrant_host: str = "localhost", qdrant_port: int = 6333):
        self._embedder = embedder
        self._host = qdrant_host
        self._port = qdrant_port
        self._client = None

        # BM25 inverted index per project: {project_id → {term → {chunk_id → tf}}}
        self._bm25_index: dict[str, dict[str, dict[str, float]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        # Chunk text store for BM25: {project_id → {chunk_id → chunk}}
        self._chunk_store: dict[str, dict[str, SemanticChunk]] = defaultdict(dict)
        # Document frequency per project: {project_id → {term → doc_count}}
        self._df: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            self._client = QdrantClient(host=self._host, port=self._port)
            # Ensure collection exists
            existing = [c.name for c in self._client.get_collections().collections]
            if _QDRANT_COLLECTION not in existing:
                self._client.create_collection(
                    collection_name=_QDRANT_COLLECTION,
                    vectors_config=VectorParams(size=_VECTOR_DIM, distance=Distance.COSINE),
                )
                logger.info("Created Qdrant collection: %s", _QDRANT_COLLECTION)
        return self._client

    # ── Upsert ─────────────────────────────────────────────────────────────────

    def upsert_chunks(self, chunks: list[SemanticChunk], project_id: str) -> int:
        """
        Embed and upsert chunks into Qdrant.
        project_id is mandatory — enforced by type signature AND payload.
        Returns number of chunks upserted.
        """
        if not chunks:
            return 0

        from qdrant_client.models import PointStruct

        client = self._get_client()
        points = []

        for chunk in chunks:
            embedding = self._embedder.embed_text(chunk.content)
            point_id = _chunk_uuid(chunk.chunk_id)
            payload = {
                "project_id":    project_id,   # MANDATORY — never omit
                "source_file":   chunk.source_file,
                "section_title": chunk.section_title,
                "file_type":     chunk.file_type,
                "page":          chunk.page,
                "content":       chunk.content,
                "chunk_id":      chunk.chunk_id,
            }
            points.append(PointStruct(id=point_id, vector=embedding, payload=payload))

            # BM25 index update
            self._bm25_add(project_id, chunk.chunk_id, chunk.content, chunk)

        client.upsert(collection_name=_QDRANT_COLLECTION, points=points)
        logger.debug("Upserted %d chunks for project=%s", len(points), project_id)
        return len(points)

    # ── Vector search ──────────────────────────────────────────────────────────

    def vector_search(
        self,
        query: str,
        project_id: str,
        top_k: int = 5,
        file_type: Optional[str] = None,
    ) -> list[ScoredChunk]:
        """Pure cosine vector search, filtered by project_id (mandatory)."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = self._get_client()
        q_emb = self._embedder.embed_text(query)

        must = [FieldCondition(key="project_id", match=MatchValue(value=project_id))]
        if file_type:
            must.append(FieldCondition(key="file_type", match=MatchValue(value=file_type)))

        hits = client.search(
            collection_name=_QDRANT_COLLECTION,
            query_vector=q_emb,
            query_filter=Filter(must=must),
            limit=top_k,
            with_payload=True,
        )
        return [_hit_to_scored(h, "vector") for h in hits]

    # ── BM25 keyword search ────────────────────────────────────────────────────

    def bm25_search(
        self,
        query: str,
        project_id: str,
        top_k: int = 5,
    ) -> list[ScoredChunk]:
        """
        In-process BM25 over chunks stored for this project.
        Formula: standard BM25 with k1=1.5, b=0.75.
        """
        terms = _tokenise(query)
        if not terms or project_id not in self._chunk_store:
            return []

        store = self._chunk_store[project_id]
        bm25 = self._bm25_index[project_id]
        df = self._df[project_id]
        N = len(store)
        if N == 0:
            return []

        k1, b = 1.5, 0.75
        avg_len = sum(len(_tokenise(c.content)) for c in store.values()) / N

        scores: dict[str, float] = defaultdict(float)
        for term in terms:
            if term not in bm25:
                continue
            idf = math.log((N - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5) + 1)
            for chunk_id, tf in bm25[term].items():
                chunk = store.get(chunk_id)
                if chunk is None:
                    continue
                dl = len(_tokenise(chunk.content))
                norm_tf = tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avg_len))
                scores[chunk_id] += idf * norm_tf

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        results = []
        for cid, score in ranked:
            chunk = store[cid]
            results.append(ScoredChunk(chunk=chunk, score=score, retrieval_method="bm25"))
        return results

    # ── Hybrid search (RRF) ────────────────────────────────────────────────────

    def hybrid_search(
        self,
        query: str,
        project_id: str,
        top_k: int = 5,
        file_type: Optional[str] = None,
    ) -> list[ScoredChunk]:
        """
        Reciprocal Rank Fusion of BM25 + vector results.
        RRF formula: score = Σ 1/(k + rank)  with k=60.
        """
        k_rrf = 60
        vector_hits = self.vector_search(query, project_id, top_k=top_k * 2, file_type=file_type)
        bm25_hits   = self.bm25_search(query, project_id, top_k=top_k * 2)

        rrf: dict[str, float] = {}
        seen_chunks: dict[str, ScoredChunk] = {}

        for rank, item in enumerate(vector_hits, 1):
            cid = item.chunk.chunk_id
            rrf[cid] = rrf.get(cid, 0.0) + 1 / (k_rrf + rank)
            seen_chunks[cid] = item

        for rank, item in enumerate(bm25_hits, 1):
            cid = item.chunk.chunk_id
            rrf[cid] = rrf.get(cid, 0.0) + 1 / (k_rrf + rank)
            if cid not in seen_chunks:
                seen_chunks[cid] = item

        ranked = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            ScoredChunk(chunk=seen_chunks[cid].chunk, score=score, retrieval_method="hybrid")
            for cid, score in ranked
            if cid in seen_chunks
        ]

    # ── Utility ───────────────────────────────────────────────────────────────

    def collection_size(self, project_id: str) -> int:
        """Number of chunks indexed for this project."""
        return len(self._chunk_store.get(project_id, {}))

    def delete_project(self, project_id: str) -> None:
        """Remove all Qdrant points and BM25 data for this project."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        client = self._get_client()
        client.delete(
            collection_name=_QDRANT_COLLECTION,
            points_selector=Filter(
                must=[FieldCondition(key="project_id", match=MatchValue(value=project_id))]
            ),
        )
        self._bm25_index.pop(project_id, None)
        self._chunk_store.pop(project_id, None)
        self._df.pop(project_id, None)
        logger.info("Deleted SemanticIndex data for project=%s", project_id)

    # ── BM25 helpers ──────────────────────────────────────────────────────────

    def _bm25_add(self, project_id: str, chunk_id: str, text: str, chunk: SemanticChunk) -> None:
        tokens = _tokenise(text)
        tf_map: dict[str, float] = {}
        for t in tokens:
            tf_map[t] = tf_map.get(t, 0) + 1
        for term, tf in tf_map.items():
            self._bm25_index[project_id][term][chunk_id] = tf
            self._df[project_id][term] = self._df[project_id].get(term, 0) + 1
        self._chunk_store[project_id][chunk_id] = chunk


# ── Module helpers ─────────────────────────────────────────────────────────────

def _tokenise(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _chunk_uuid(chunk_id: str) -> int:
    """Convert chunk_id string to a positive int usable as Qdrant point ID."""
    h = hashlib.sha1(chunk_id.encode()).hexdigest()[:16]
    return int(h, 16) & 0x7FFFFFFFFFFFFFFF   # keep positive


def _hit_to_scored(hit, method: str) -> ScoredChunk:
    p = hit.payload or {}
    chunk = SemanticChunk(
        chunk_id=p.get("chunk_id", str(hit.id)),
        content=p.get("content", ""),
        source_file=p.get("source_file", ""),
        section_title=p.get("section_title", ""),
        file_type=p.get("file_type", ""),
        page=p.get("page", 0),
        project_id=p.get("project_id", ""),
    )
    return ScoredChunk(chunk=chunk, score=hit.score, retrieval_method=method)


# ── Singleton registry ─────────────────────────────────────────────────────────

_instance: SemanticIndex | None = None


def get_semantic_index(embedder=None, host="localhost", port=6333) -> SemanticIndex:
    global _instance
    if _instance is None:
        if embedder is None:
            from app.embeddings.mock_embedder import MockEmbedder
            embedder = MockEmbedder()
        _instance = SemanticIndex(embedder=embedder, qdrant_host=host, qdrant_port=port)
    return _instance
