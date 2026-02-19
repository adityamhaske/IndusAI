from typing import List
from app.storage.sqlite_client import SQLiteClient
from app.storage.models import Log

class LogService:
    def __init__(self, db_client: SQLiteClient):
        self.db_client = db_client

    def add_log(self, level: str, message: str, module: str):
        session = self.db_client.get_session()
        try:
            log = Log(level=level, message=message, module=module)
            session.add(log)
            session.commit()
        finally:
            session.close()
            
    def get_logs(self, limit: int = 100) -> List[Log]:
        session = self.db_client.get_session()
        try:
            return session.query(Log).order_by(Log.timestamp.desc()).limit(limit).all()
        finally:
            session.close()
