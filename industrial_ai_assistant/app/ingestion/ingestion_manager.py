from typing import List, Dict, Any
from app.core.interfaces.vector_store_interface import VectorStoreInterface
from app.core.interfaces.embedding_interface import EmbeddingInterface
from app.ingestion.processors import PDFProcessor, L5XProcessor, ExcelProcessor
from app.core.schemas import DocumentChunk

class IngestionManager:
    def __init__(
        self, 
        vector_store: VectorStoreInterface,
        embedder: EmbeddingInterface,
        processors: Dict[str, Any]
    ):
        self.vector_store = vector_store
        self.embedder = embedder
        self.processors = processors

    def ingest_file(self, file_path: str) -> bool:
        ext = file_path.split(".")[-1].lower()
        processor = self.processors.get(ext)
        
        if not processor:
            print(f"No processor for extension {ext}")
            return False
            
        chunks: List[DocumentChunk] = processor.process(file_path)
        
        # Embed chunks
        texts = [c.content for c in chunks]
        embeddings = self.embedder.embed_batch(texts)
        
        for i, chunk in enumerate(chunks):
            chunk.embedding = embeddings[i]
            
        # Store
        return self.vector_store.add_documents(chunks)
