"""
PDF parser — chunks by heading for industrial documentation.

Uses pdfplumber (already in requirements.txt).
Heading detection: ALL CAPS lines, lines ending with ':', or lines
whose word count ≤ 6 and are preceded by a blank line.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_CHUNK_CHARS = 800
_MIN_CHUNK_CHARS = 40   # discard too-short fragments


@dataclass
class PdfChunk:
    title: str
    content: str
    page: int
    source_file: str


@dataclass
class PdfParseResult:
    chunks: list[PdfChunk] = field(default_factory=list)
    source_file: str = ""
    page_count: int = 0
    warnings: list[str] = field(default_factory=list)


def parse(file_path: str | Path) -> PdfParseResult:
    """
    Parse a PDF into heading-chunked text blocks.
    Never raises — returns warnings in result.
    """
    try:
        import pdfplumber
    except ImportError:
        return PdfParseResult(
            source_file=str(file_path),
            warnings=["pdfplumber not installed — PDF parsing skipped."],
        )

    path = Path(file_path)
    result = PdfParseResult(source_file=str(path))

    try:
        pdf = pdfplumber.open(path)
    except Exception as exc:
        result.warnings.append(f"Cannot open PDF {path.name}: {exc}")
        return result

    with pdf:
        result.page_count = len(pdf.pages)
        current_heading = path.stem       # default heading = filename
        current_lines: list[str] = []
        current_page = 1

        for page in pdf.pages:
            text = page.extract_text() or ""
            page_num = page.page_number

            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue

                if _is_heading(line):
                    # Flush current chunk
                    _flush(result.chunks, current_heading,
                           current_lines, current_page, str(path))
                    current_heading = line
                    current_lines = []
                    current_page = page_num
                else:
                    current_lines.append(line)

                    # Auto-split long accumulations
                    if sum(len(l) for l in current_lines) >= _MAX_CHUNK_CHARS:
                        _flush(result.chunks, current_heading,
                               current_lines, current_page, str(path))
                        current_lines = []

            current_page = page_num

        _flush(result.chunks, current_heading, current_lines, current_page, str(path))

    logger.debug("PDF parsed: %s → %d chunks across %d pages",
                 path.name, len(result.chunks), result.page_count)
    return result


def _is_heading(line: str) -> bool:
    """
    True if the line looks like a section heading.
    Heuristics (ordered by reliability):
      1. All uppercase and mixed ≥ 3 chars
      2. Line ends with ':'
      3. Numbered section pattern like '1.2.3 Title'
    """
    stripped = line.strip(".\t ")
    if len(stripped) < 3:
        return False

    if re.match(r"^[A-Z0-9 /,\-]+$", stripped) and len(stripped) <= 80:
        return True

    if stripped.endswith(":") and len(stripped.split()) <= 8:
        return True

    if re.match(r"^\d+(\.\d+)*\s+[A-Z]", stripped) and len(stripped.split()) <= 10:
        return True

    return False


def _flush(
    chunks: list[PdfChunk],
    heading: str,
    lines: list[str],
    page: int,
    source: str,
) -> None:
    content = " ".join(lines).strip()
    if len(content) < _MIN_CHUNK_CHARS:
        return
    # Split into sub-chunks if still too large
    while len(content) > _MAX_CHUNK_CHARS:
        chunks.append(PdfChunk(
            title=heading,
            content=content[:_MAX_CHUNK_CHARS],
            page=page,
            source_file=source,
        ))
        content = content[_MAX_CHUNK_CHARS - 50:]   # 50-char overlap
    if content:
        chunks.append(PdfChunk(title=heading, content=content, page=page, source_file=source))
