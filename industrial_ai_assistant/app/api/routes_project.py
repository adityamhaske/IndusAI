from typing import List
from fastapi import APIRouter, Depends
from app.core.schemas import ProjectInfo
from app.config.dependency_injection import get_container, Container

router = APIRouter()

@router.post("/projects")
def create_project(project_id: str, name: str, container: Container = Depends(get_container)):
    container.project_service.create_project(project_id, name)
    return {"status": "created", "id": project_id}

@router.get("/projects", response_model=List[ProjectInfo])
def list_projects(container: Container = Depends(get_container)):
    projs = container.project_service.get_projects()
    return [
        ProjectInfo(id=p.id, name=p.name) for p in projs
    ]
