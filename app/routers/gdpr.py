import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel
from typing import Optional

from app.database import get_auth_client, supabase

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_self(authorization: Optional[str], user_id: str) -> str:
    """Verify Bearer token and that it belongs to user_id. Returns verified uid."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header απαιτείται.")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        resp = get_auth_client().auth.get_user(token)
        if not resp or not resp.user:
            raise HTTPException(status_code=401, detail="Μη έγκυρο token.")
        if resp.user.id != user_id:
            raise HTTPException(status_code=403, detail="Δεν έχεις πρόσβαση σε αυτά τα δεδομένα.")
        return resp.user.id
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Μη έγκυρο ή ληγμένο token.")


# ── 1. GET /gdpr/export ──────────────────────────────────────────────────────

@router.get("/export")
def export_data(
    user_id: str = Query(...),
    authorization: Optional[str] = Header(None),
):
    _require_self(authorization, user_id)
    try:
        user_row = supabase.table("users").select("*").eq("id", user_id).execute()
        reports = supabase.table("reports").select("*").eq("user_id", user_id).execute()
        points = supabase.table("user_points").select("*").eq("user_id", user_id).execute()
        votes = supabase.table("poll_votes").select("*").eq("user_id", user_id).execute()
        appts = supabase.table("appointments").select("*").eq("user_id", user_id).execute()
        consents = supabase.table("consent").select("*").eq("user_id", user_id).execute()

        return {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "user": user_row.data[0] if user_row.data else {},
            "reports": reports.data or [],
            "user_points": points.data[0] if points.data else {},
            "poll_votes": votes.data or [],
            "appointments": appts.data or [],
            "consent": consents.data or [],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GDPR export error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── 2. DELETE /gdpr/delete ───────────────────────────────────────────────────

class DeleteRequest(BaseModel):
    user_id: str


@router.delete("/delete")
def delete_account(
    payload: DeleteRequest,
    authorization: Optional[str] = Header(None),
):
    uid = _require_self(authorization, payload.user_id)
    try:
        # Anonymise user row (keep id so FK references stay valid)
        supabase.table("users").update({
            "email": f"deleted_{uid}@deleted.com",
            "full_name": "Διαγραμμένος Χρήστης",
            "phone": None,
        }).eq("id", uid).execute()

        # Anonymise reports (preserve user_id FK)
        supabase.table("reports").update({
            "description": "[διαγράφηκε]",
            "image_url": None,
        }).eq("user_id", uid).execute()

        # Hard-delete rows with no downstream FK dependents
        supabase.table("poll_votes").delete().eq("user_id", uid).execute()
        supabase.table("appointments").delete().eq("user_id", uid).execute()
        supabase.table("user_points").delete().eq("user_id", uid).execute()
        supabase.table("consent").delete().eq("user_id", uid).execute()

        return {"message": "Τα δεδομένα σου διαγράφηκαν."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GDPR delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── 3. POST /gdpr/consent ────────────────────────────────────────────────────

class ConsentRequest(BaseModel):
    user_id: str
    consent_type: str
    granted: bool


@router.post("/consent")
def record_consent(payload: ConsentRequest):
    try:
        # Upsert: one record per (user_id, consent_type)
        existing = (
            supabase.table("consent")
            .select("id")
            .eq("user_id", payload.user_id)
            .eq("consent_type", payload.consent_type)
            .execute()
        )
        if existing.data:
            supabase.table("consent").update({
                "granted": payload.granted,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", existing.data[0]["id"]).execute()
        else:
            supabase.table("consent").insert({
                "user_id": payload.user_id,
                "consent_type": payload.consent_type,
                "granted": payload.granted,
            }).execute()

        return {"message": "Consent αποθηκεύτηκε."}
    except Exception as e:
        logger.error(f"GDPR consent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── 4. GET /gdpr/consent ─────────────────────────────────────────────────────

@router.get("/consent")
def get_consent(user_id: str = Query(...)):
    try:
        result = supabase.table("consent").select("*").eq("user_id", user_id).execute()
        return {"consent": result.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
