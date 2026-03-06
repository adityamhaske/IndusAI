"""
ProjectService — Phase 20 Persistent Project Architecture.

Manages the Projects, ProjectFiles, and TelemetryDatasets tables.
All state flows through project_id.
No global singletons.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.storage.sqlite_client import SQLiteClient
from app.storage.models import Project, ProjectFile, TelemetryDataset

logger = logging.getLogger(__name__)


class ProjectService:
    def __init__(self, db_client: SQLiteClient):
        self.db_client = db_client

    # ── Project lifecycle ───────────────────────────────────────────────────────

    def upsert_project(
        self,
        project_id: str,
        name: str,
        root_directory: Optional[str] = None,
        vector_collection_name: Optional[str] = None,
        embedding_model: Optional[str] = None,
        embedding_dimension: Optional[int] = None,
        index_version: Optional[str] = None,
        index_status: Optional[str] = None,
    ) -> Project:
        """Create or update a project record."""
        db = self.db_client.get_session()
        try:
            obj = db.query(Project).filter_by(id=project_id).first()
            if obj is None:
                obj = Project(id=project_id, name=name)
                db.add(obj)
            else:
                obj.name = name
            if root_directory is not None:
                obj.root_directory = root_directory
            if vector_collection_name is not None:
                obj.vector_collection_name = vector_collection_name
            if embedding_model is not None:
                obj.embedding_model = embedding_model
            if embedding_dimension is not None:
                obj.embedding_dimension = embedding_dimension
            if index_version is not None:
                obj.index_version = index_version
            if index_status is not None:
                obj.index_status = index_status
            obj.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(obj)
            logger.info("Upserted project %s [%s]", project_id, obj.index_status)
            return obj
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def create_project(self, project_id: str, name: str) -> Project:
        """Backward-compatible create. Delegates to upsert."""
        return self.upsert_project(project_id, name)

    def delete_project(self, project_id: str) -> bool:
        """Delete a project and all associated files and telemetry datasets."""
        db = self.db_client.get_session()
        try:
            obj = db.query(Project).filter_by(id=project_id).first()
            if not obj:
                return False
            # Delete associated records first
            db.query(ProjectFile).filter_by(project_id=project_id).delete()
            db.query(TelemetryDataset).filter_by(project_id=project_id).delete()
            db.delete(obj)
            db.commit()
            logger.info("Deleted project %s and all associated data", project_id)
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def update_index_status(
        self,
        project_id: str,
        status: str,
        last_indexed_at: Optional[datetime] = None,
        index_version: Optional[str] = None,
    ) -> None:
        db = self.db_client.get_session()
        try:
            obj = db.query(Project).filter_by(id=project_id).first()
            if obj:
                obj.index_status = status
                if last_indexed_at:
                    obj.last_indexed_at = last_indexed_at
                if index_version:
                    obj.index_version = index_version
                obj.updated_at = datetime.utcnow()
                db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        db = self.db_client.get_session()
        try:
            obj = db.query(Project).filter_by(id=project_id).first()
            if not obj:
                return None
            return self._serialize(obj)
        finally:
            db.close()

    def get_projects(self) -> List[Project]:
        """Legacy: returns ORM rows."""
        db = self.db_client.get_session()
        try:
            rows = db.query(Project).order_by(Project.updated_at.desc()).all()
            result = []
            for r in rows:
                db.expunge(r)
                result.append(r)
            return result
        finally:
            db.close()

    def get_all_projects(self) -> List[Dict[str, Any]]:
        """Returns serialized list for API."""
        db = self.db_client.get_session()
        try:
            rows = db.query(Project).order_by(Project.updated_at.desc()).all()
            return [self._serialize(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def _serialize(obj: Project) -> Dict[str, Any]:
        return {
            "id":                     obj.id,
            "name":                   obj.name,
            "root_directory":         obj.root_directory,
            "vector_collection_name": obj.vector_collection_name,
            "embedding_model":        obj.embedding_model,
            "embedding_dimension":    obj.embedding_dimension,
            "index_version":          obj.index_version,
            "index_status":           obj.index_status or "UNLOADED",
            "last_indexed_at":        obj.last_indexed_at.isoformat() if obj.last_indexed_at else None,
            "created_at":             obj.created_at.isoformat() if obj.created_at else None,
            "updated_at":             obj.updated_at.isoformat() if obj.updated_at else None,
        }

    # ── ProjectFile tracking ────────────────────────────────────────────────────

    def upsert_project_file(
        self,
        project_id: str,
        file_path: str,
        file_hash: str,
        file_type: str = "txt",
        embedding_count: int = 0,
        last_modified: Optional[float] = None,
        status: str = "indexed",
    ) -> None:
        db = self.db_client.get_session()
        try:
            obj = (
                db.query(ProjectFile)
                .filter_by(project_id=project_id, file_path=file_path)
                .first()
            )
            if obj is None:
                obj = ProjectFile(project_id=project_id, file_path=file_path)
                db.add(obj)
            obj.file_hash       = file_hash
            obj.file_type       = file_type
            obj.embedding_count = embedding_count
            obj.last_modified   = last_modified
            obj.indexed_at      = datetime.utcnow()
            obj.status          = status
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_project_files(self, project_id: str) -> List[Dict[str, Any]]:
        db = self.db_client.get_session()
        try:
            rows = (
                db.query(ProjectFile)
                .filter_by(project_id=project_id)
                .order_by(ProjectFile.indexed_at.desc())
                .all()
            )
            return [
                {
                    "id":              r.id,
                    "file_path":       r.file_path,
                    "file_type":       r.file_type,
                    "file_hash":       r.file_hash,
                    "last_modified":   r.last_modified,
                    "indexed_at":      r.indexed_at.isoformat() if r.indexed_at else None,
                    "embedding_count": r.embedding_count,
                    "status":          r.status,
                }
                for r in rows
            ]
        finally:
            db.close()

    def sync_from_index_metadata(
        self, project_id: str, folder: str, index_meta_files: Dict[str, Any]
    ) -> None:
        """
        Backfill ProjectFile table from the .indusai_index.json file map.
        index_meta_files: {rel_path: IndexedFile-like with .file_hash, .last_modified, .chunk_count}
        """
        for rel_path, record in index_meta_files.items():
            abs_path = str(Path(folder) / rel_path)
            ext = Path(rel_path).suffix.lower().lstrip(".")
            ftype = {"l5x": "l5x", "xlsx": "excel", "xls": "excel", "pdf": "pdf",
                     "csv": "txt", "txt": "txt", "md": "txt"}.get(ext, "txt")
            self.upsert_project_file(
                project_id=project_id,
                file_path=abs_path,
                file_hash=getattr(record, "file_hash", ""),
                file_type=ftype,
                embedding_count=getattr(record, "chunk_count", 0),
                last_modified=getattr(record, "last_modified", None),
            )
        logger.info("Synced %d project files to DB for project %s", len(index_meta_files), project_id)

    # ── TelemetryDataset registry ───────────────────────────────────────────────

    def upsert_telemetry_dataset(
        self,
        project_id: str,
        file_name: str,
        file_path: str,
        file_hash: Optional[str] = None,
        row_count: int = 0,
    ) -> TelemetryDataset:
        db = self.db_client.get_session()
        try:
            obj = (
                db.query(TelemetryDataset)
                .filter_by(project_id=project_id, file_path=file_path)
                .first()
            )
            if obj is None:
                obj = TelemetryDataset(
                    project_id=project_id,
                    file_name=file_name,
                    file_path=file_path,
                )
                db.add(obj)
            obj.file_hash   = file_hash
            obj.row_count   = row_count
            obj.uploaded_at = datetime.utcnow()
            db.commit()
            db.refresh(obj)
            logger.info("Registered telemetry dataset %s for project %s", file_name, project_id)
            return obj
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_telemetry_datasets(self, project_id: str) -> List[Dict[str, Any]]:
        """Returns all registered CSV datasets for a project — for the dropdown."""
        db = self.db_client.get_session()
        try:
            rows = (
                db.query(TelemetryDataset)
                .filter_by(project_id=project_id)
                .order_by(TelemetryDataset.uploaded_at.desc())
                .all()
            )
            return [
                {
                    "id":          r.id,
                    "file_name":   r.file_name,
                    "file_path":   r.file_path,
                    "file_hash":   r.file_hash,
                    "row_count":   r.row_count,
                    "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
                }
                for r in rows
            ]
        finally:
            db.close()

    @staticmethod
    def compute_file_hash(file_path: str) -> str:
        """SHA-256 hash — full for files < 1MB, head+size otherwise."""
        p = Path(file_path)
        h = hashlib.sha256()
        size = p.stat().st_size
        if size <= 1024 * 1024:
            h.update(p.read_bytes())
        else:
            with open(p, "rb") as f:
                h.update(f.read(65536))
            h.update(str(size).encode())
        return h.hexdigest()
