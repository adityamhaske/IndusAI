"""
TXT / Markdown / CSV text parser.

Uses fixed-size overlapping windows — no heading heuristics needed.
Each window becomes one DocumentChunk.
"""
import hashlib
import logging
from pathlib import Path
from typing import List

from app.core.schemas import ChunkMetadata, DocumentChunk

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 512          # characters per chunk
_OVERLAP = 64              # overlap between consecutive chunks
_MIN_CHUNK_CHARS = 40


def parse_text(file_path: str, project_id: str = "") -> List[DocumentChunk]:
    """
    Read a plain text / Markdown / CSV file and chunk it with overlap.
    Returns List[DocumentChunk].
    """
    path = Path(file_path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Cannot read text file %s: %s", file_path, exc)
        return []

    text = text.strip()
    if not text:
        return []

    chunks = _sliding_window(text, source=path.name, project_id=project_id)
    logger.info("TXT parsed: %s → %d chunks", path.name, len(chunks))
    return chunks


def _sliding_window(text: str, source: str, project_id: str) -> List[DocumentChunk]:
    """Split text into overlapping fixed-size windows."""
    chunks: List[DocumentChunk] = []
    start = 0
    idx = 0

    while start < len(text):
        end = min(start + _CHUNK_SIZE, len(text))
        content = text[start:end].strip()
        if len(content) >= _MIN_CHUNK_CHARS:
            cid = hashlib.md5(f"{source}:{idx}:{content[:30]}".encode()).hexdigest()[:16]
            chunks.append(DocumentChunk(
                content=content,
                metadata=ChunkMetadata(
                    source_file=source,
                    chunk_id=cid,
                    project_id=project_id or None,
                ),
            ))
        start += _CHUNK_SIZE - _OVERLAP
        idx += 1

    return chunks
