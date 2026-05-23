from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import Optional
from app.services.ai_service import classify_image
import traceback

router = APIRouter()

@router.get("/test")
async def test_ai():
    try:
        from app.config import ANTHROPIC_API_KEY
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=100,
            messages=[{"role": "user", "content": "Πες μου 'Γεια σου Ηράκλειο!'"}]
        )
        return {"status": "ok", "response": msg.content[0].text}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/classify")
async def classify(
    image: UploadFile = File(...),
    description: Optional[str] = None
):
    try:
        image_bytes = await image.read()
        print(f"Image received: {len(image_bytes)} bytes")
        result = await classify_image(image_bytes, description)
        return result
    except Exception as e:
        print("ERROR:", str(e))
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))