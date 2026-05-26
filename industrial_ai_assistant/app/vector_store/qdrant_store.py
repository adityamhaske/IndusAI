from typing import List, Optional, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.core.interfaces.vector_store_interface import VectorStoreInterface
from app.core.schemas import DocumentChunk, ChunkMetadata
from app.core.exceptions import VectorStoreError

class QdrantStore(VectorStoreInterface):
    def __init__(self, host: str, port: int, collection_name: str, vector_size: int = 768, url: str = "", api_key: str = ""):
        if url and api_key:
            self.client = QdrantClient(url=url, api_key=api_key)
        else:
            self.client = QdrantClient(host=host, port=port)
        self.collection_name = collection_name
        self.vector_size = vector_size
        self._ensure_collection()

    def _ensure_collection(self):
        from qdrant_client.http.exceptions import UnexpectedResponse
        try:
            self.client.get_collection(self.collection_name)
        except Exception:
            try:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(size=self.vector_size, distance=models.Distance.COSINE)
                )
            except UnexpectedResponse as e:
                if getattr(e, "status_code", None) == 409 or "already exists" in str(e):
                    pass # Collection already exists
                else:
                    raise

    def add_documents(self, documents: List[DocumentChunk]) -> bool:
        try:
            points = []
            for doc in documents:
                points.append(models.PointStruct(
                    id=doc.metadata.chunk_id,
                    vector=doc.embedding,
                    payload={
                        "content": doc.content,
                        "metadata": doc.metadata.model_dump()
                    }
                ))
            
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            return True
        except Exception as e:
            raise VectorStoreError(f"Failed to add documents to Qdrant: {str(e)}")

    def search(self, query_embedding: List[float], top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[DocumentChunk]:
        try:
            # Construct Qdrant filter if needed
            query_filter = None
            if filters:
               # Placeholder: simplistic filter logic
               pass

            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=top_k,
                query_filter=query_filter
            )
            
            chunks = []
            for point in results:
                payload = point.payload
                chunks.append(DocumentChunk(
                    content=payload.get("content", ""),
                    metadata=ChunkMetadata(**payload.get("metadata", {})),
                    embedding=point.vector
                ))
            return chunks
        except Exception as e:
            raise VectorStoreError(f"Qdrant search failed: {str(e)}")

    def delete_collection(self) -> bool:
        try:
            self.client.delete_collection(self.collection_name)
            return True
        except Exception as e:
            raise VectorStoreError(f"Failed to delete collection: {str(e)}")
