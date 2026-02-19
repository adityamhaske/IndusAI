from typing import List
from app.core.interfaces.chunker_interface import ChunkerInterface
from app.core.schemas import DocumentChunk, ChunkMetadata

class SemanticChunker(ChunkerInterface):
    def chunk_text(self, text: str, metadata: ChunkMetadata) -> List[DocumentChunk]:
        # TODO: Implement semantic chunking logic using embeddings to find break points
        # For now, falls back to simple paragraph splitting
        paragraphs = text.split("\n\n")
        chunks = []
        
        for i, para in enumerate(paragraphs):
            if not para.strip():
                continue
                
            new_metadata = metadata.model_copy()
            new_metadata.chunk_id = f"{metadata.source_file}_semantic_{i}"
            
            chunks.append(DocumentChunk(
                content=para,
                metadata=new_metadata
            ))
        return chunks
