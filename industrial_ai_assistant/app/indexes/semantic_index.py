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
_VECTOR_DIM = 768   # Gemini embeddings


class SemanticIndex:
    """
    Wraps Qdrant for semantic storage and retrieval.
    BM25 index is maintained in-process over chunk texts per project.
    """

    def __init__(self, embedder, qdrant_host: str = "127.0.0.1", qdrant_port: int = 6333):
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

    def upsert_chunks(self, chunks: list[SemanticChunk], project_id: str, embedder=None) -> int:
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
        
        active_embedder = embedder or self._embedder

        for chunk in chunks:
            embedding = active_embedder.embed_text(chunk.content)
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
        logger.info("[Ingestion - %s] Upserted %d chunk embeddings into Qdrant", project_id, len(points))
        return len(points)

    # ── Vector search ──────────────────────────────────────────────────────────

    def vector_search(
        self,
        query: str,
        project_id: str,
        top_k: int = 5,
        file_type: Optional[str] = None,
        scope_files: set[str] | None = None,
        embedder=None,
    ) -> list[ScoredChunk]:
        """Pure cosine vector search, filtered by project_id (mandatory)."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

        client = self._get_client()
        active_embedder = embedder or self._embedder
        q_emb = active_embedder.embed_text(query)

        must = [FieldCondition(key="project_id", match=MatchValue(value=project_id))]
        if file_type:
            must.append(FieldCondition(key="file_type", match=MatchValue(value=file_type)))
        if scope_files is not None:
            must.append(FieldCondition(key="source_file", match=MatchAny(any=list(scope_files))))

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
        scope_files: set[str] | None = None,
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
                if scope_files is not None and chunk.source_file not in scope_files:
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
        scope_files: set[str] | None = None,
        embedder=None,
    ) -> list[ScoredChunk]:
        """
        Reciprocal Rank Fusion of BM25 + vector results.
        RRF formula: score = Σ 1/(k + rank)  with k=60.
        """
        k_rrf = 60

        # Auto-warm BM25 from Qdrant if not yet loaded
        if project_id not in self._chunk_store or len(self._chunk_store.get(project_id, {})) == 0:
            self.warm_bm25_from_qdrant(project_id)

        vector_hits = self.vector_search(query, project_id, top_k=top_k * 2, file_type=file_type, scope_files=scope_files, embedder=embedder)
        bm25_hits   = self.bm25_search(query, project_id, top_k=top_k * 2, scope_files=scope_files)

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
        """Number of chunks indexed for this project — queries Qdrant directly."""
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            client = self._get_client()
            result = client.count(
                collection_name=_QDRANT_COLLECTION,
                count_filter=Filter(
                    must=[FieldCondition(key="project_id", match=MatchValue(value=project_id))]
                ),
                exact=True,
            )
            return result.count
        except Exception as exc:
            logger.warning("collection_size query failed: %s", exc)
            # Fallback to in-memory count
            return len(self._chunk_store.get(project_id, {}))

    def all_source_files(self, project_id: str) -> set[str]:
        """Return all unique source_file paths — queries Qdrant directly."""
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue, ScrollRequest
            client = self._get_client()
            records, _ = client.scroll(
                collection_name=_QDRANT_COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="project_id", match=MatchValue(value=project_id))]
                ),
                limit=10000,
                with_payload=["source_file"],
                with_vectors=False,
            )
            return {r.payload.get("source_file", "") for r in records if r.payload.get("source_file")}
        except Exception as exc:
            logger.warning("all_source_files query failed: %s", exc)
            store = self._chunk_store.get(project_id, {})
            return {chunk.source_file for chunk in store.values() if chunk.source_file}

    def warm_bm25_from_qdrant(self, project_id: str) -> int:
        """
        Rebuild in-process BM25 index from persisted Qdrant data.
        Call this on startup or first query for a project.
        Returns number of chunks loaded.
        """
        if project_id in self._chunk_store and len(self._chunk_store[project_id]) > 0:
            return len(self._chunk_store[project_id])  # Already warm

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            client = self._get_client()
            records, _ = client.scroll(
                collection_name=_QDRANT_COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="project_id", match=MatchValue(value=project_id))]
                ),
                limit=50000,
                with_payload=True,
                with_vectors=False,
            )
            count = 0
            for r in records:
                p = r.payload or {}
                chunk_id = p.get("chunk_id", "")
                content = p.get("content", "")
                if not chunk_id or not content:
                    continue
                fake_chunk = SemanticChunk(
                    chunk_id=chunk_id,
                    content=content,
                    source_file=p.get("source_file", ""),
                    section_title=p.get("section_title", ""),
                    file_type=p.get("file_type", ""),
                    page=p.get("page", 0),
                )
                self._bm25_add(project_id, chunk_id, content, fake_chunk)
                count += 1
            logger.info("[BM25 warm] Loaded %d chunks from Qdrant for project=%s", count, project_id)
            return count
        except Exception as exc:
            logger.warning("BM25 warm-up failed for project=%s: %s", project_id, exc)
            return 0

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

    def remove_file(self, project_id: str, source_file: str) -> int:
        """Remove all chunks associated with a specific file from Qdrant and BM25."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        # 1. Remove from BM25 memory
        removed_count = 0
        store = self._chunk_store.get(project_id, {})
        to_delete = [cid for cid, chunk in store.items() if chunk.source_file == source_file]
        for cid in to_delete:
            chunk = store.pop(cid)
            removed_count += 1
            tokens = _tokenise(chunk.content)
            tf_map = {}
            for t in tokens:
                tf_map[t] = tf_map.get(t, 0) + 1
            for term, tf in tf_map.items():
                if term in self._bm25_index[project_id] and cid in self._bm25_index[project_id][term]:
                    del self._bm25_index[project_id][term][cid]
                if term in self._df[project_id]:
                    self._df[project_id][term] = max(0, self._df[project_id][term] - 1)

        # 2. Remove from Qdrant
        if removed_count > 0:
            client = self._get_client()
            client.delete(
                collection_name=_QDRANT_COLLECTION,
                points_selector=Filter(
                    must=[
                        FieldCondition(key="project_id", match=MatchValue(value=project_id)),
                        FieldCondition(key="source_file", match=MatchValue(value=source_file))
                    ]
                )
            )
        logger.info("[%s] Removed %d semantic chunks for file '%s'.", project_id, removed_count, source_file)
        return removed_count

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


def get_semantic_index(embedder=None, host="127.0.0.1", port=6333) -> SemanticIndex:
    global _instance
    if _instance is None:
        if embedder is None:
            from app.embeddings.gemini_embedder import GeminiEmbedder
            embedder = GeminiEmbedder()
        _instance = SemanticIndex(embedder=embedder, qdrant_host=host, qdrant_port=port)
    return _instance
