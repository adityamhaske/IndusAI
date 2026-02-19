from typing import List
from app.core.interfaces.chunker_interface import ChunkerInterface
from app.core.schemas import DocumentChunk, ChunkMetadata

class FixedTokenChunker(ChunkerInterface):
    def __init__(self, chunk_size: int = 512, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str, metadata: ChunkMetadata) -> List[DocumentChunk]:
        # Placeholder for real tokenizer logic
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), self.chunk_size - self.overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = " ".join(chunk_words)
            
            new_metadata = metadata.model_copy()
            new_metadata.chunk_id = f"{metadata.source_file}_{i}"
            
            chunks.append(DocumentChunk(
                content=chunk_text,
                metadata=new_metadata
            ))
            
        return chunks
