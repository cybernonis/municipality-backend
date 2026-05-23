from fastapi import APIRouter, UploadFile, File
from typing import Optional, List
from app.services.ai_service import classify_image, chat_with_claude
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