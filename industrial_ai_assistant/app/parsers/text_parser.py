"""
Text Parser — plain text, Markdown, CSV files.

Uses a sliding window (800 chars, 200 overlap) to produce SemanticChunks.
"""
import logging
from pathlib import Path
from typing import List

from app.models.project_models import SemanticChunk

logger = logging.getLogger(__name__)

_WINDOW = 800
_OVERLAP = 200
_ENCODINGS = ("utf-8", "latin-1", "cp1252")


def parse(path: str | Path, project_id: str = "default") -> List[SemanticChunk]:
    """
    Read a text file and produce overlapping SemanticChunks.

    Returns:
        List of SemanticChunk.
    Raises:
        ValueError if file cannot be decoded.
    """
    source = str(path)
    text = _read_text(source)

    chunks: List[SemanticChunk] = []
    stem = Path(source).stem
    start = 0
    idx = 0
    while start < len(text):
        end = start + _WINDOW
        content = text[start:end].strip()
        if content:
            chunks.append(SemanticChunk(
                chunk_id=f"{stem}_{idx}",
                project_id=project_id,
                content=content,
                source_file=source,
                section_title="",
                file_type="txt",
                char_offset=start,
            ))
            idx += 1
        start += _WINDOW - _OVERLAP

    logger.debug("Text %s → %d chunks", Path(source).name, len(chunks))
    return chunks


def _read_text(source: str) -> str:
    for enc in _ENCODINGS:
        try:
            with open(source, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError(f"Could not decode {source} with encodings {_ENCODINGS}")
