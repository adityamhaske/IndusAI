from typing import List
import re
from app.core.interfaces.chunker_interface import ChunkerInterface
from app.core.schemas import DocumentChunk, ChunkMetadata

class SectionChunker(ChunkerInterface):
    def chunk_text(self, text: str, metadata: ChunkMetadata) -> List[DocumentChunk]:
        # Simple regex split on headers like "## Header"
        # TODO: Improve regex for various formats
        sections = re.split(r'(^#+ .*$)', text, flags=re.MULTILINE)
        chunks = []
        
        current_header = "Intro"
        
        for part in sections:
            if part.startswith("#"):
                current_header = part.strip()
            elif part.strip():
                new_metadata = metadata.model_copy()
                new_metadata.section_title = current_header
                new_metadata.chunk_id = f"{metadata.source_file}_{current_header[:20]}"
                
                chunks.append(DocumentChunk(
                    content=part.strip(),
                    metadata=new_metadata
                ))
                
        return chunks
