"""
File-upload ingestion endpoint — Phase 20 Persistent Project Architecture.

POST /api/project/ingest-upload
  Accept: multipart/form-data
  Fields:
    - project_id: str
    - files: list of UploadFile (all files from selected folder)

Phase 20 changes:
  - REMOVED shutil.rmtree — existing files are preserved across uploads.
  - Only files whose content hash changed are overwritten (selective update).
  - CSV files are registered in TelemetryDataset for the persistent dropdown.
  - Project record is upserted in DB before ingestion runs.
  - After ingestion, ProjectFile table is synced from .indusai_index.json.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.services.project_ingestion_pipeline import get_ingestion_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/project", tags=["Project Knowledge"])

_env_root = os.environ.get("INDUSAI_DATA_DIR", "")
DATA_ROOT = Path(_env_root).resolve() if _env_root else (Path.cwd() / "data" / "projects")


def _file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@router.post("/ingest-upload")
async def ingest_upload(
    project_id: str = Form(default="default"),
    files: list[UploadFile] = File(...),
):
    """
    Accept a folder's files from the browser's <input webkitdirectory> picker.

    Phase 20: does NOT wipe existing project storage.
    Only overwrites files whose content hash has changed.
    Registers CSVs as TelemetryDatasets.
    """
    if not files:
        return JSONResponse(status_code=400, content={"error": "NO_FILES", "message": "No files uploaded."})

    project_dir = DATA_ROOT / project_id
    try:
        project_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return JSONResponse(status_code=500, content={
            "error": "STORAGE_FAILED",
            "message": f"Could not create project storage: {exc}",
        })

    saved = overwritten = skipped = 0
    save_errors: list[str] = []
    csv_files: list[tuple[str, str]] = []   # (name, abs_path)

    for upload in files:
        rel = upload.filename or ""
        parts = [p for p in Path(rel).parts if p not in ("", ".", "..")]
        if not parts:
            skipped += 1
            continue

        dest = project_dir.joinpath(*parts)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = await upload.read()
            incoming_hash = _file_hash(content)

            # Selective overwrite — skip if file exists and hash matches
            if dest.exists():
                existing_hash = _file_hash(dest.read_bytes())
                if existing_hash == incoming_hash:
                    skipped += 1
                    # Still track CSVs even if unchanged
                    if dest.suffix.lower() == ".csv":
                        csv_files.append((dest.name, str(dest)))
                    continue
                else:
                    dest.write_bytes(content)
                    overwritten += 1
            else:
                dest.write_bytes(content)
                saved += 1

            if dest.suffix.lower() == ".csv":
                csv_files.append((dest.name, str(dest)))

        except Exception as exc:
            save_errors.append(f"{rel}: {exc}")
            skipped += 1

    if saved + overwritten == 0 and skipped == 0:
        return JSONResponse(status_code=400, content={
            "error": "NO_FILES_SAVED",
            "message": "No files could be saved.",
            "errors": save_errors[:5],
        })

    logger.info(
        "[ingest-upload] project=%s new=%d overwritten=%d skipped=%d",
        project_id, saved, overwritten, skipped,
    )

    # ── Register project in DB ──────────────────────────────────────────────────
    try:
        from app.config.dependency_injection import get_container
        ps = get_container().project_service
        ps.upsert_project(
            project_id=project_id,
            name=project_id.replace("_", " ").replace("-", " ").title(),
            root_directory=str(project_dir),
            index_status="INDEXING",
        )
        # Register CSV telemetry datasets
        for fname, fpath in csv_files:
            try:
                row_count = sum(1 for _ in open(fpath)) - 1  # crude line count
            except Exception:
                row_count = 0
            fhash = _file_hash(Path(fpath).read_bytes())
            ps.upsert_telemetry_dataset(
                project_id=project_id,
                file_name=fname,
                file_path=fpath,
                file_hash=fhash,
                row_count=max(row_count, 0),
            )
    except Exception as reg_err:
        logger.warning("DB registration failed (non-fatal): %s", reg_err)

    # ── Run ingestion pipeline ──────────────────────────────────────────────────
    try:
        pipeline = get_ingestion_pipeline()
        result = await pipeline.ingest(str(project_dir), project_id)
        result.warnings.append(f"Upload: {saved} new, {overwritten} updated, {skipped} skipped.")
        if save_errors:
            result.warnings.append(f"Save errors: {'; '.join(save_errors[:3])}")

        # Sync file hashes to DB
        try:
            from app.config.dependency_injection import get_container
            from app.models.project_models import IndexMetadata
            import json
            ps = get_container().project_service
            meta_path = Path(str(project_dir)) / ".indusai_index.json"
            if meta_path.exists():
                meta = IndexMetadata.model_validate_json(meta_path.read_text())
                ps.sync_from_index_metadata(project_id, str(project_dir), meta.files)
            ps.update_index_status(
                project_id, "READY",
                last_indexed_at=__import__("datetime").datetime.utcnow(),
                index_version=result.project_hash,
            )
        except Exception as sync_err:
            logger.warning("Post-ingestion DB sync failed (non-fatal): %s", sync_err)

        return result

    except Exception as exc:
        logger.exception("Ingestion failed after upload for project=%s", project_id)
        try:
            from app.config.dependency_injection import get_container
            get_container().project_service.update_index_status(project_id, "OUTDATED")
        except Exception:
            pass
        return JSONResponse(status_code=500, content={
            "error": "INGESTION_FAILED",
            "message": str(exc),
            "storage_path": str(project_dir),
        })
