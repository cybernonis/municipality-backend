import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from app.database import supabase

logger = logging.getLogger(__name__)
router = APIRouter()


class AnnouncementCreate(BaseModel):
    title: str
    body: str
    category: Optional[str] = "general"
    admin_id: Optional[str] = None


@router.post("/")
async def create_announcement(payload: AnnouncementCreate):
    try:
        announcement = {
            "id": str(uuid.uuid4()),
            "title": payload.title,
            "body": payload.body,
            "category": payload.category,
            "admin_id": payload.admin_id,
        }
        result = supabase.table("announcements").insert(announcement).execute()

        # FCM push σε όλους
        try:
            users_result = supabase.table("users").select("fcm_token").execute()
            tokens = [u["fcm_token"] for u in (users_result.data or []) if u.get("fcm_token")]
            if tokens:
                from app.services.notification_service import send_push_to_multiple
                asyncio.create_task(send_push_to_multiple(
                    tokens=tokens,
                    title=f"📢 {payload.title}",
                    body=payload.body,
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


@router.delete("/{announcement_id}")
def delete_announcement(announcement_id: str):
    try:
        result = supabase.table("announcements").delete().eq("id", announcement_id).execute()
        return {"message": "Deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
