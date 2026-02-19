from typing import List
from app.core.schemas import DocumentChunk

class Reranker:
    def rerank(self, query: str, documents: List[DocumentChunk], top_k: int) -> List[DocumentChunk]:
        # TODO: Implement cross-encoder reranking
        # For now, just return top_k of the input list
        return documents[:top_k]
