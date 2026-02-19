"""
ProjectIngestionPipeline — walks a folder tree and ingests all supported file types.

File routing:
  .l5x            → L5X parser → StructuredIndex (tags/routines/aois) + SemanticIndex
  .xlsx / .xls    → Excel parser → StructuredIndex (IO) + SemanticIndex
  .pdf            → PDF parser → SemanticIndex only
  .txt / .md      → TXT parser → SemanticIndex only
  .csv            → TXT parser → SemanticIndex only
  anything else   → skipped (warning logged)

Design:
  - File-level errors are caught, logged, and stored in context manager
  - Pipeline continues on single file failure
  - Ingestion status transitions: RUNNING → COMPLETE (or FAILED on catastrophic error)
  - Returns aggregated FileIngestionResult list
"""
from __future__ import annotations

import logging
import os
import time
from typing import List

from app.indexes.semantic_index import SemanticIndex
from app.indexes.structured_index import StructuredIndexStore
from app.models.project_models import FileIngestionResult
from app.parsers.excel_parser import excel_to_text, parse_excel_io
from app.parsers.l5x_parser import l5x_to_text_chunks, parse_l5x
from app.parsers.pdf_parser import parse_pdf
from app.parsers.txt_parser import parse_text
from app.services.project_context_manager import ProjectContextManager

logger = logging.getLogger(__name__)

_SUPPORTED_EXT = {".l5x", ".xlsx", ".xls", ".pdf", ".txt", ".md", ".csv"}


def ingest_project(
    project_id: str,
    folder_path: str,
    context_manager: ProjectContextManager,
    struct_store: StructuredIndexStore,
    semantic_index: SemanticIndex,
) -> List[FileIngestionResult]:
    """
    Main entry point — walk folder, classify files, parse, index, return results.
    """
    context_manager.mark_running(project_id)
    struct_idx = struct_store.get_or_create(project_id)
    results: List[FileIngestionResult] = []

    try:
        for root, dirs, files in os.walk(folder_path):
            # Skip hidden directories and common build artefacts
            dirs[:] = [
                d for d in sorted(dirs)
                if not d.startswith(".") and d not in {"__pycache__", "node_modules", "venv"}
            ]
            for filename in sorted(files):
                ext = os.path.splitext(filename)[1].lower()
                if ext not in _SUPPORTED_EXT:
                    continue

                file_path = os.path.join(root, filename)
                t_start = time.perf_counter()
                result = _ingest_file(file_path, ext, project_id, struct_idx, semantic_index, context_manager)
                result.duration_ms = round((time.perf_counter() - t_start) * 1000, 1)
                results.append(result)

    except Exception as exc:
        msg = f"Fatal ingestion error: {exc}"
        logger.exception(msg)
        context_manager.mark_failed(project_id, msg)
        return results

    # Aggregate metrics
    metrics = {
        "files_indexed": sum(1 for r in results if r.success),
        "tags_indexed": struct_idx.tags.count(),
        "routines_indexed": struct_idx.routines.count(),
        "aois_indexed": struct_idx.aois.count(),
        "io_rows_indexed": struct_idx.io.count(),
        "semantic_chunks": sum(r.semantic_chunks for r in results),
    }
    context_manager.mark_complete(project_id, metrics)

    logger.info(
        "Ingestion complete: project=%s files=%d tags=%d routines=%d io=%d chunks=%d",
        project_id,
        metrics["files_indexed"],
        metrics["tags_indexed"],
        metrics["routines_indexed"],
        metrics["io_rows_indexed"],
        metrics["semantic_chunks"],
    )
    return results


# ── Per-file ingestion ────────────────────────────────────────────────────────

def _ingest_file(
    file_path: str,
    ext: str,
    project_id: str,
    struct_idx,
    semantic_index: SemanticIndex,
    context_manager: ProjectContextManager,
) -> FileIngestionResult:
    result = FileIngestionResult(file_path=file_path, file_type=ext, success=False)

    try:
        if ext == ".l5x":
            result = _ingest_l5x(file_path, project_id, struct_idx, semantic_index, result)
        elif ext in (".xlsx", ".xls"):
            result = _ingest_excel(file_path, project_id, struct_idx, semantic_index, result)
        elif ext == ".pdf":
            result = _ingest_pdf(file_path, project_id, semantic_index, result)
        else:
            result = _ingest_text(file_path, project_id, semantic_index, result)

        result.success = True
        logger.info("Ingested: %s (type=%s)", os.path.basename(file_path), ext)

    except Exception as exc:
        result.error = str(exc)
        context_manager.add_error(project_id, f"{os.path.basename(file_path)}: {exc}")
        logger.warning("Failed to ingest %s: %s", file_path, exc)

    return result


def _ingest_l5x(file_path, project_id, struct_idx, semantic_index, result):
    tags, routines, aois = parse_l5x(file_path)
    struct_idx.tags.add_batch(tags)
    struct_idx.routines.add_batch(routines)
    struct_idx.aois.add_batch(aois)
    result.tags_extracted = len(tags)
    result.routines_extracted = len(routines)
    result.aois_extracted = len(aois)

    # Also index text representation semantically
    from app.core.schemas import ChunkMetadata, DocumentChunk
    import hashlib
    text = l5x_to_text_chunks(tags, routines, aois)
    if text.strip():
        cid = hashlib.md5(f"{file_path}:l5x_text".encode()).hexdigest()[:16]
        chunk = DocumentChunk(
            content=text[:4000],
            metadata=ChunkMetadata(
                source_file=os.path.basename(file_path),
                section_title="L5X Project Data",
                chunk_id=cid,
                project_id=project_id,
            ),
        )
        result.semantic_chunks = semantic_index.index_chunks(project_id, [chunk])
    return result


def _ingest_excel(file_path, project_id, struct_idx, semantic_index, result):
    records = parse_excel_io(file_path)
    struct_idx.io.add_batch(records)
    result.io_rows_extracted = len(records)

    # Text representation
    from app.core.schemas import ChunkMetadata, DocumentChunk
    import hashlib
    from app.parsers.excel_parser import excel_to_text
    text = excel_to_text(records)
    if text.strip():
        cid = hashlib.md5(f"{file_path}:io_text".encode()).hexdigest()[:16]
        chunk = DocumentChunk(
            content=text[:4000],
            metadata=ChunkMetadata(
                source_file=os.path.basename(file_path),
                section_title="IO Assignment",
                chunk_id=cid,
                project_id=project_id,
            ),
        )
        result.semantic_chunks = semantic_index.index_chunks(project_id, [chunk])
    return result


def _ingest_pdf(file_path, project_id, semantic_index, result):
    chunks = parse_pdf(file_path, project_id=project_id)
    result.semantic_chunks = semantic_index.index_chunks(project_id, chunks)
    return result


def _ingest_text(file_path, project_id, semantic_index, result):
    chunks = parse_text(file_path, project_id=project_id)
    result.semantic_chunks = semantic_index.index_chunks(project_id, chunks)
    return result
