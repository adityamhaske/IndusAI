from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from app.core.schemas import DocumentChunk

class VectorStoreInterface(ABC):
    @abstractmethod
    def add_documents(self, documents: List[DocumentChunk]) -> bool:
        """
        Add documents to the vector store.
        
        Args:
            documents: List of DocumentChunk objects.
            
        Returns:
            True if successful.
        """
        pass

    @abstractmethod
    def search(self, query_embedding: List[float], top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[DocumentChunk]:
        """
        Search for similar documents using a query embedding.
        
        Args:
            query_embedding: The vector representation of the query.
            top_k: Number of results to return.
            filters: Optional metadata filters.
            
        Returns:
            List of matching DocumentChunk objects.
        """
        pass
    
    @abstractmethod
    def delete_collection(self) -> bool:
        """
        Delete the entire collection/index.
        
        Returns:
            True if successful.
        """
        pass
