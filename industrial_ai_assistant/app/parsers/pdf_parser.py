"""
PDF Parser — chunks PDF content by headings for semantic indexing.

Uses pdfminer.six when available, falls back to pypdf.
Each detected heading starts a new chunk.
"""
import logging
import re
from pathlib import Path
from typing import List
import hashlib

from app.core.schemas import ChunkMetadata, DocumentChunk

logger = logging.getLogger(__name__)

# Heading detection regexes (ordered by priority)
_HEADING_PATTERNS = [
    re.compile(r"^\s*(?:\d+\.)+\s+[A-Z].{3,}$"),        # 1.2.3 Title
    re.compile(r"^\s*[A-Z][A-Z\s]{4,}$"),                # ALL CAPS HEADING
    re.compile(r"^\s*(?:Chapter|Section|Appendix)\s+\d+", re.IGNORECASE),
    re.compile(r"^\s*#{1,4}\s+.+"),                       # Markdown-style (in text-PDFs)
]
_MIN_CHUNK_CHARS = 80
_MAX_CHUNK_CHARS = 2000


def parse_pdf(file_path: str, project_id: str = "") -> List[DocumentChunk]:
    """
    Parse a PDF into heading-bounded DocumentChunks.

    Tries pdfminer.six first, falls back to pypdf.
    Returns an empty list (logs warning) if neither is installed.
    """
    path = Path(file_path)
    text = _extract_text(file_path)
    if not text:
        logger.warning("PDF extraction yielded no text: %s", path.name)
        return []

    chunks = _chunk_by_headings(text, source=path.name, project_id=project_id)
    logger.info("PDF parsed: %s → %d chunks", path.name, len(chunks))
    return chunks


def _extract_text(file_path: str) -> str:
    """Try pdfminer.six, then pypdf, then return empty string."""
    # ── pdfminer.six (preferred — better layout handling) ─────────────────────
    try:
        from pdfminer.high_level import extract_text as pm_extract
        return pm_extract(file_path)
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("pdfminer failed on %s: %s", file_path, exc)

    # ── pypdf fallback ────────────────────────────────────────────────────────
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        return "\n".join(parts)
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("pypdf failed on %s: %s", file_path, exc)

    logger.error(
        "No PDF library installed. Run: pip install pdfminer.six  OR  pip install pypdf"
    )
    return ""


def _chunk_by_headings(text: str, source: str, project_id: str) -> List[DocumentChunk]:
    lines = text.splitlines()
    chunks: List[DocumentChunk] = []
    current_title = "Introduction"
    current_lines: List[str] = []

    def _flush(title: str, lines: List[str]):
        content = "\n".join(lines).strip()
        if len(content) < _MIN_CHUNK_CHARS:
            return
        content = content[:_MAX_CHUNK_CHARS]
        cid = hashlib.md5(f"{source}:{title}:{content[:40]}".encode()).hexdigest()[:16]
        chunks.append(DocumentChunk(
            content=content,
            metadata=ChunkMetadata(
                source_file=source,
                section_title=title,
                chunk_id=cid,
                project_id=project_id or None,
            ),
        ))

    for line in lines:
        if _is_heading(line):
            _flush(current_title, current_lines)
            current_title = line.strip().lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    _flush(current_title, current_lines)
    return chunks


def _is_heading(line: str) -> bool:
    stripped = line.rstrip()
    return any(p.match(stripped) for p in _HEADING_PATTERNS)
