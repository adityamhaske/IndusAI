from abc import ABC, abstractmethod
from typing import List
from app.core.schemas import DocumentChunk, ChunkMetadata

class ChunkerInterface(ABC):
    @abstractmethod
    def chunk_text(self, text: str, metadata: ChunkMetadata) -> List[DocumentChunk]:
        """
        Split text into chunks.
        
        Args:
            text: The full text content.
            metadata: Base metadata to attach to each chunk.
            
        Returns:
            List of DocumentChunk objects.
        """
        pass
