import os
import time
import json
import logging
from pathlib import Path
from google import genai
from typing import List
from app.core.schemas import DocumentChunk, ChunkMetadata
from app.core.interfaces.chunker_interface import ChunkerInterface

logger = logging.getLogger(__name__)

class PDFProcessor:
    def __init__(self, chunker: ChunkerInterface, api_key: str):
        self.chunker = chunker
        self.api_key = api_key
        
    def process(self, file_bytes: bytes, filename: str) -> List[DocumentChunk]:
        if not self.api_key:
            logger.error("GEMINI_API_KEY is missing")
            raise ValueError("API key is required to process PDFs")
            
        client = genai.Client(api_key=self.api_key)
        
        logger.info(f"Uploading {filename} to Gemini...")
        
        # Write bytes to temp file because upload_file needs a path or fd
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
            
        try:
            uploaded_file = client.files.upload(file=tmp_path, config={'display_name': Path(filename).name})
        finally:
            os.unlink(tmp_path)
        
        MAX_WAIT_SECONDS = 30
        POLL_INTERVAL = 2
        elapsed = 0
        while uploaded_file.state.name == "PROCESSING":
            if elapsed >= MAX_WAIT_SECONDS:
                raise TimeoutError(f"Gemini file never became ACTIVE: {uploaded_file.name}")
            logger.info("Waiting for PDF to be processed by Gemini...")
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            uploaded_file = client.files.get(name=uploaded_file.name)
            
        if uploaded_file.state.name == "FAILED":
            client.files.delete(name=uploaded_file.name)
            raise RuntimeError("Gemini failed to process the PDF.")
            
        logger.info("Extracting chunks via Gemini...")
        prompt = (
            "Analyze this document. Extract the text and break it down into logical, coherent paragraphs or sections "
            "suitable for a vector database. Return ONLY a valid JSON array of strings, where each string represents a chunk of text. "
            "Do not include any markdown formatting or code blocks."
        )
        
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[uploaded_file, prompt],
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        try:
            raw_text = response.text or ""
            if not raw_text.strip():
                raise ValueError("Empty response from Gemini")
        except Exception as access_err:
            finish_reason = getattr(response.candidates[0].finish_reason, "name", str(response.candidates[0].finish_reason)) if response.candidates else "UNKNOWN"
            raise ValueError(f"Gemini returned no text content for PDF (finish_reason: {finish_reason}). Error: {access_err}")
            
        try:
            chunks_text = json.loads(raw_text.strip())
        except json.JSONDecodeError:
            logger.warning("Failed to decode JSON from Gemini, falling back to raw text")
            chunks_text = [raw_text.strip()]
            
        client.files.delete(name=uploaded_file.name)
        
        chunks = []
        for text_chunk in chunks_text:
            if not isinstance(text_chunk, str) or not text_chunk.strip():
                continue
            metadata = ChunkMetadata(source_file=filename, chunk_id="")
            chunks.extend(self.chunker.chunk_text(text_chunk.strip(), metadata))
            
        return chunks

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
