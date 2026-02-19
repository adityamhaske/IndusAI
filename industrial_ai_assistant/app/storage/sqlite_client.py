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

    def get_session(self) -> Session:
        return self.SessionLocal()
