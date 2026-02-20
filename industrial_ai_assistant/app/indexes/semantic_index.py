"""
SemanticIndex — Hybrid BM25 + Qdrant vector retrieval, project-scoped.

Design:
  - Every upsert includes metadata.project_id
  - Every search filters by metadata.project_id — no cross-project leakage
  - BM25 keyword search via scikit-learn TfidfVectorizer (in-process)
  - Qdrant vector search with project_id payload filter
  - Results merged + deduplicated by chunk_id, re-ranked by combined score
"""
import logging
import uuid
from typing import Dict, List, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models.project_models import SemanticChunk

logger = logging.getLogger(__name__)

_QDRANT_COLLECTION = "project_knowledge"
_VECTOR_SIZE = 384   # all-MiniLM-L6-v2 output dim


class SemanticIndex:
    """
    Hybrid semantic retrieval index (per-application singleton, project-scoped by metadata).
    """

    def __init__(self, qdrant_host: str = "localhost", qdrant_port: int = 6333,
                 embedder=None):
        self._host = qdrant_host
        self._port = qdrant_port
        self._embedder = embedder
        self._qdrant = None
        # BM25 store: project_id → {chunk_id: content}
        self._bm25_store: Dict[str, Dict[str, str]] = {}

    def _get_qdrant(self):
        if self._qdrant is None:
            try:
                from qdrant_client import QdrantClient
                self._qdrant = QdrantClient(host=self._host, port=self._port, timeout=5)
                self._ensure_collection()
            except Exception as exc:
                logger.warning("Qdrant unavailable — falling back to keyword-only: %s", exc)
                self._qdrant = None
        return self._qdrant

    def _ensure_collection(self) -> None:
        try:
            from qdrant_client.models import Distance, VectorParams
            client = self._qdrant
            existing = [c.name for c in client.get_collections().collections]
            if _QDRANT_COLLECTION not in existing:
                client.create_collection(
                    collection_name=_QDRANT_COLLECTION,
                    vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
                )
                logger.info("Created Qdrant collection '%s'", _QDRANT_COLLECTION)
        except Exception as exc:
            logger.warning("Could not ensure collection: %s", exc)

    def upsert_chunks(self, project_id: str, chunks: List[SemanticChunk]) -> int:
        """
        Embed and upsert chunks into Qdrant + BM25 store.
        EVERY chunk must carry project_id in metadata.

        Returns number of chunks successfully indexed.
        """
        if not chunks:
            return 0

        # Update BM25 store
        if project_id not in self._bm25_store:
            self._bm25_store[project_id] = {}
        for c in chunks:
            self._bm25_store[project_id][c.chunk_id] = c.content

        # Qdrant vector upsert
        client = self._get_qdrant()
        if client is None:
            logger.warning("Qdrant not available. Chunks stored in BM25 only.")
            return len(chunks)

        try:
            from qdrant_client.models import PointStruct
            texts = [c.content for c in chunks]
            embeddings = self._embed_batch(texts)
            if embeddings is None:
                return len(chunks)

            points = []
            for chunk, vector in zip(chunks, embeddings):
                points.append(PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_id)),
                    vector=vector.tolist(),
                    payload={
                        "project_id": project_id,        # MANDATORY — enables filtering
                        "chunk_id": chunk.chunk_id,
                        "content": chunk.content,
                        "source_file": chunk.source_file,
                        "section_title": chunk.section_title,
                        "file_type": chunk.file_type,
                        "page": chunk.page,
                    },
                ))

            client.upsert(collection_name=_QDRANT_COLLECTION, points=points)
            return len(points)
        except Exception as exc:
            logger.error("Qdrant upsert failed: %s", exc, exc_info=True)
            return len(chunks)

    def search(
        self,
        query: str,
        project_id: str,
        top_k: int = 5,
        file_type_filter: Optional[str] = None,
    ) -> List[dict]:
        """
        Hybrid search: BM25 keyword + Qdrant vector, filtered by project_id.
        Returns up to top_k results with similarity_score.
        Cross-project results are NEVER returned.
        """
        bm25_hits = self._bm25_search(query, project_id, top_k * 2)
        vector_hits = self._vector_search(query, project_id, top_k * 2, file_type_filter)

        # Merge + deduplicate by chunk_id
        seen: Dict[str, dict] = {}
        for hit in vector_hits:
            seen[hit["chunk_id"]] = hit
        for hit in bm25_hits:
            cid = hit["chunk_id"]
            if cid in seen:
                # Boost combined score
                seen[cid]["score"] = min(1.0, seen[cid]["score"] + hit["score"] * 0.3)
            else:
                seen[cid] = hit

        ranked = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
        return ranked[:top_k]

    def delete_project(self, project_id: str) -> None:
        """Remove all vectors and BM25 entries for a project."""
        self._bm25_store.pop(project_id, None)
        client = self._get_qdrant()
        if client is None:
            return
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            client.delete(
                collection_name=_QDRANT_COLLECTION,
                points_selector=Filter(
                    must=[FieldCondition(key="project_id", match=MatchValue(value=project_id))]
                ),
            )
        except Exception as exc:
            logger.error("Qdrant delete for project '%s' failed: %s", project_id, exc)

    def chunk_count(self, project_id: str) -> int:
        """Count chunks stored for a project (BM25 store as proxy)."""
        return len(self._bm25_store.get(project_id, {}))

    # ── Internal search methods ───────────────────────────────────────────────

    def _bm25_search(self, query: str, project_id: str, top_k: int) -> List[dict]:
        """TF-IDF keyword search scoped to project_id."""
        store = self._bm25_store.get(project_id, {})
        if not store:
            return []
        try:
            ids = list(store.keys())
            docs = [store[i] for i in ids]
            corpus = docs + [query]
            vec = TfidfVectorizer(stop_words="english", max_features=10_000)
            tfidf = vec.fit_transform(corpus)
            scores = cosine_similarity(tfidf[-1:], tfidf[:-1]).flatten()
            top_idx = np.argsort(scores)[::-1][:top_k]
            return [
                {
                    "chunk_id": ids[i],
                    "content": docs[i],
                    "score": float(scores[i]),
                    "source": "bm25",
                    "section_title": "",
                    "source_file": "",
                    "file_type": "",
                }
                for i in top_idx if scores[i] > 0.01
            ]
        except Exception as exc:
            logger.warning("BM25 search failed: %s", exc)
            return []

    def _vector_search(self, query: str, project_id: str, top_k: int,
                       file_type_filter: Optional[str]) -> List[dict]:
        """Qdrant cosine vector search filtered by project_id."""
        client = self._get_qdrant()
        if client is None:
            return []
        embedding = self._embed_text(query)
        if embedding is None:
            return []
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue, FieldCondition
            must = [FieldCondition(key="project_id", match=MatchValue(value=project_id))]
            if file_type_filter:
                must.append(FieldCondition(key="file_type", match=MatchValue(value=file_type_filter)))

            results = client.search(
                collection_name=_QDRANT_COLLECTION,
                query_vector=embedding.tolist(),
                query_filter=Filter(must=must),
                limit=top_k,
                with_payload=True,
            )
            return [
                {
                    "chunk_id": r.payload.get("chunk_id", ""),
                    "content": r.payload.get("content", ""),
                    "score": r.score,
                    "source": "vector",
                    "section_title": r.payload.get("section_title", ""),
                    "source_file": r.payload.get("source_file", ""),
                    "file_type": r.payload.get("file_type", ""),
                }
                for r in results
            ]
        except Exception as exc:
            logger.error("Qdrant search error: %s", exc, exc_info=True)
            return []

    def _embed_text(self, text: str):
        if self._embedder is None:
            return None
        try:
            vec = self._embedder.embed_text(text)
            return np.array(vec, dtype=np.float32)
        except Exception as exc:
            logger.warning("Embedding failed: %s", exc)
            return None

    def _embed_batch(self, texts: List[str]):
        if self._embedder is None:
            return None
        try:
            vecs = [self._embedder.embed_text(t) for t in texts]
            return np.array(vecs, dtype=np.float32)
        except Exception as exc:
            logger.warning("Batch embedding failed: %s", exc)
            return None


# ── Global singleton ──────────────────────────────────────────────────────────
_instance: Optional[SemanticIndex] = None


def get_semantic_index(qdrant_host: str = "localhost", qdrant_port: int = 6333,
                       embedder=None) -> SemanticIndex:
    global _instance
    if _instance is None:
        _instance = SemanticIndex(qdrant_host, qdrant_port, embedder)
    return _instance
