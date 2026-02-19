from typing import Optional, List
from app.core.interfaces.llm_interface import LLMInterface
from app.core.interfaces.retriever_interface import RetrieverInterface
from app.services.validation_service import ValidationService
from app.core.schemas import ChatRequest, ChatResponse, ChatMessage
from app.storage.sqlite_client import SQLiteClient
from app.storage.models import ChatMessage as DBChatMessage

class ChatService:
    def __init__(
        self,
        llm: LLMInterface,
        retriever: RetrieverInterface,
        validator: ValidationService,
        db_client: SQLiteClient
    ):
        self.llm = llm
        self.retriever = retriever
        self.validator = validator
        self.db_client = db_client

    def chat(self, request: ChatRequest) -> ChatResponse:
        # 1. Retrieve Context
        # TODO: Parse filters from request
        chunks = self.retriever.retrieve(request.query, top_k=5)
        
        context_str = "\n\n".join([f"Source: {c.metadata.source_file}\nContent: {c.content}" for c in chunks])
        
        # 2. Construct System Prompt
        system_prompt = (
            "You are an expert Industrial AI Assistant. "
            "Answer the user's query using strictly the provided context. "
            "If the answer is not in the context, state that you do not know. "
            "Provide the output in strict JSON format matching the schema."
            f"\n\nContext:\n{context_str}"
        )

        # 3. Call LLM
        # We assume the LLM implementation handles the JSON parsing or we do it here.
        # Since our interface says generate_json, we use that.
        raw_response = self.llm.generate_json(request.query, ChatResponse, system_prompt=system_prompt)
        
        # 4. Parse & Validate
        try:
            response = ChatResponse(**raw_response)
        except Exception as e:
            # Fallback or error
            # For now, return a low confidence error response
            return ChatResponse(
                summary=f"Failed to parse response: {str(e)}",
                confidence_score=0.0,
                limitations="System Error",
                likely_causes=[]
            )

        # 5. Hallucination Check
        # TODO: Fetch valid tags from TagService/DB
        known_tags = [] 
        try:
            self.validator.validate_response(response, known_tags)
        except Exception as e:
            response.limitations += f" [Validation Warning: {str(e)}]"
            response.confidence_score = max(0.0, response.confidence_score - 0.2)

        # 6. Save History (Async in real world, sync here for simplicity)
        self._sava_history(request.query, response.summary)

        return response

    def _sava_history(self, user_query: str, ai_response: str):
        session = self.db_client.get_session()
        try:
            # Placeholder session ID
            session_id = "default_session" 
            
            user_msg = DBChatMessage(session_id=session_id, role="user", content=user_query)
            ai_msg = DBChatMessage(session_id=session_id, role="assistant", content=ai_response)
            
            session.add(user_msg)
            session.add(ai_msg)
            session.commit()
        finally:
            session.close()
