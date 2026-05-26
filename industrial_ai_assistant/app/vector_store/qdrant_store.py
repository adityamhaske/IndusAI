"""
Qdrant vector store — supports per-user dynamic collections (indusai_{uid}).

The constructor takes a default collection name, but all operations
can be overridden with a per-user collection via method parameters.
"""
from typing import List, Optional, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.core.interfaces.vector_store_interface import VectorStoreInterface
from app.core.schemas import DocumentChunk, ChunkMetadata
from app.core.exceptions import VectorStoreError


def user_collection_name(uid: str) -> str:
    """Derive the per-user Qdrant collection name."""
    # Sanitize uid for collection name (alphanumeric + underscore only)
    safe_uid = "".join(c if c.isalnum() else "_" for c in uid)
    return f"indusai_{safe_uid}"


class QdrantStore(VectorStoreInterface):
    def __init__(
        self,
        host: str = "",
        port: int = 6333,
        collection_name: str = "industrial_docs",
        vector_size: int = 768,
        url: str = "",
        api_key: str = "",
    ):
        if url and api_key:
            self.client = QdrantClient(url=url, api_key=api_key)
        elif host:
            self.client = QdrantClient(host=host, port=port)
        else:
            self.client = QdrantClient(url=url or "http://localhost:6333")
        self.collection_name = collection_name
        self.vector_size = vector_size

    def _resolve_collection(self, collection: Optional[str] = None) -> str:
        return collection or self.collection_name

    def ensure_collection(self, collection: Optional[str] = None) -> None:
        """Create collection if it doesn't exist."""
        name = self._resolve_collection(collection)
        from qdrant_client.http.exceptions import UnexpectedResponse
        try:
            self.client.get_collection(name)
        except Exception:
            try:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=models.VectorParams(
                        size=self.vector_size, distance=models.Distance.COSINE
                    ),
                )
            except UnexpectedResponse as e:
                if getattr(e, "status_code", None) == 409 or "already exists" in str(e):
                    pass
                else:
                    raise

    def add_documents(
        self, documents: List[DocumentChunk], collection: Optional[str] = None
    ) -> bool:
        name = self._resolve_collection(collection)
        self.ensure_collection(name)
        try:
            points = [
                models.PointStruct(
                    id=doc.metadata.chunk_id,
                    vector=doc.embedding,
                    payload={
                        "content": doc.content,
                        "metadata": doc.metadata.model_dump(),
                    },
                )
                for doc in documents
            ]
            self.client.upsert(collection_name=name, points=points)
            return True
        except Exception as e:
            raise VectorStoreError(f"Failed to add documents to Qdrant: {e}")

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        collection: Optional[str] = None,
    ) -> List[DocumentChunk]:
        name = self._resolve_collection(collection)
        try:
            query_filter = None
            if filters:
                pass  # Placeholder for filter construction

            results = self.client.search(
                collection_name=name,
                query_vector=query_embedding,
                limit=top_k,
                query_filter=query_filter,
            )

            chunks = []
            for point in results:
                payload = point.payload
                chunks.append(
                    DocumentChunk(
                        content=payload.get("content", ""),
                        metadata=ChunkMetadata(**payload.get("metadata", {})),
                        embedding=point.vector,
                    )
                )
            return chunks
        except Exception as e:
            raise VectorStoreError(f"Qdrant search failed: {e}")

    def delete_collection(self, collection: Optional[str] = None) -> bool:
        name = self._resolve_collection(collection)
        try:
            self.client.delete_collection(name)
            return True
        except Exception as e:
            raise VectorStoreError(f"Failed to delete collection: {e}")

    def collection_exists(self, collection: Optional[str] = None) -> bool:
        name = self._resolve_collection(collection)
        try:
            self.client.get_collection(name)
            return True
        except Exception:
            return False

    def collection_count(self, collection: Optional[str] = None) -> int:
        name = self._resolve_collection(collection)
        try:
            info = self.client.get_collection(name)
            return info.points_count or 0
        except Exception:
            return 0
