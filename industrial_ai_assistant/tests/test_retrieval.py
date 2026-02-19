import pytest
from app.vector_store.in_memory_store import InMemoryStore
from app.embeddings.mock_embedder import MockEmbedder
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.keyword_search import KeywordSearch
from app.core.schemas import DocumentChunk, ChunkMetadata

def test_hybrid_retrieval_flow():
    # Setup
    store = InMemoryStore()
    embedder = MockEmbedder()
    keyword = KeywordSearch()
    
    retriever = HybridRetriever(store, embedder, keyword)
    
    # Add doc
    doc = DocumentChunk(
        content="Test content",
        metadata=ChunkMetadata(source_file="test.txt", chunk_id="1"),
        embedding=embedder.embed_text("Test content")
    )
    store.add_documents([doc])
    
    # Retrieve
    results = retriever.retrieve("Test", top_k=1)
    assert len(results) == 1
    assert results[0].content == "Test content"
