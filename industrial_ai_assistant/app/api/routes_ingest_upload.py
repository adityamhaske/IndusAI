"""
File-upload ingestion endpoint — Phase 20 Persistent Project Architecture.

POST /api/project/ingest-upload
  Accept: multipart/form-data
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.auth.firebase_auth import AuthenticatedUser, get_current_user
from app.core.firebase import get_storage_bucket
from app.storage.firestore_client import get_firestore
from app.services.project_ingestion_pipeline import get_ingestion_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/project", tags=["Project Knowledge"])


def _file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _run_ingestion_task(job_id: str, project_id: str, uid: str, uploaded_blob_paths: list[str], csv_files: list[tuple[str, str]]):
    try:
        db = get_firestore()
        
        def progress_cb(indexed, total):
            db.set_doc(uid, "ingest_jobs", job_id, {
                "progress": f"{indexed}/{total} files indexed"
            }, merge=True)
            
        try:
            from app.config.dependency_injection import get_container
            ps = get_container()._project_service
            ps.upsert_project(
                uid=uid,
                project_id=project_id,
                name=project_id.replace("_", " ").replace("-", " ").title(),
                index_status="INDEXING",
            )
            for fname, fpath in csv_files:
                ps.upsert_telemetry_dataset(
                    uid=uid,
                    project_id=project_id,
                    file_name=fname,
                    file_path=fpath,
                    file_hash="firebase_blob",
                    row_count=100, # Mock row count since we don't read line by line here
                )
        except Exception as reg_err:
            logger.warning("DB registration failed (non-fatal): %s", reg_err)

        pipeline = get_ingestion_pipeline()
        result = await pipeline.ingest(uploaded_blob_paths, project_id, uid, progress_callback=progress_cb)

        try:
            from app.config.dependency_injection import get_container
            ps = get_container()._project_service
            ps.update_index_status(
                uid=uid,
                project_id=project_id,
                status="READY",
                last_indexed_at=datetime.utcnow(),
                index_version=result.project_hash,
            )
        except Exception as sync_err:
            logger.warning("Post-ingestion DB sync failed (non-fatal): %s", sync_err)

        db.set_doc(uid, "ingest_jobs", job_id, {
            "status": "complete",
            "updated_at": datetime.utcnow().isoformat()
        }, merge=True)
        
    except Exception as exc:
        logger.exception("Ingestion failed after upload for project=%s", project_id)
        db = get_firestore()
        db.set_doc(uid, "ingest_jobs", job_id, {
            "status": "failed",
            "error": str(exc),
            "updated_at": datetime.utcnow().isoformat()
        }, merge=True)
        try:
            from app.config.dependency_injection import get_container
            get_container()._project_service.update_index_status(uid, project_id, "OUTDATED")
        except Exception:
            pass


@router.get("/ingest/status/{job_id}")
async def get_ingestion_status(
    job_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    db = get_firestore()
    job = db.get_doc(user.uid, "ingest_jobs", job_id)
    if not job:
        return JSONResponse(status_code=200, content={
            "status": "unknown",
            "progress": "",
            "error": "Job not found. The server may have restarted. Please re-upload your files."
        })
    return JSONResponse(status_code=200, content=job)


@router.post("/ingest-upload")
async def ingest_upload(
    background_tasks: BackgroundTasks,
    project_id: str = Form(default="default"),
    files: list[UploadFile] = File(...),
    user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Accept a folder's files from the browser's <input webkitdirectory> picker.
    Uploads directly to Firebase Storage.
    """
    if not files:
        return JSONResponse(status_code=400, content={"error": "NO_FILES", "message": "No files uploaded."})

    bucket = get_storage_bucket()
    job_id = str(uuid.uuid4())
    
    saved = skipped = 0
    save_errors = []
    csv_files = []
    uploaded_blob_paths = []

    for upload in files:
        rel = upload.filename or ""
        parts = [p for p in Path(rel).parts if p not in ("", ".", "..")]
        if not parts:
            skipped += 1
            continue

        filename = "/".join(parts)
        
        try:
            content = await upload.read()

            if rel.lower().endswith(".pdf"):
                if upload.content_type != "application/pdf":
                    save_errors.append(f"{rel}: Not a valid PDF file (invalid MIME type)")
                    skipped += 1
                    continue
                if len(content) > 20 * 1024 * 1024:
                    save_errors.append(f"{rel}: File size exceeds 20MB limit for Gemini API")
                    skipped += 1
                    continue

            blob_path = f"users/{user.uid}/documents/{job_id}/{filename}"
            blob = bucket.blob(blob_path)
            blob.upload_from_string(content)
            
            saved += 1
            uploaded_blob_paths.append(blob_path)

            if rel.lower().endswith(".csv"):
                csv_files.append((Path(rel).name, blob_path))

        except Exception as exc:
            save_errors.append(f"{rel}: {exc}")
            skipped += 1

    if saved == 0 and skipped == 0:
        return JSONResponse(status_code=400, content={
            "error": "NO_FILES_SAVED",
            "message": "No files could be saved.",
            "errors": save_errors[:5],
        })

    logger.info("[ingest-upload] project=%s job=%s saved=%d skipped=%d", project_id, job_id, saved, skipped)

    db = get_firestore()
    db.set_doc(user.uid, "ingest_jobs", job_id, {
        "status": "processing",
        "progress": "0 files indexed",
        "error": None,
        "blob_paths": uploaded_blob_paths,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    })

    background_tasks.add_task(
        _run_ingestion_task,
        job_id=job_id,
        project_id=project_id,
        uid=user.uid,
        uploaded_blob_paths=uploaded_blob_paths,
        csv_files=csv_files
    )

    return JSONResponse(status_code=202, content={"job_id": job_id})
