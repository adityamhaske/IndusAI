"""
PDF Parser — Extracts sections from engineering PDFs.

Strategy:
  - Use pdfplumber for text extraction page-by-page
  - Detect headings using ALL_CAPS or short-line + title-case heuristics
  - Chunk by heading; max 1200 chars with 150-char overlap
  - Returns [{title, content, page, source_file}]
"""
import logging
import re
from pathlib import Path
from typing import List

from app.models.project_models import SemanticChunk

logger = logging.getLogger(__name__)

_MAX_CHUNK_CHARS = 1_200
_OVERLAP_CHARS = 150
_MIN_HEADING_WORDS = 2
_MAX_HEADING_WORDS = 12


def parse(path: str | Path, project_id: str = "default") -> List[SemanticChunk]:
    """
    Parse a PDF into heading-chunked SemanticChunks.

    Returns:
        List of SemanticChunk — one per section/chunk.
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError("pdfplumber is required: pip install pdfplumber") from exc

    source = str(path)
    chunks: List[SemanticChunk] = []

    try:
        with pdfplumber.open(source) as pdf:
            sections: List[dict] = []   # [{title, content, page}]
            current_title = "Introduction"
            current_content: List[str] = []
            current_page = 1

            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if _is_heading(stripped):
                        # Save current section
                        if current_content:
                            sections.append({
                                "title": current_title,
                                "content": " ".join(current_content),
                                "page": current_page,
                            })
                        current_title = stripped
                        current_content = []
                        current_page = page.page_number
                    else:
                        current_content.append(stripped)

            # Flush last section
            if current_content:
                sections.append({
                    "title": current_title,
                    "content": " ".join(current_content),
                    "page": current_page,
                })

        # Split long sections into overlapping chunks
        for section in sections:
            sub_chunks = _split_to_chunks(section["content"], _MAX_CHUNK_CHARS, _OVERLAP_CHARS)
            for i, text in enumerate(sub_chunks):
                chunk_id = f"{Path(source).stem}_{section['page']}_{i}"
                chunks.append(SemanticChunk(
                    chunk_id=chunk_id,
                    project_id=project_id,
                    content=text,
                    source_file=source,
                    section_title=section["title"],
                    file_type="pdf",
                    page=section["page"],
                ))

    except Exception as exc:
        raise ValueError(f"PDF parse error for {source}: {exc}") from exc

    logger.debug("PDF %s → %d chunks", Path(source).name, len(chunks))
    return chunks


# ── Helpers ───────────────────────────────────────────────────────────────────

_SECTION_NUM_RE = re.compile(r"^\d+(\.\d+)*\s+\w")  # "3.2 Section Title"


def _is_heading(line: str) -> bool:
    """Heuristically detect heading lines."""
    words = line.split()
    n = len(words)
    if n < _MIN_HEADING_WORDS or n > _MAX_HEADING_WORDS:
        return False
    if line.isupper() and n <= 8:
        return True
    if _SECTION_NUM_RE.match(line):
        return True
    # Title case (most words capitalize)
    upper_words = sum(1 for w in words if w and w[0].isupper())
    return upper_words >= max(2, n // 2) and not line.endswith(".")


def _split_to_chunks(text: str, max_chars: int, overlap: int) -> List[str]:
    """Split long text into overlapping fixed-size chunks."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunks.append(text[start:end])
        start += max_chars - overlap
    return chunks
