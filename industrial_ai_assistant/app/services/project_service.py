"""
ProjectService — Persistent Project Architecture.

Rewritten for Firestore. All data scoped to /users/{uid}/projects and /users/{uid}/project_files.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

from app.storage.firestore_client import FirestoreClient

logger = logging.getLogger(__name__)


class ProjectService:
    def __init__(self, db: FirestoreClient):
        self.db = db

    # ── Project lifecycle ───────────────────────────────────────────────────────

    def upsert_project(
        self,
        uid: str,
        project_id: str,
        name: str,
        vector_collection_name: Optional[str] = None,
        embedding_model: Optional[str] = None,
        embedding_dimension: Optional[int] = None,
        index_version: Optional[str] = None,
        index_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create or update a project record."""
        now = datetime.utcnow().isoformat()
        existing = self.db.get_doc(uid, "projects", project_id)

        doc: Dict[str, Any] = {
            "name": name,
            "updated_at": now,
        }
        if existing is None:
            doc["created_at"] = now
        if vector_collection_name is not None:
            doc["vector_collection_name"] = vector_collection_name
        if embedding_model is not None:
            doc["embedding_model"] = embedding_model
        if embedding_dimension is not None:
            doc["embedding_dimension"] = embedding_dimension
        if index_version is not None:
            doc["index_version"] = index_version
        if index_status is not None:
            doc["index_status"] = index_status

        self.db.set_doc(uid, "projects", project_id, doc, merge=True)
        logger.info("Upserted project %s for user %s [%s]", project_id, uid, index_status)
        return {**doc, "id": project_id}

    def create_project(self, uid: str, project_id: str, name: str) -> Dict[str, Any]:
        """Backward-compatible create. Delegates to upsert."""
        return self.upsert_project(uid, project_id, name)

    def delete_project(self, uid: str, project_id: str) -> bool:
        """Delete a project and all associated files and telemetry datasets."""
        existed = self.db.delete_doc(uid, "projects", project_id)
        if existed:
            # Delete associated project_files (sub-docs keyed by project_id)
            # We store them in a flat collection with project_id field
            self._delete_docs_with_filter(uid, "project_files", "project_id", project_id)
            self._delete_docs_with_filter(uid, "telemetry_datasets", "project_id", project_id)
            logger.info("Deleted project %s and all associated data for user %s", project_id, uid)
        return existed

    def _delete_docs_with_filter(self, uid: str, subcollection: str, field: str, value: str) -> None:
        """Delete all documents in a subcollection matching a field value."""
        col = self.db._user_col(uid, subcollection)
        docs = col.where(field, "==", value).stream()
        batch = self.db.db.batch()
        count = 0
        for doc in docs:
            batch.delete(doc.reference)
            count += 1
            if count >= 400:
                batch.commit()
                batch = self.db.db.batch()
                count = 0
        if count > 0:
            batch.commit()

    def update_index_status(
        self,
        uid: str,
        project_id: str,
        status: str,
        last_indexed_at: Optional[datetime] = None,
        index_version: Optional[str] = None,
    ) -> None:
        update: Dict[str, Any] = {
            "index_status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if last_indexed_at:
            update["last_indexed_at"] = last_indexed_at.isoformat()
        if index_version:
            update["index_version"] = index_version
        self.db.set_doc(uid, "projects", project_id, update, merge=True)

    def get_project(self, uid: str, project_id: str) -> Optional[Dict[str, Any]]:
        doc = self.db.get_doc(uid, "projects", project_id)
        if doc and "index_status" not in doc:
            doc["index_status"] = "UNLOADED"
        return doc

    def get_all_projects(self, uid: str) -> List[Dict[str, Any]]:
        """Returns serialized list for API."""
        docs = self.db.list_docs(uid, "projects", order_by="updated_at", descending=True)
        for d in docs:
            if "index_status" not in d:
                d["index_status"] = "UNLOADED"
        return docs

    # ── ProjectFile tracking ────────────────────────────────────────────────────

    def upsert_project_file(
        self,
        uid: str,
        project_id: str,
        file_path: str,
        file_hash: str,
        file_type: str = "txt",
        embedding_count: int = 0,
        last_modified: Optional[float] = None,
        status: str = "indexed",
    ) -> None:
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{project_id}:{file_path}"))
        doc = {
            "project_id": project_id,
            "file_path": file_path,
            "file_hash": file_hash,
            "file_type": file_type,
            "embedding_count": embedding_count,
            "last_modified": last_modified,
            "indexed_at": datetime.utcnow().isoformat(),
            "status": status,
        }
        self.db.set_doc(uid, "project_files", doc_id, doc, merge=True)

    def get_project_files(self, uid: str, project_id: str) -> List[Dict[str, Any]]:
        return self.db.list_docs(
            uid, "project_files",
            order_by="indexed_at",
            descending=True,
            limit=500,
            filters={"project_id": project_id},
        )

    # ── TelemetryDataset registry ───────────────────────────────────────────────

    def upsert_telemetry_dataset(
        self,
        uid: str,
        project_id: str,
        file_name: str,
        file_path: str,
        file_hash: Optional[str] = None,
        row_count: int = 0,
    ) -> Dict[str, Any]:
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{project_id}:{file_path}"))
        doc = {
            "project_id": project_id,
            "file_name": file_name,
            "file_path": file_path,
            "file_hash": file_hash,
            "row_count": row_count,
            "uploaded_at": datetime.utcnow().isoformat(),
        }
        self.db.set_doc(uid, "telemetry_datasets", doc_id, doc, merge=True)
        doc["id"] = doc_id
        logger.info("Registered telemetry dataset %s for project %s, user %s", file_name, project_id, uid)
        return doc

    def get_telemetry_datasets(self, uid: str, project_id: str) -> List[Dict[str, Any]]:
        """Returns all registered CSV datasets for a project — for the dropdown."""
        return self.db.list_docs(
            uid, "telemetry_datasets",
            order_by="uploaded_at",
            descending=True,
            limit=100,
            filters={"project_id": project_id},
        )
