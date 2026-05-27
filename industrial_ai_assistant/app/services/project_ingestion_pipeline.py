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
                if ext == "pdf":
                    chunks = processors[ext].process(file_bytes, filename)
                elif ext == "l5x":
                    import tempfile
                    import os
                    from app.parsers.l5x_parser import parse as parse_l5x
                    from app.indexes.structured_index import get_structured_index

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".L5X") as tmp:
                        tmp.write(file_bytes)
                        tmp_path = tmp.name

                    try:
                        parsed = parse_l5x(tmp_path)
                        si = get_structured_index(project_id)
                        for tag in parsed.tags:
                            si.add_tag(tag)
                        for routine in parsed.routines:
                            si.add_routine(routine)
                        for aoi in parsed.aois:
                            si.add_aoi(aoi)
                        
                        result.tags_indexed += len(parsed.tags)
                        result.routines_indexed += len(parsed.routines)

                        # Create a semantic chunk summarizing the L5X routine contents
                        # so it can also be searched semantically!
                        text_content = f"PLC Logic L5X file: {filename}\n"
                        text_content += f"Contains {len(parsed.tags)} tags, {len(parsed.routines)} routines, {len(parsed.aois)} AOIs.\n"
                        for r in parsed.routines[:10]:
                            text_content += f"Routine: {r.name} in Program: {r.program} ({r.routine_type}): {r.content_snippet}\n"
                        
                        from app.core.schemas import ChunkMetadata
                        chunks = chunker.chunk_text(text_content, ChunkMetadata(source_file=filename, chunk_id=""))
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass
                elif ext in ["xlsx", "xls"]:
                    import tempfile
                    import os
                    from app.parsers.excel_parser import parse as parse_excel
                    from app.indexes.structured_index import get_structured_index

                    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
                        tmp.write(file_bytes)
                        tmp_path = tmp.name

                    try:
                        parsed = parse_excel(tmp_path)
                        si = get_structured_index(project_id)
                        for io in parsed.io_rows:
                            si.add_io(io)
                        
                        # Register the dataset in project telemetry so io_rows count is populated correctly!
                        try:
                            import hashlib
                            ps = container._project_service
                            ps.upsert_telemetry_dataset(
                                uid=uid,
                                project_id=project_id,
                                file_name=filename,
                                file_path=blob_path,
                                file_hash=hashlib.md5(blob_path.encode()).hexdigest(),
                                row_count=len(parsed.io_rows),
                            )
                        except Exception as reg_err:
                            logger.warning("Failed to register Excel dataset in telemetry: %s", reg_err)

                        # Create semantic chunks for each IO row so it can be searched semantically!
                        text_content = f"IO Sheet: {filename}\n"
                        text_content += f"Contains {len(parsed.io_rows)} IO channel rows.\n"
                        for io in parsed.io_rows[:15]:
                            text_content += f"IO Point - Slot: {io.slot}, Rack: {io.rack}, Module: {io.module}, Tag: {io.tag_name}, Description: {io.description}\n"
                        
                        from app.core.schemas import ChunkMetadata
                        chunks = chunker.chunk_text(text_content, ChunkMetadata(source_file=filename, chunk_id=""))
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass
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

                try:
                    import hashlib
                    ps = container._project_service
                    ps.upsert_project_file(
                        uid=uid,
                        project_id=project_id,
                        file_path=blob_path,
                        file_hash=hashlib.md5(blob_path.encode()).hexdigest(),
                        file_type=ext,
                        embedding_count=len(chunks),
                        status="indexed"
                    )
                except Exception as db_err:
                    logger.warning("Failed to save project file metadata to DB: %s", db_err)

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
