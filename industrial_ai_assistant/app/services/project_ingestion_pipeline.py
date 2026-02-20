"""
ProjectIngestionPipeline — Walks a project folder and populates indexes.

Design:
  - threading.Lock per project_id (409 if already ingesting)
  - File classification by extension → typed parsers
  - Structured artifacts → StructuredIndex
  - Semantic chunks → SemanticIndex
  - Full metrics: files_indexed, failed, tags, routines, chunks, duration_s, errors
  - Never silently swallows failures at file level; logs every error
"""
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from app.core.project_exceptions import IngestionAlreadyRunningError
from app.indexes.semantic_index import get_semantic_index
from app.indexes.structured_index import get_structured_index
from app.models.project_models import IngestionResult

logger = logging.getLogger(__name__)

# ── Path exclusion patterns ───────────────────────────────────────────────────
_SKIP_DIRS = {"__pycache__", ".git", "node_modules", "venv", ".venv",
              "dist", "build", ".pytest_cache", ".idea", ".vscode"}

_SKIP_SUFFIXES = {".pyc", ".pyo", ".class", ".o", ".bin",
                  ".exe", ".dll", ".so", ".dylib", ".db", ".sqlite",
                  ".zip", ".tar", ".gz", ".bz2", ".rar", ".7z",
                  ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico",
                  ".mp4", ".avi", ".mov", ".mp3", ".wav"}

# ── File type classification ──────────────────────────────────────────────────
_L5X_EXTS  = {".l5x"}
_EXCEL_EXTS = {".xlsx", ".xls"}
_PDF_EXTS   = {".pdf"}
_TEXT_EXTS  = {".txt", ".md", ".rst", ".csv"}


class ProjectIngestionPipeline:
    """Ingests a project folder into StructuredIndex + SemanticIndex."""

    def __init__(self):
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_lock(self, project_id: str) -> threading.Lock:
        with self._global_lock:
            if project_id not in self._locks:
                self._locks[project_id] = threading.Lock()
            return self._locks[project_id]

    def ingest(self, folder_path: str, project_id: str) -> IngestionResult:
        """
        Full ingestion pipeline.
        Raises IngestionAlreadyRunningError(409) if already running for this project.
        """
        lock = self._get_lock(project_id)
        if not lock.acquire(blocking=False):
            raise IngestionAlreadyRunningError(project_id)

        t0 = time.perf_counter()
        result = IngestionResult(
            project_id=project_id,
            folder=folder_path,
            project_hash="",
        )

        try:
            from app.services.project_context_manager import get_project_context_manager
            ctx = get_project_context_manager()
            ph, fc = ctx.set_project(folder_path, project_id)
            result.project_hash = ph
            result.files_scanned = fc

            # Reset existing indexes
            get_structured_index(project_id).clear()
            get_semantic_index().delete_project(project_id)

            # Walk and ingest
            folder = Path(folder_path)
            self._walk(folder, project_id, result)

            result.duration_s = round(time.perf_counter() - t0, 2)
            ctx.mark_ingested(project_id, result)

            logger.info(
                "Ingestion complete: project=%s files=%d tags=%d routines=%d chunks=%d errors=%d %.1fs",
                project_id, result.files_indexed, result.tags_indexed,
                result.routines_indexed, result.semantic_chunks,
                result.files_failed, result.duration_s,
            )
        except Exception as exc:
            result.errors.append(f"Pipeline fatal error: {exc}")
            logger.exception("Ingestion fatal error for project '%s'", project_id)
        finally:
            lock.release()

        return result

    def _walk(self, folder: Path, project_id: str, result: IngestionResult) -> None:
        """Recursively walk folder, classify files, dispatch to parsers."""
        s_idx = get_structured_index(project_id)
        sem_idx = get_semantic_index()

        for path in sorted(folder.rglob("*")):
            if path.is_dir():
                if path.name in _SKIP_DIRS:
                    continue
                continue

            if not path.is_file():
                continue

            # Skip hidden and excluded suffixes
            if path.name.startswith("."):
                continue
            if path.suffix.lower() in _SKIP_SUFFIXES:
                continue
            if any(part in _SKIP_DIRS for part in path.parts):
                continue

            ext = path.suffix.lower()
            try:
                if ext in _L5X_EXTS:
                    self._ingest_l5x(path, project_id, s_idx, sem_idx, result)
                elif ext in _EXCEL_EXTS:
                    self._ingest_excel(path, project_id, s_idx, sem_idx, result)
                elif ext in _PDF_EXTS:
                    self._ingest_pdf(path, project_id, sem_idx, result)
                elif ext in _TEXT_EXTS:
                    self._ingest_text(path, project_id, sem_idx, result)
                else:
                    logger.debug("Skipping unsupported file type: %s", path.name)
                    continue

                result.files_indexed += 1
            except Exception as exc:
                err = f"{path.relative_to(folder)}: {exc}"
                result.errors.append(err)
                result.files_failed += 1
                logger.warning("Ingestion error — %s", err)

    def _ingest_l5x(self, path, project_id, s_idx, sem_idx, result):
        from app.parsers import l5x_parser
        tags, routines, aois = l5x_parser.parse(path)
        s_idx.load_tags(tags)
        s_idx.load_routines(routines)
        s_idx.load_aois(aois)
        result.tags_indexed += len(tags)
        result.routines_indexed += len(routines)
        result.aois_indexed += len(aois)

        # Also index routine content semantically
        from app.models.project_models import SemanticChunk
        chunks = [
            SemanticChunk(
                chunk_id=f"l5x_{r.program}_{r.name}",
                project_id=project_id,
                content=f"Routine: {r.name} (Program: {r.program})\n{r.content[:800]}",
                source_file=str(path),
                section_title=f"{r.program}.{r.name}",
                file_type="l5x",
            )
            for r in routines if r.content
        ]
        if chunks:
            n = sem_idx.upsert_chunks(project_id, chunks)
            result.semantic_chunks += n

    def _ingest_excel(self, path, project_id, s_idx, sem_idx, result):
        from app.parsers import excel_parser
        io_records = excel_parser.parse(path)
        s_idx.load_io(io_records)
        result.io_rows_indexed += len(io_records)

        # Semantic: one chunk per IO table
        from app.models.project_models import SemanticChunk
        if io_records:
            summary = "\n".join(
                f"Slot {r.slot} Rack {r.rack}: {r.module} — {r.description} [{r.tag_name}]"
                for r in io_records[:100]
            )
            chunk = SemanticChunk(
                chunk_id=f"excel_{path.stem}",
                project_id=project_id,
                content=summary,
                source_file=str(path),
                section_title=path.stem,
                file_type="excel",
            )
            n = sem_idx.upsert_chunks(project_id, [chunk])
            result.semantic_chunks += n

    def _ingest_pdf(self, path, project_id, sem_idx, result):
        from app.parsers import pdf_parser
        chunks = pdf_parser.parse(path, project_id)
        if chunks:
            n = sem_idx.upsert_chunks(project_id, chunks)
            result.semantic_chunks += n

    def _ingest_text(self, path, project_id, sem_idx, result):
        from app.parsers import text_parser
        chunks = text_parser.parse(path, project_id)
        if chunks:
            n = sem_idx.upsert_chunks(project_id, chunks)
            result.semantic_chunks += n


# ── Singleton ─────────────────────────────────────────────────────────────────
_pipeline: Optional[ProjectIngestionPipeline] = None


def get_ingestion_pipeline() -> ProjectIngestionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ProjectIngestionPipeline()
    return _pipeline
