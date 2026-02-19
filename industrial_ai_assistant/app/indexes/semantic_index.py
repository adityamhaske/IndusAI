"""
SemanticIndex — wraps QdrantStore with per-project metadata filtering.

Key design requirements:
  - Every chunk stored with project_id in metadata payload
  - Every search filtered to the calling project — no cross-project results
  - Uses the existing Qdrant collection (industrial_docs) with filter pushdown
  - Embedder is injected (SentenceTransformer or Mock)
"""
from __future__ import annotations

import logging
from typing import List, Optional

from qdrant_client.http import models as qdrant_models

from app.core.schemas import DocumentChunk
from app.embeddings.sentence_transformer_embedder import SentenceTransformerEmbedder
from app.embeddings.mock_embedder import MockEmbedder
from app.core.interfaces.embedding_interface import EmbeddingInterface

logger = logging.getLogger(__name__)


class SemanticIndex:
    """
    Project-aware semantic search index backed by Qdrant.

    All chunks are tagged with project_id in their Qdrant payload so
    searches are scoped per-project.
    """

    def __init__(self, qdrant_client, collection_name: str, embedder: EmbeddingInterface):
        self._client = qdrant_client
        self._collection = collection_name
        self._embedder = embedder

    # ── Indexing ──────────────────────────────────────────────────────────────

    def index_chunks(self, project_id: str, chunks: List[DocumentChunk]) -> int:
        """
        Embed and upsert chunks tagged with project_id.
        Returns number of chunks indexed.
        """
        if not chunks:
            return 0

        points = []
        texts = [c.content for c in chunks]
        embeddings = self._embedder.embed_batch(texts)

        for chunk, embedding in zip(chunks, embeddings):
            # Ensure project_id is set in metadata
            meta = chunk.metadata.model_copy()
            meta.project_id = project_id

            # Use a deterministic int ID from the chunk_id string
            point_id = abs(hash(chunk.metadata.chunk_id)) % (2 ** 63)
            payload = {
                "content": chunk.content,
                "metadata": meta.model_dump(),
            }
            points.append(qdrant_models.PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload,
            ))

        try:
            self._client.upsert(collection_name=self._collection, points=points)
            logger.debug("SemanticIndex: upserted %d chunks for project=%s", len(points), project_id)
        except Exception as exc:
            logger.error("Qdrant upsert failed for project=%s: %s", project_id, exc)
            raise

        return len(points)

    # ── Search ────────────────────────────────────────────────────────────────

    def search(
        self,
        project_id: str,
        query: str,
        top_k: int = 5,
    ) -> List[DocumentChunk]:
        """
        Semantic search scoped strictly to project_id.
        Returns top_k DocumentChunks ordered by similarity.
        """
        query_vec = self._embedder.embed_text(query)

        # Qdrant filter: only return chunks belonging to this project
        project_filter = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="metadata.project_id",
                    match=qdrant_models.MatchValue(value=project_id),
                )
            ]
        )

        try:
            results = self._client.search(
                collection_name=self._collection,
                query_vector=query_vec,
                limit=top_k,
                query_filter=project_filter,
                with_payload=True,
            )
        except Exception as exc:
            logger.error("Qdrant search failed (project=%s): %s", project_id, exc)
            return []

        chunks = []
        for point in results:
            payload = point.payload or {}
            meta_dict = payload.get("metadata", {})
            content = payload.get("content", "")
            from app.core.schemas import ChunkMetadata
            try:
                meta = ChunkMetadata(**meta_dict)
            except Exception:
                meta = ChunkMetadata(
                    source_file=meta_dict.get("source_file", "unknown"),
                    chunk_id=meta_dict.get("chunk_id", str(point.id)),
                    project_id=project_id,
                )
            chunks.append(DocumentChunk(content=content, metadata=meta))

        return chunks

    # ── Delete project chunks ─────────────────────────────────────────────────

    def delete_project(self, project_id: str) -> None:
        """Remove all chunks belonging to project_id from the collection."""
        try:
            self._client.delete(
                collection_name=self._collection,
                points_selector=qdrant_models.FilterSelector(
                    filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="metadata.project_id",
                                match=qdrant_models.MatchValue(value=project_id),
                            )
                        ]
                    )
                ),
            )
            logger.info("SemanticIndex: deleted all chunks for project=%s", project_id)
        except Exception as exc:
            logger.warning("Failed to delete project chunks (project=%s): %s", project_id, exc)
