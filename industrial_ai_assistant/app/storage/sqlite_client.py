from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.constants import DB_PATH
from app.storage.models import Base

class SQLiteClient:
    def __init__(self, db_path: str = str(DB_PATH)):
        self.engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.init_db()

    def init_db(self):
        Base.metadata.create_all(bind=self.engine)
        self._migrate_schema()

    def _migrate_schema(self):
        """Surgical migration for Phase 20+ columns without using Alembic."""
        from sqlalchemy import text
        with self.engine.connect() as conn:
            # Check projects table for missing industrial enterprise columns
            res = conn.execute(text("PRAGMA table_info(projects)"))
            columns = [row[1] for row in res]
            
            # Map of column: type to add
            needed = {
                "root_directory": "VARCHAR",
                "vector_collection_name": "VARCHAR",
                "embedding_model": "VARCHAR",
                "embedding_dimension": "INTEGER",
                "index_version": "VARCHAR",
                "index_status": "VARCHAR",
                "last_indexed_at": "DATETIME",
                "updated_at": "DATETIME",
            }
            
            for col, col_type in needed.items():
                if col not in columns:
                    print(f"🔧 Migrating: Adding column {col} to projects table...")
                    try:
                        conn.execute(text(f"ALTER TABLE projects ADD COLUMN {col} {col_type}"))
                        conn.commit()
                    except Exception as e:
                        print(f"⚠️ Migration failed for {col}: {e}")

    def get_session(self) -> Session:
        return self.SessionLocal()
