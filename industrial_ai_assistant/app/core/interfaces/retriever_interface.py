from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from app.core.schemas import DocumentChunk

class RetrieverInterface(ABC):
    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[DocumentChunk]:
        """
        Retrieve relevant documents for a query.
        
        Args:
            query: The search query string.
            top_k: Number of results.
            filters: Optional filters.
            
        Returns:
            List of relevant DocumentChunks.
        """
        pass
