from typing import List
from app.storage.sqlite_client import SQLiteClient
from app.storage.models import ChatMessage

class HistoryService:
    def __init__(self, db_client: SQLiteClient):
        self.db_client = db_client

    def get_session_history(self, session_id: str) -> List[ChatMessage]:
        session = self.db_client.get_session()
        try:
            return session.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.timestamp).all()
        finally:
            session.close()
