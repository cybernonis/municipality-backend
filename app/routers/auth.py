import logging
import os
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.database import supabase
from app.limiter import limiter
from app.models.schemas import UserRegister, UserLogin
from app.services.email_service import send_email

logger = logging.getLogger(__name__)
router = APIRouter()

BACKEND_URL = os.getenv("BACKEND_URL", "https://municipality-backend-production.up.railway.app")


class FCMTokenUpdate(BaseModel):
    user_id: str
    fcm_token: str


class ResendVerificationRequest(BaseModel):
    email: str


def _verification_html(token: str) -> str:
    url = f"{BACKEND_URL}/auth/verify/{token}"
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <div style="background:#1d4ed8;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2>Καλωσήρθες στον Δήμο Ηρακλείου!</h2>
      </div>
      <div style="padding:20px;border:1px solid #e5e7eb;border-radius:0 0 8px 8px">
        <p>Πάτησε τον παρακάτω σύνδεσμο για να επιβεβαιώσεις το email σου:</p>
        <a href="{url}"
           style="background:#1d4ed8;color:white;padding:10px 20px;
                  border-radius:6px;text-decoration:none;display:inline-block;margin-top:10px">
          Επιβεβαίωση Email
        </a>
        <p style="color:#6b7280;margin-top:20px">Ο σύνδεσμος λήγει σε 24 ώρες.</p>
      </div>
    </div>
    """


# ── POST /auth/register ───────────────────────────────────────────────────────

@router.post("/register")
async def register(user: UserRegister):
    try:
        result = supabase.auth.sign_up({
            "email": user.email,
            "password": user.password,
        })

        if result.user:
            user_id = result.user.id
            supabase.table("users").insert({
                "id": user_id,
                "full_name": user.full_name,
                "phone": user.phone,
                "role": "citizen",
            }).execute()

            token = secrets.token_urlsafe(32)
            supabase.table("users").update({
                "verification_token": token,
            }).eq("id", user_id).execute()

            try:
                await send_email(
                    to=user.email,
                    subject="Επιβεβαίωση email — Δήμος Ηρακλείου",
                    html=_verification_html(token),
                )
            except Exception as email_err:
                logger.error(f"Verification email failed for {user_id}: {email_err}")

        return {
            "message": "Εγγραφή επιτυχής! Ελέγξτε το email σας.",
            "user_id": result.user.id,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── GET /auth/verify/{token} ──────────────────────────────────────────────────

@router.get("/verify/{token}", response_class=HTMLResponse)
def verify_email(token: str):
    result = supabase.table("users").select("id").eq("verification_token", token).execute()
    if not result.data:
        raise HTTPException(status_code=400, detail="Μη έγκυρος ή ληγμένος σύνδεσμος.")

    user_id = result.data[0]["id"]
    supabase.table("users").update({
        "email_verified": True,
        "verification_token": None,
    }).eq("id", user_id).execute()

    return """
    <html>
    <body style="font-family:Arial,sans-serif;max-width:600px;margin:60px auto;text-align:center">
      <h2>&#9989; Email επιβεβαιώθηκε!</h2>
      <p>Μπορείς τώρα να συνδεθείς στην εφαρμογή.</p>
    </body>
    </html>
    """


# ── POST /auth/login ──────────────────────────────────────────────────────────

@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, user: UserLogin):
    try:
        result = supabase.auth.sign_in_with_password({
            "email": user.email,
            "password": user.password,
        })

        user_row = (
            supabase.table("users")
            .select("email_verified")
            .eq("id", result.user.id)
            .execute()
        )
        if user_row.data and not user_row.data[0].get("email_verified", False):
            raise HTTPException(
                status_code=403,
                detail="Παρακαλώ επιβεβαιώστε το email σας πρώτα.",
            )

        return {
            "access_token": result.session.access_token,
            "user_id": result.user.id,
            "email": result.user.email,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Λάθος email ή password")


# ── POST /auth/resend-verification ───────────────────────────────────────────

@router.post("/resend-verification")
async def resend_verification(payload: ResendVerificationRequest):
    user_row = (
        supabase.table("users")
        .select("id, email_verified")
        .eq("email", payload.email)
        .execute()
    )

    if not user_row.data:
        raise HTTPException(status_code=400, detail="Ο χρήστης δεν βρέθηκε.")

    user = user_row.data[0]
    if user.get("email_verified", False):
        raise HTTPException(status_code=400, detail="Το email έχει ήδη επιβεβαιωθεί.")

    uid = user["id"]
    token = secrets.token_urlsafe(32)
    supabase.table("users").update({"verification_token": token}).eq("id", uid).execute()

    try:
        await send_email(
            to=payload.email,
            subject="Επιβεβαίωση email — Δήμος Ηρακλείου",
            html=_verification_html(token),
        )
    except Exception as email_err:
        logger.error(f"Resend verification email failed for {uid}: {email_err}")

    return {"message": "Ο σύνδεσμος επιβεβαίωσης εστάλη εκ νέου."}


# ── POST /auth/fcm-token ──────────────────────────────────────────────────────

@router.post("/fcm-token")
def update_fcm_token(data: FCMTokenUpdate):
    try:
        supabase.table("users")\
            .update({"fcm_token": data.fcm_token})\
            .eq("id", data.user_id)\
            .execute()
        return {"message": "FCM token ενημερώθηκε!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
