from fastapi import APIRouter, Depends, UploadFile, File
from typing import Optional, List
from app.services.ai_service import classify_image, chat_with_claude, chat_with_citizen, chat_with_admin
from app.dependencies import require_admin
from pydantic import BaseModel

router = APIRouter()

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    user_id: Optional[str] = None

@router.post("/classify")
async def classify(
    image: UploadFile = File(...),
    description: Optional[str] = None
):
    image_bytes = await image.read()
    result = await classify_image(image_bytes, description)
    return result

@router.post("/chat")
async def chat(request: ChatRequest):
    result = await chat_with_claude(
        messages=request.messages,
        user_id=request.user_id
    )
    return {"response": result}

@router.post("/chat/citizen")
async def chat_citizen(request: ChatRequest):
    result = await chat_with_citizen(messages=request.messages)
    return {"response": result}

@router.post("/chat/admin")
async def chat_admin(request: ChatRequest, _admin: dict = Depends(require_admin)):
    return await chat_with_admin(messages=request.messages)