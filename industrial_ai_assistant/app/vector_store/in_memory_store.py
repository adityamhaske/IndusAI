from typing import List, Optional, Dict, Any
import numpy as np
from app.core.interfaces.vector_store_interface import VectorStoreInterface
from app.core.schemas import DocumentChunk

class InMemoryStore(VectorStoreInterface):
    def __init__(self):
        self.documents: List[DocumentChunk] = []

    def add_documents(self, documents: List[DocumentChunk]) -> bool:
        self.documents.extend(documents)
        return True

    def search(self, query_embedding: List[float], top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[DocumentChunk]:
        if not self.documents:
            return []
        
        # Simple cosine similarity (unoptimized for large scale)
        # In a real scenario, use faiss or similar for in-memory
        query_vec = np.array(query_embedding)
        scores = []
        
        for doc in self.documents:
            if not doc.embedding:
                continue
            doc_vec = np.array(doc.embedding)
            score = np.dot(query_vec, doc_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(doc_vec))
            scores.append((score, doc))
            
        scores.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scores[:top_k]]

    def delete_collection(self) -> bool:
        self.documents = []
        return True
