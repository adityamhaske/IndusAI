"""
Text / plain-text parser — sliding window chunking.

Handles: .txt, .md, .csv, and any other text file.
Window: 512 chars, overlap: 64 chars.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_WINDOW = 512
_OVERLAP = 64
_ENCODINGS = ["utf-8", "latin-1", "cp1252"]


@dataclass
class TextChunk:
    content: str
    char_offset: int
    source_file: str


@dataclass
class TextParseResult:
    chunks: list[TextChunk] = field(default_factory=list)
    source_file: str = ""
    char_count: int = 0
    warnings: list[str] = field(default_factory=list)


def parse(file_path: str | Path) -> TextParseResult:
    """
    Read a text file and return sliding-window chunks.
    Tries multiple encodings — never raises.
    """
    path = Path(file_path)
    result = TextParseResult(source_file=str(path))

    text: str | None = None
    for enc in _ENCODINGS:
        try:
            text = path.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, OSError):
            continue

    if text is None:
        result.warnings.append(f"Could not decode {path.name} with any known encoding.")
        return result

    # Normalise whitespace runs
    text = " ".join(text.split())
    result.char_count = len(text)

    if len(text) < 20:
        result.warnings.append(f"{path.name} is too short to chunk ({len(text)} chars).")
        return result

    pos = 0
    while pos < len(text):
        end = min(pos + _WINDOW, len(text))
        chunk_text = text[pos:end].strip()
        if chunk_text:
            result.chunks.append(TextChunk(
                content=chunk_text,
                char_offset=pos,
                source_file=str(path),
            ))
        if end == len(text):
            break
        pos += _WINDOW - _OVERLAP

    logger.debug("Text parsed: %s → %d chunks (%d chars)",
                 path.name, len(result.chunks), result.char_count)
    return result
