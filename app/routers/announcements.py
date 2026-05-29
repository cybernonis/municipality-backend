import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from typing import Optional

from app.database import supabase
from app.services.storage_service import upload_image

logger = logging.getLogger(__name__)
router = APIRouter()


async def _try_upload(image: Optional[UploadFile]) -> Optional[str]:
    """Upload image, return public URL or None on failure (never raises)."""
    if image is None:
        return None
    try:
        return await upload_image(image)
    except Exception as e:
        logger.error(f"[announcements] Image upload failed: {e}")
        return None


@router.post("/")
async def create_announcement(
    title: str = Form(...),
    body: str = Form(...),
    category: Optional[str] = Form("general"),
    admin_id: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
):
    try:
        image_url = await _try_upload(image)

        announcement = {
            "id": str(uuid.uuid4()),
            "title": title,
            "body": body,
            "category": category or "general",
            "admin_id": admin_id,
            "image_url": image_url,
        }
        result = supabase.table("announcements").insert(announcement).execute()

        # FCM push to all users
        try:
            users_result = supabase.table("users").select("fcm_token").execute()
            tokens = [u["fcm_token"] for u in (users_result.data or []) if u.get("fcm_token")]
            if tokens:
                from app.services.notification_service import send_push_to_multiple
                asyncio.create_task(send_push_to_multiple(
                    tokens=tokens,
                    title=f"📢 {title}",
                    body=body,
                    data={"type": "announcement", "announcement_id": announcement["id"]},
                ))
        except Exception as e:
            logger.error(f"FCM multicast error: {e}")

        return {"message": "Ανακοίνωση δημιουργήθηκε!", "announcement": result.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
def get_announcements(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
):
    try:
        query = supabase.table("announcements").select("*", count="exact")
        if category:
            query = query.eq("category", category)
        offset = (page - 1) * per_page
        result = query.order("created_at", desc=True).range(offset, offset + per_page - 1).execute()
        total = result.count or 0
        return {
            "data": result.data,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{announcement_id}")
async def update_announcement(
    announcement_id: str,
    title: Optional[str] = Form(None),
    body: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
):
    try:
        data: dict = {}
        if title is not None:
            data["title"] = title
        if body is not None:
            data["body"] = body
        if category is not None:
            data["category"] = category

        image_url = await _try_upload(image)
        if image_url is not None:
            data["image_url"] = image_url

        if not data:
            raise HTTPException(status_code=400, detail="Δεν δόθηκε κανένα πεδίο προς ενημέρωση")

        result = supabase.table("announcements").update(data).eq("id", announcement_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Ανακοίνωση δεν βρέθηκε")
        return {"message": "Ανακοίνωση ενημερώθηκε!", "announcement": result.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{announcement_id}")
def delete_announcement(announcement_id: str):
    try:
        supabase.table("announcements").delete().eq("id", announcement_id).execute()
        return {"message": "Deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
