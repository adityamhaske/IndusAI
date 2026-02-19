from typing import List
from app.storage.sqlite_client import SQLiteClient
from app.storage.models import Project

class ProjectService:
    def __init__(self, db_client: SQLiteClient):
        self.db_client = db_client

    def create_project(self, project_id: str, name: str):
        session = self.db_client.get_session()
        try:
            proj = Project(id=project_id, name=name)
            session.add(proj)
            session.commit()
        finally:
            session.close()

    def get_projects(self) -> List[Project]:
        session = self.db_client.get_session()
        try:
            return session.query(Project).all()
        finally:
            session.close()
