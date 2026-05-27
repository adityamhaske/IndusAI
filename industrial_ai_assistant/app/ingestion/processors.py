import os
import time
import json
import logging
from pathlib import Path
import google.generativeai as genai
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
            
        genai.configure(api_key=self.api_key)
        
        logger.info(f"Uploading {filename} to Gemini...")
        
        # Write bytes to temp file because upload_file needs a path or fd
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
            
        try:
            uploaded_file = genai.upload_file(path=tmp_path, display_name=Path(filename).name)
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
            uploaded_file = genai.get_file(uploaded_file.name)
            
        if uploaded_file.state.name == "FAILED":
            genai.delete_file(uploaded_file.name)
            raise RuntimeError("Gemini failed to process the PDF.")
            
        logger.info("Extracting chunks via Gemini 2.5 Flash...")
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = (
            "Analyze this document. Extract the text and break it down into logical, coherent paragraphs or sections "
            "suitable for a vector database. Return ONLY a valid JSON array of strings, where each string represents a chunk of text. "
            "Do not include any markdown formatting or code blocks."
        )
        response = model.generate_content([uploaded_file, prompt])
        
        try:
            raw_text = response.text.strip()
        except Exception as access_err:
            if response.candidates and response.candidates[0].content.parts:
                raw_text = "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text')).strip()
            else:
                finish_reason = response.candidates[0].finish_reason.name if response.candidates else "UNKNOWN"
                raise ValueError(f"Gemini returned no text content for PDF (finish_reason: {finish_reason}). Error: {access_err}")
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        try:
            chunks_text = json.loads(raw_text.strip())
        except json.JSONDecodeError:
            logger.warning("Failed to decode JSON from Gemini, falling back to raw text")
            chunks_text = [raw_text.strip()]
            
        genai.delete_file(uploaded_file.name)
        
        chunks = []
        for text_chunk in chunks_text:
            if not isinstance(text_chunk, str) or not text_chunk.strip():
                continue
            metadata = ChunkMetadata(source_file=filename, chunk_id="")
            chunks.extend(self.chunker.chunk_text(text_chunk.strip(), metadata))
            
        return chunks

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
