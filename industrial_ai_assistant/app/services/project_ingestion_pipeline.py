"""
ProjectIngestionPipeline — walks a project folder and populates
StructuredIndex + SemanticIndex.

Concurrency guard:
  asyncio.Lock per project_id — raises IngestionLockError if lock held.

File routing:
  .L5X / .l5x   → L5XParser    → StructuredIndex (tags, routines, AOIs)
                                 + SemanticIndex   (routine snippets)
  .xlsx / .xls   → ExcelParser  → StructuredIndex (IO rows)
                                 + SemanticIndex   (IO summaries)
  .pdf           → PdfParser    → SemanticIndex
  .txt/.md/.csv  → TextParser   → SemanticIndex
  binary/unknown → SKIP (logged)
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from pathlib import Path

from app.core.project_exceptions import IngestionLockError
from app.indexes.semantic_index import get_semantic_index
from app.indexes.structured_index import clear_structured_index, get_structured_index
from app.models.project_models import (
    IngestionResult,
    SemanticChunk,
    StructuredHit,
)
from app.parsers import excel_parser, l5x_parser, pdf_parser, text_parser
from app.services.project_context_manager import get_project_context_manager

logger = logging.getLogger(__name__)

# Extensions skipped entirely (binaries, build artifacts)
_SKIP_EXTENSIONS = {
    ".exe", ".dll", ".pdb", ".obj", ".bin", ".pyc", ".so", ".class",
    ".zip", ".tar", ".gz", ".rar", ".7z", ".db", ".sqlite", ".bak",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".eot", ".ttf", ".woff", ".woff2",
}
_SKIP_DIRS = {"venv", ".venv", "__pycache__", ".git", "node_modules", "dist", "build"}

# Extension → file_type tag stored in SemanticIndex
_TYPE_MAP = {
    ".l5x": "l5x", ".xlsx": "excel", ".xls": "excel",
    ".pdf": "pdf",
    ".txt": "txt", ".md": "txt", ".csv": "txt",
}

# asyncio lock registry
_locks: dict[str, asyncio.Lock] = {}
_lock_registry_lock = asyncio.Lock()


async def _get_lock(project_id: str) -> asyncio.Lock:
    async with _lock_registry_lock:
        if project_id not in _locks:
            _locks[project_id] = asyncio.Lock()
        return _locks[project_id]


class ProjectIngestionPipeline:
    """Orchestrates full project ingestion with concurrency guard."""

    async def ingest(self, folder_path: str, project_id: str) -> IngestionResult:
        """
        Entry point. Returns IngestionResult.
        Raises IngestionLockError if already running for this project.
        """
        lock = await _get_lock(project_id)
        if lock.locked():
            raise IngestionLockError(project_id)

        async with lock:
            return await self._run_ingestion(folder_path, project_id)

    async def _run_ingestion(self, folder_path: str, project_id: str) -> IngestionResult:
        ctx = get_project_context_manager()
        t0 = time.perf_counter()

        # Register folder + compute hash (raises ValueError if bad path)
        ctx.set_project(folder_path, project_id)
        ctx.mark_indexing(project_id)

        result = IngestionResult(
            project_id=project_id,
            project_hash=ctx.get_status(project_id).project_hash,
            folder=folder_path,
        )

        # Clear previous indexes
        clear_structured_index(project_id)
        si = get_structured_index(project_id)
        sem = get_semantic_index()
        sem.delete_project(project_id)

        folder = Path(folder_path)
        all_files = _collect_files(folder)
        result.files_scanned = len(all_files)

        for file_path in all_files:
            ext = file_path.suffix.lower()
            try:
                if ext in (".l5x",):
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._ingest_l5x, file_path, project_id, si, sem, result
                    )
                elif ext in (".xlsx", ".xls"):
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._ingest_excel, file_path, project_id, si, sem, result
                    )
                elif ext == ".pdf":
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._ingest_pdf, file_path, project_id, sem, result
                    )
                elif ext in (".txt", ".md", ".csv"):
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._ingest_text, file_path, project_id, sem, result
                    )
                else:
                    result.files_skipped += 1
                    continue

                result.files_indexed += 1

            except Exception as exc:
                msg = f"Failed to ingest {file_path.name}: {exc}"
                logger.error(msg, exc_info=True)
                result.errors.append(msg)
                result.files_failed += 1

        # Size warnings
        si_stats = si.stats()
        result.warnings.extend(si_stats.warnings)
        if si_stats.at_capacity:
            result.warnings.append(
                f"StructuredIndex at capacity. Some records were dropped."
            )

        result.duration_ms = (time.perf_counter() - t0) * 1000
        ctx.mark_ready(project_id, result)

        logger.info(
            "[%s] Ingestion complete: %d files, %d tags, %d routines, "
            "%d IO rows, %d chunks in %.0fms",
            project_id, result.files_indexed, result.tags_indexed,
            result.routines_indexed, result.io_rows_indexed,
            result.semantic_chunks_indexed, result.duration_ms,
        )
        return result

    # ── Per-type handlers ──────────────────────────────────────────────────────

    def _ingest_l5x(self, path: Path, project_id: str, si, sem, result: IngestionResult):
        parsed = l5x_parser.parse(path)
        result.warnings.extend(parsed.warnings)

        for tag in parsed.tags:
            si.add_tag(tag)
            result.tags_indexed += 1

        for rtn in parsed.routines:
            si.add_routine(rtn)
            result.routines_indexed += 1
            # Also add routine content to semantic for "explain routine" queries
            if rtn.content_snippet:
                chunk = _make_chunk(
                    f"{rtn.content_snippet} [Routine: {rtn.name}]",
                    str(path), rtn.name, "l5x", project_id
                )
                sem.upsert_chunks([chunk], project_id)
                result.semantic_chunks_indexed += 1

        for aoi in parsed.aois:
            si.add_aoi(aoi)

    def _ingest_excel(self, path: Path, project_id: str, si, sem, result: IngestionResult):
        parsed = excel_parser.parse(path)
        result.warnings.extend(parsed.warnings)

        for io in parsed.io_rows:
            si.add_io(io)
            result.io_rows_indexed += 1
            # Semantic chunk: one sentence per IO row for keyword matching
            text = f"Slot {io.slot} Rack {io.rack} Module {io.module}: {io.description} Tag={io.tag_name}"
            chunk = _make_chunk(text, str(path), f"IO Slot {io.slot}", "excel", project_id)
            sem.upsert_chunks([chunk], project_id)
            result.semantic_chunks_indexed += 1

    def _ingest_pdf(self, path: Path, project_id: str, sem, result: IngestionResult):
        parsed = pdf_parser.parse(path)
        result.warnings.extend(parsed.warnings)
        chunks = [
            _make_chunk(c.content, str(path), c.title, "pdf", project_id, page=c.page)
            for c in parsed.chunks
        ]
        if chunks:
            sem.upsert_chunks(chunks, project_id)
            result.semantic_chunks_indexed += len(chunks)

    def _ingest_text(self, path: Path, project_id: str, sem, result: IngestionResult):
        parsed = text_parser.parse(path)
        result.warnings.extend(parsed.warnings)
        chunks = [
            _make_chunk(c.content, str(path), path.stem, "txt", project_id)
            for c in parsed.chunks
        ]
        if chunks:
            sem.upsert_chunks(chunks, project_id)
            result.semantic_chunks_indexed += len(chunks)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _collect_files(folder: Path) -> list[Path]:
    """Recursively collect all processable files, skipping excluded dirs."""
    files: list[Path] = []
    try:
        for item in folder.rglob("*"):
            if item.is_file():
                if any(part in _SKIP_DIRS for part in item.parts):
                    continue
                if item.suffix.lower() in _SKIP_EXTENSIONS:
                    continue
                files.append(item)
    except PermissionError as exc:
        logger.warning("Permission error during file walk: %s", exc)
    return files


def _make_chunk(
    content: str, source_file: str, section_title: str,
    file_type: str, project_id: str, page: int = 0,
) -> SemanticChunk:
    cid_raw = f"{project_id}:{source_file}:{section_title}:{content[:32]}"
    chunk_id = hashlib.sha1(cid_raw.encode()).hexdigest()
    return SemanticChunk(
        chunk_id=chunk_id,
        content=content,
        source_file=source_file,
        section_title=section_title,
        file_type=file_type,
        page=page,
        project_id=project_id,
    )


# ── Singleton ──────────────────────────────────────────────────────────────────

_pipeline: ProjectIngestionPipeline | None = None


def get_ingestion_pipeline() -> ProjectIngestionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ProjectIngestionPipeline()
    return _pipeline
