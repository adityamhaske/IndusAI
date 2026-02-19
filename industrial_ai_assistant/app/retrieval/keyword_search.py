from typing import List, Optional, Dict, Any
from app.core.interfaces.retriever_interface import RetrieverInterface
from app.core.schemas import DocumentChunk

class KeywordSearch(RetrieverInterface):
    def retrieve(self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[DocumentChunk]:
        # TODO: Implement actual keyword search (e.g., BM25 or SQL LIKE)
        # For now, return empty list or mock
        return []
