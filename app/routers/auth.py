import logging
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.config import settings
from app.database import supabase, get_supabase
from app.limiter import limiter
from app.models.schemas import UserRegister, UserLogin
from app.services.email_service import send_email

logger = logging.getLogger(__name__)
router = APIRouter()

BACKEND_URL = settings.backend_url
_MAX_ATTEMPTS = 5
_BLOCK_MINUTES = 15


class FCMTokenUpdate(BaseModel):
    user_id: str
    fcm_token: str


class ResendVerificationRequest(BaseModel):
    email: str


class RefreshRequest(BaseModel):
    refresh_token: str


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


# ── Brute-force helpers ───────────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_brute_force(ip: str) -> None:
    """Raise 429 if IP is currently blocked."""
    client = get_supabase()
    now = datetime.now(timezone.utc)
    try:
        row = client.table("login_attempts").select("attempts, blocked_until").eq("ip_address", ip).execute()
        if not row.data:
            return
        rec = row.data[0]
        blocked_until = rec.get("blocked_until")
        if blocked_until:
            bu = datetime.fromisoformat(blocked_until.replace("Z", "+00:00"))
            if now < bu:
                remaining = int((bu - now).total_seconds() / 60) + 1
                raise HTTPException(
                    status_code=429,
                    detail=f"Πολλές αποτυχημένες προσπάθειες. Δοκιμάστε ξανά σε {remaining} λεπτά.",
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[BRUTE FORCE CHECK] {e}")


def _record_failed_attempt(ip: str) -> None:
    client = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    try:
        row = client.table("login_attempts").select("id, attempts").eq("ip_address", ip).execute()
        if not row.data:
            client.table("login_attempts").insert({
                "ip_address": ip, "attempts": 1, "last_attempt": now,
            }).execute()
        else:
            new_attempts = row.data[0]["attempts"] + 1
            update: dict = {"attempts": new_attempts, "last_attempt": now}
            if new_attempts >= _MAX_ATTEMPTS:
                update["blocked_until"] = (
                    datetime.now(timezone.utc) + timedelta(minutes=_BLOCK_MINUTES)
                ).isoformat()
            client.table("login_attempts").update(update).eq("ip_address", ip).execute()
    except Exception as e:
        logger.warning(f"[BRUTE FORCE RECORD] {e}")


def _clear_attempts(ip: str) -> None:
    try:
        get_supabase().table("login_attempts").delete().eq("ip_address", ip).execute()
    except Exception as e:
        logger.warning(f"[BRUTE FORCE CLEAR] {e}")


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
    ip = _get_client_ip(request)
    _check_brute_force(ip)

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

        _clear_attempts(ip)

        return {
            "access_token":  result.session.access_token,
            "refresh_token": result.session.refresh_token,
            "user_id":       result.user.id,
            "email":         result.user.email,
        }
    except HTTPException:
        raise
    except Exception:
        _record_failed_attempt(ip)
        raise HTTPException(status_code=401, detail="Λάθος email ή password")


# ── POST /auth/refresh ────────────────────────────────────────────────────────

@router.post("/refresh")
@limiter.limit("30/minute")
def refresh_token(request: Request, payload: RefreshRequest):
    try:
        result = supabase.auth.refresh_session(payload.refresh_token)
        if not result.session:
            raise HTTPException(status_code=401, detail="Μη έγκυρο refresh token.")
        return {
            "access_token":  result.session.access_token,
            "refresh_token": result.session.refresh_token,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Μη έγκυρο refresh token.")


# ── POST /auth/logout ─────────────────────────────────────────────────────────

@router.post("/logout")
def logout():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    return {"message": "Αποσύνδεση επιτυχής."}


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
