"""
Project API — Persistent Project Architecture
Mounted at /api by main.py (prefix="/api")

All endpoints require Firebase Auth. Data is scoped to the authenticated user.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.firebase_auth import AuthenticatedUser, get_current_user
from app.config.dependency_injection import get_container, Container

logger = logging.getLogger(__name__)
router = APIRouter()


# ── GET /api/projects ──────────────────────────────────────────────────────────

@router.get("/projects", tags=["Projects"])
def list_projects(
    user: AuthenticatedUser = Depends(get_current_user),
    container: Container = Depends(get_container),
):
    """List all registered projects with index_status."""
    return container.project_service.get_all_projects(user.uid)


# ── POST /api/projects ─────────────────────────────────────────────────────────

class CreateProjectBody(BaseModel):
    project_id: str
    name: str

@router.post("/projects", tags=["Projects"])
def create_project(
    body: CreateProjectBody,
    user: AuthenticatedUser = Depends(get_current_user),
    container: Container = Depends(get_container),
):
    """Create or update a project record."""
    obj = container.project_service.create_project(
        uid=user.uid,
        project_id=body.project_id,
        name=body.name,
    )
    return {"status": "created", "id": obj.get("id")}


# ── GET /api/projects/{id} ─────────────────────────────────────────────────────

@router.get("/projects/{project_id}", tags=["Projects"])
def get_project(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    container: Container = Depends(get_container),
):
    """Full project detail including index_status."""
    data = container.project_service.get_project(user.uid, project_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return data


# ── GET /api/projects/{id}/files ───────────────────────────────────────────────

@router.get("/projects/{project_id}/files", tags=["Projects"])
def get_project_files(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    container: Container = Depends(get_container),
):
    """List all tracked files with hash, status, and embedding count."""
    return container.project_service.get_project_files(user.uid, project_id)


# ── GET /api/projects/{id}/telemetry ──────────────────────────────────────────

@router.get("/projects/{project_id}/telemetry", tags=["Projects"])
def get_telemetry_datasets(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    container: Container = Depends(get_container),
):
    """List all registered telemetry CSV datasets for the project."""
    return container.project_service.get_telemetry_datasets(user.uid, project_id)


# ── DELETE /api/projects/{id} ─────────────────────────────────────────────────

@router.delete("/projects/{project_id}", tags=["Projects"])
def delete_project(
    project_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    container: Container = Depends(get_container),
):
    """
    Permanently delete a project and all associated data:
    - Firestore records (project, files, telemetry datasets)
    - Qdrant vectors for this project
    - Fault dataset cache
    """
    if project_id == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default project.")

    # 1. Delete vectors from Qdrant
    try:
        from app.indexes.structured_index import clear_structured_index
        from app.indexes.semantic_index import get_semantic_index
        clear_structured_index(project_id)
        get_semantic_index().delete_project(project_id)
    except Exception as e:
        logger.warning("Could not clear vectors for project %s: %s", project_id, e)

    # 2. Clear fault dataset cache
    try:
        from app.services.fault_service import get_fault_service
        get_fault_service().reset(project_id)
    except Exception as e:
        logger.warning("Could not clear fault cache for project %s: %s", project_id, e)

    # 3. Delete from Firestore (project + files + telemetry)
    deleted = container.project_service.delete_project(user.uid, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    logger.info("Project %s fully deleted for user %s.", project_id, user.uid)
    return {"status": "deleted", "project_id": project_id}
