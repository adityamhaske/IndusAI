"""
ProjectIngestionPipeline — processes files from Firebase Storage directly.
"""
import asyncio
import logging
import time
from pathlib import Path

from app.core.project_exceptions import IngestionLockError
from app.models.project_models import IngestionResult
from app.core.firebase import get_storage_bucket
from app.chunking.semantic_chunker import SemanticChunker
from app.ingestion.processors import PDFProcessor, L5XProcessor, ExcelProcessor
from app.vector_store.qdrant_store import user_collection_name
from app.services.user_settings_service import UserSettingsService

logger = logging.getLogger(__name__)

_locks: dict[str, asyncio.Lock] = {}
_lock_registry_lock = asyncio.Lock()


async def _get_lock(project_id: str) -> asyncio.Lock:
    async with _lock_registry_lock:
        if project_id not in _locks:
            _locks[project_id] = asyncio.Lock()
        return _locks[project_id]


class ProjectIngestionPipeline:
    """Orchestrates full project ingestion with concurrency guard from Firebase Storage."""

    async def ingest(self, uploaded_blob_paths: list[str], project_id: str, uid: str, progress_callback=None) -> IngestionResult:
        lock = await _get_lock(project_id)
        if lock.locked():
            raise IngestionLockError(project_id)

        async with lock:
            return await self._run_ingestion(uploaded_blob_paths, project_id, uid, progress_callback)

    async def _run_ingestion(self, uploaded_blob_paths: list[str], project_id: str, uid: str, progress_callback=None) -> IngestionResult:
        t0 = time.perf_counter()

        from app.config.dependency_injection import get_container
        container = get_container()
        qdrant_store = container._vector_store

        from app.embeddings.embedder_factory import get_embedder_for_user
        embedder = get_embedder_for_user(uid)

        svc = UserSettingsService()
        api_key = svc.get_raw_key(uid, "llm_api_key_enc") or ""

        chunker = SemanticChunker()
        processors = {
            "pdf": PDFProcessor(chunker=chunker, api_key=api_key),
            "l5x": L5XProcessor(chunker=chunker),
            "xlsx": ExcelProcessor(chunker=chunker),
            "xls": ExcelProcessor(chunker=chunker),
        }

        result = IngestionResult(
            project_id=project_id,
            project_hash=f"job_{int(time.time())}",
            folder="firebase_storage",
        )

        collection_name = user_collection_name(uid)
        if qdrant_store:
            qdrant_store.ensure_collection(collection_name)

        bucket = get_storage_bucket()
        total_files = len(uploaded_blob_paths)
        processed_count = 0

        for blob_path in uploaded_blob_paths:
            processed_count += 1
            if progress_callback:
                progress_callback(processed_count, total_files)

            try:
                blob = bucket.blob(blob_path)
                file_bytes = blob.download_as_bytes()
                filename = Path(blob_path).name
                ext = Path(filename).suffix.lower().strip('.')

                chunks = []
                if ext in processors:
                    chunks = processors[ext].process(file_bytes, filename)
                elif ext in ["txt", "md", "csv"]:
                    text = file_bytes.decode('utf-8', errors='ignore')
                    from app.core.schemas import ChunkMetadata
                    chunks = chunker.chunk_text(text, ChunkMetadata(source_file=filename, chunk_id=""))
                else:
                    result.files_skipped += 1
                    continue

                if chunks and embedder and qdrant_store:
                    embeddings = embedder.embed_batch([c.content for c in chunks])
                    for chunk, emb in zip(chunks, embeddings):
                        chunk.embedding = emb

                    qdrant_store.add_documents(chunks, collection=collection_name)
                    result.semantic_chunks_indexed += len(chunks)

                result.files_indexed += 1

            except Exception as exc:
                msg = f"Failed to ingest {blob_path}: {exc}"
                logger.error(msg, exc_info=True)
                result.errors.append(msg)
                result.files_failed += 1

        result.duration_ms = (time.perf_counter() - t0) * 1000
        return result


_pipeline: ProjectIngestionPipeline | None = None


def get_ingestion_pipeline() -> ProjectIngestionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ProjectIngestionPipeline()
    return _pipeline
