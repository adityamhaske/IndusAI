"""
File-upload ingestion endpoint.

POST /api/project/ingest-upload
  Accept: multipart/form-data
  Fields:
    - project_id: str
    - files: list of UploadFile (all files from selected folder)

Browser sends relative paths via File.webkitRelativePath (e.g. "my_proj/src/Main.L5X").
Backend reconstructs the folder tree under ./data/projects/{project_id}/ and runs ingestion.

This eliminates all filesystem-path dependency:
  - No Docker mount issues
  - No copy/paste path errors
  - No OS path normalisation bugs
  - Cross-platform, deployment-safe
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.services.project_ingestion_pipeline import get_ingestion_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/project", tags=["Project Knowledge"])

# Root storage for uploaded projects (relative to backend process cwd)
_env_root = os.environ.get("INDUSAI_DATA_DIR", "")
DATA_ROOT = Path(_env_root).resolve() if _env_root else (Path.cwd() / "data" / "projects")


@router.post("/ingest-upload")
async def ingest_upload(
    project_id: str = Form(default="default"),
    files: list[UploadFile] = File(...),
):
    """
    Accept a folder's files from the browser's <input webkitdirectory> picker.

    Browser sends webkitRelativePath as the filename (e.g. "proj/subdir/file.l5x").
    Backend stores files under data/projects/{project_id}/ preserving the tree,
    then runs the ingestion pipeline on that stored folder.

    Returns IngestionResult on success, or structured error JSON on failure.
    """
    if not files:
        return JSONResponse(status_code=400, content={"error": "NO_FILES", "message": "No files uploaded."})

    # Build project staging folder
    project_dir = DATA_ROOT / project_id
    try:
        # Clear any previous upload for this project
        if project_dir.exists():
            shutil.rmtree(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return JSONResponse(status_code=500, content={
            "error": "STORAGE_FAILED",
            "message": f"Could not create project storage: {exc}",
            "storage_root": str(DATA_ROOT),
        })

    saved = 0
    skipped = 0
    save_errors: list[str] = []

    for upload in files:
        # webkitRelativePath comes as the filename field from the browser
        # e.g. "MyProject/IO_List.xlsx" or just "file.l5x" if flat
        rel = upload.filename or ""
        # Sanitize: prevent directory traversal
        parts = [p for p in Path(rel).parts if p not in ("", ".", "..")]
        if not parts:
            skipped += 1
            continue

        dest = project_dir.joinpath(*parts)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = await upload.read()
            dest.write_bytes(content)
            saved += 1
        except Exception as exc:
            save_errors.append(f"{rel}: {exc}")
            skipped += 1

    if saved == 0:
        return JSONResponse(status_code=400, content={
            "error": "NO_FILES_SAVED",
            "message": "No files could be saved to backend storage.",
            "errors": save_errors[:5],
            "storage_path": str(project_dir),
        })

    logger.info(
        "[ingest-upload] project=%s saved=%d skipped=%d storage=%s",
        project_id, saved, skipped, project_dir,
    )

    # Run ingestion pipeline on the stored folder
    try:
        pipeline = get_ingestion_pipeline()
        result = await pipeline.ingest(str(project_dir), project_id)

        # Attach upload stats to result warnings
        result.warnings.append(f"Uploaded {saved} files, skipped {skipped}.")
        if save_errors:
            result.warnings.append(f"Save errors: {'; '.join(save_errors[:3])}")

        return result

    except Exception as exc:
        logger.exception("Ingestion failed after upload for project=%s", project_id)
        return JSONResponse(status_code=500, content={
            "error": "INGESTION_FAILED",
            "message": str(exc),
            "storage_path": str(project_dir),
            "files_saved": saved,
        })
