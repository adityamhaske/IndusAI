from typing import List, Optional, Dict, Any
from app.core.interfaces.retriever_interface import RetrieverInterface
from app.core.interfaces.vector_store_interface import VectorStoreInterface
from app.core.interfaces.embedding_interface import EmbeddingInterface
from app.core.schemas import DocumentChunk
from app.retrieval.keyword_search import KeywordSearch
from app.retrieval.reranker import Reranker

class HybridRetriever(RetrieverInterface):
    def __init__(
        self, 
        vector_store: VectorStoreInterface, 
        embedder: EmbeddingInterface, 
        keyword_retriever: KeywordSearch,
        reranker: Optional[Reranker] = None
    ):
        self.vector_store = vector_store
        self.embedder = embedder
        self.keyword_retriever = keyword_retriever
        self.reranker = reranker

    def retrieve(self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[DocumentChunk]:
        # 1. Vector Search
        query_embedding = self.embedder.embed_text(query)
        vector_results = self.vector_store.search(query_embedding, top_k=top_k, filters=filters)
        
        # 2. Keyword Search
        keyword_results = self.keyword_retriever.retrieve(query, top_k=top_k, filters=filters)
        
        # 3. Merge & Deduplicate
        seen_ids = set()
        merged_results = []
        
        for doc in vector_results + keyword_results:
            if doc.metadata.chunk_id not in seen_ids:
                merged_results.append(doc)
                seen_ids.add(doc.metadata.chunk_id)
        
        # 4. Rerank if available
        if self.reranker:
            return self.reranker.rerank(query, merged_results, top_k)
            
        return merged_results[:top_k]
