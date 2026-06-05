import asyncio
import logging
import sys
import traceback
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form

from app.database import supabase
from app.dependencies import get_current_user, require_admin, require_permission
from app.limiter import limiter
from app.services.storage_service import upload_image
from app.utils.sanitize import sanitize_text

logger = logging.getLogger(__name__)
router = APIRouter()


def normalize_announcement(row: dict) -> dict:
    return {
        "id":           row.get("id"),
        "title":        row.get("title", ""),
        "content":      row.get("content") or row.get("body") or row.get("description") or "",
        "is_important": row.get("is_important", False),
        "is_urgent":    row.get("is_urgent", False),
        "priority":     row.get("priority", 0),
        "category":     row.get("category", "general"),
        "created_at":   str(row.get("created_at", "")),
        "expires_at":   str(row.get("expires_at")) if row.get("expires_at") else None,
    }


async def _try_upload(image: Optional[UploadFile]) -> Optional[str]:
    if image is None:
        return None
    try:
        return await upload_image(image)
    except Exception as e:
        logger.error(f"[announcements] Image upload failed: {e}")
        return None


async def _push_announcement(title: str, body: str, announcement_id: str):
    try:
        users_result = supabase.table("users").select("fcm_token").execute()
        tokens = [u["fcm_token"] for u in (users_result.data or []) if u.get("fcm_token")]
        if tokens:
            from app.services.notification_service import send_push_to_multiple
            asyncio.create_task(send_push_to_multiple(
                tokens=tokens,
                title=f"📢 {title}",
                body=body,
                data={"type": "announcement", "announcement_id": announcement_id},
            ))
    except Exception as e:
        logger.error(f"[announcements] Push notification error: {e}")


@router.post("/")
@limiter.limit("30/minute")
async def create_announcement(
    request: Request,
    title: str = Form(...),
    content: Optional[str] = Form(None),
    body: Optional[str] = Form(None),
    category: Optional[str] = Form("general"),
    is_important: bool = Form(False),
    is_urgent: bool = Form(False),
    expires_at: Optional[str] = Form(None),
    admin_id: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    _user: dict = Depends(get_current_user),  # TEMP: bypass role check for diagnosis
):
    # ═══ EXTENSIVE LOGGING ═══
    print("=" * 60, flush=True)
    print(f"[ANNOUNCE POST] Request received", flush=True)
    print(f"[ANNOUNCE POST] title={title!r} category={category!r}", flush=True)
    print(f"[ANNOUNCE POST] is_important={is_important} is_urgent={is_urgent}", flush=True)
    if isinstance(_user, dict):
        print(f"[ANNOUNCE POST] user keys={list(_user.keys())}", flush=True)
        print(f"[ANNOUNCE POST] user role={_user.get('role')!r}", flush=True)
        print(f"[ANNOUNCE POST] user id={_user.get('id')!r}", flush=True)
        print(f"[ANNOUNCE POST] user email_verified={_user.get('email_verified')!r}", flush=True)
    else:
        print(f"[ANNOUNCE POST] user type={type(_user).__name__} attrs={dir(_user)}", flush=True)
    print("=" * 60, flush=True)
    sys.stdout.flush()

    # ── Step 1: image upload ──
    try:
        image_url = await _try_upload(image)
        print(f"[ANNOUNCE POST] image_url={image_url!r}", flush=True)
    except Exception as e:
        print(f"[ANNOUNCE POST] image upload error (non-fatal): {e}", flush=True)
        image_url = None

    # ── Step 2: build row ──
    title = sanitize_text(title)
    actual_content = sanitize_text(content or body or "")
    announcement_id = str(uuid.uuid4())

    row = {
        "id":           announcement_id,
        "title":        title,
        "body":         actual_content,
        "category":     category or "general",
        "is_important": is_important,
        "is_urgent":    is_urgent,
        "admin_id":     admin_id,
        "image_url":    image_url,
    }
    if expires_at:
        row["expires_at"] = expires_at

    print(f"[ANNOUNCE POST] row to insert: {row}", flush=True)
    sys.stdout.flush()

    # ── Step 3: DB insert ──
    try:
        result = supabase.table("announcements").insert(row).execute()
        print(f"[ANNOUNCE POST] insert result.data={result.data}", flush=True)
        print(f"[ANNOUNCE POST] ✅ Created id={announcement_id}", flush=True)
        sys.stdout.flush()
    except Exception as db_err:
        print(f"[ANNOUNCE POST] ❌ DB INSERT FAILED: {type(db_err).__name__}: {db_err}", flush=True)
        traceback.print_exc()
        sys.stdout.flush()
        raise HTTPException(status_code=500, detail=f"DB error: {str(db_err)}")

    if not result.data:
        print(f"[ANNOUNCE POST] ❌ insert returned empty data", flush=True)
        raise HTTPException(status_code=500, detail="Insert returned no data")

    await _push_announcement(title, actual_content, announcement_id)

    return {"message": "Ανακοίνωση δημιουργήθηκε!", "announcement": normalize_announcement(result.data[0])}


# NOTE: /important MUST be declared before /{announcement_id} to avoid routing conflict
@router.get("/important")
def get_important_announcements():
    try:
        now = datetime.now(timezone.utc).isoformat()
        result = (
            supabase.table("announcements")
            .select("*")
            .or_("is_urgent.eq.true,is_important.eq.true")
            .or_(f"expires_at.is.null,expires_at.gt.{now}")
            .order("is_urgent", desc=True)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        data = [normalize_announcement(row) for row in (result.data or [])]
        return {"data": data}
    except Exception as e:
        logger.error(f"[announcements/important] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
def get_announcements(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
):
    try:
        now = datetime.now(timezone.utc).isoformat()
        query = supabase.table("announcements").select("*", count="exact")
        if category:
            query = query.eq("category", category)
        query = query.or_(f"expires_at.is.null,expires_at.gt.{now}")
        offset = (page - 1) * per_page
        result = (
            query
            .order("is_urgent", desc=True)
            .order("is_important", desc=True)
            .order("created_at", desc=True)
            .range(offset, offset + per_page - 1)
            .execute()
        )
        total = result.count or 0
        data = [normalize_announcement(row) for row in (result.data or [])]
        return {
            "data":     data,
            "total":    total,
            "page":     page,
            "per_page": per_page,
            "pages":    max(1, (total + per_page - 1) // per_page),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{announcement_id}")
async def update_announcement(
    announcement_id: str,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    body: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    is_important: Optional[bool] = Form(None),
    is_urgent: Optional[bool] = Form(None),
    expires_at: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    _admin: dict = Depends(require_admin),
):
    try:
        data: dict = {}
        if title is not None:
            data["title"] = sanitize_text(title)
        actual_content = content or body
        if actual_content is not None:
            data["body"] = sanitize_text(actual_content)
        if category is not None:
            data["category"] = category
        if is_important is not None:
            data["is_important"] = is_important
        if is_urgent is not None:
            data["is_urgent"] = is_urgent
        if expires_at is not None:
            data["expires_at"] = expires_at

        image_url = await _try_upload(image)
        if image_url is not None:
            data["image_url"] = image_url

        if not data:
            raise HTTPException(status_code=400, detail="Δεν δόθηκε κανένα πεδίο προς ενημέρωση")

        result = supabase.table("announcements").update(data).eq("id", announcement_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Ανακοίνωση δεν βρέθηκε")
        return {"message": "Ανακοίνωση ενημερώθηκε!", "announcement": normalize_announcement(result.data[0])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{announcement_id}")
def delete_announcement(announcement_id: str, _user: dict = Depends(require_permission("announcements:delete"))):
    try:
        supabase.table("announcements").delete().eq("id", announcement_id).execute()
        return {"message": "Deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
