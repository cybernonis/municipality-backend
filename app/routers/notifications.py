from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Body

from app.database import supabase
from app.services.notification_service import send_push_notification, send_push_to_multiple

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.post("/register-token")
async def register_fcm_token(payload: dict = Body(...)):
    """Register FCM token για user."""
    user_id = payload.get("user_id")
    token = payload.get("token")

    if not user_id or not token:
        raise HTTPException(400, "Απαιτούνται user_id και token")

    try:
        supabase.table("users").update({
            "fcm_token": token,
            "fcm_token_updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", user_id).execute()
        return {"success": True, "user_id": user_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/test")
async def send_test_notification(payload: dict = Body(...)):
    """Test notification σε συγκεκριμένο user (admin testing)."""
    user_id = payload.get("user_id")
    title = payload.get("title", "Test Notification")
    body = payload.get("body", "Αυτό είναι ένα δοκιμαστικό μήνυμα")

    if not user_id:
        raise HTTPException(400, "Απαιτείται user_id")

    user_result = supabase.table("users").select("fcm_token").eq("id", user_id).execute()

    if not user_result.data or not user_result.data[0].get("fcm_token"):
        raise HTTPException(404, "User δεν έχει FCM token. Πρέπει να ανοίξει το mobile app.")

    token = user_result.data[0]["fcm_token"]
    success = await send_push_notification(token, title, body, {"type": "test"})

    return {
        "success": success,
        "user_id": user_id,
        "message": "Notification sent" if success else "Failed (Firebase not configured?)",
    }


@router.post("/broadcast")
async def broadcast_notification(payload: dict = Body(...)):
    """Broadcast σε όλους τους users (admin only)."""
    title = payload.get("title")
    body = payload.get("body")
    extra_data = payload.get("data", {})

    if not title or not body:
        raise HTTPException(400, "Απαιτούνται title και body")

    try:
        result = supabase.table("users").select("id, fcm_token").not_.is_("fcm_token", "null").execute()
        users = result.data or []
        tokens = [u["fcm_token"] for u in users if u.get("fcm_token")]

        if not tokens:
            return {"sent": 0, "failed": 0, "total_users": 0, "message": "Κανένας user με FCM token"}

        success = await send_push_to_multiple(tokens, title, body, extra_data)
        return {
            "success": success,
            "total_users": len(tokens),
            "message": f"Broadcast εστάλη σε {len(tokens)} συσκευές",
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/tokens-count")
async def get_active_tokens_count():
    """Πόσοι users έχουν registered FCM tokens (για debugging)."""
    try:
        result = supabase.table("users").select("id, fcm_token").not_.is_("fcm_token", "null").execute()
        tokens = [u for u in (result.data or []) if u.get("fcm_token")]
        return {"active_tokens": len(tokens)}
    except Exception as e:
        raise HTTPException(500, str(e))
