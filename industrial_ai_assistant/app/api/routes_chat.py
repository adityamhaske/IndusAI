from fastapi import APIRouter, Depends, HTTPException
from app.core.schemas import ChatRequest, ChatResponse
from app.config.dependency_injection import get_container, Container

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest, container: Container = Depends(get_container)):
    try:
        return container.chat_service.chat(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
