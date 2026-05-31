import os
import time
import json
import logging
from pathlib import Path
from typing import List
from app.core.schemas import DocumentChunk, ChunkMetadata
from app.core.interfaces.chunker_interface import ChunkerInterface

logger = logging.getLogger(__name__)

class PDFProcessor:
    def __init__(self, chunker: ChunkerInterface, api_key: str):
        self.chunker = chunker
        self.api_key = api_key
        
    def process(self, file_bytes: bytes, filename: str) -> List[DocumentChunk]:
        import pdfplumber
        import io
        
        logger.info(f"Extracting {filename} via pdfplumber...")
        full_text = []
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        full_text.append(page_text)
        except Exception as e:
            logger.error(f"Failed to parse PDF {filename}: {e}")
            raise ValueError(f"Failed to parse PDF {filename}: {e}")
            
        combined_text = "\n\n".join(full_text)
        if not combined_text.strip():
            logger.warning("Extracted empty text from PDF")
            return []
            
        metadata = ChunkMetadata(source_file=filename, chunk_id="")
        return self.chunker.chunk_text(combined_text, metadata)

class TextProcessor:
    def __init__(self, chunker: ChunkerInterface):
        self.chunker = chunker
        
    def process(self, file_bytes: bytes, filename: str) -> List[DocumentChunk]:
        try:
            text = file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            # Fallback for ISO-8859-1 or other text formats
            text = file_bytes.decode('latin-1')
        
        metadata = ChunkMetadata(source_file=filename, chunk_id="")
        return self.chunker.chunk_text(text, metadata)

class L5XProcessor:
    def __init__(self, chunker: ChunkerInterface):
        self.chunker = chunker
        
    def process(self, file_bytes: bytes, filename: str) -> List[DocumentChunk]:
        # TODO: Implement L5X XML parsing
        text = f"PLC Logic from {filename}"
        metadata = ChunkMetadata(source_file=filename, chunk_id="")
        return self.chunker.chunk_text(text, metadata)

class ExcelProcessor:
    def __init__(self, chunker: ChunkerInterface):
        self.chunker = chunker

    def process(self, file_bytes: bytes, filename: str) -> List[DocumentChunk]:
        # TODO: Implement Excel parsing (e.g. using pandas/openpyxl)
        text = f"Tabular data from {filename}"
        metadata = ChunkMetadata(source_file=filename, chunk_id="")
        return self.chunker.chunk_text(text, metadata)
