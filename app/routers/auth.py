import asyncio
import hashlib
import logging
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from supabase import create_client

from app.config import settings
from app.database import supabase, get_supabase
from app.dependencies import get_current_user
from app.limiter import limiter
from app.models.schemas import UserRegister, UserLogin
from app.services.email_service import send_email

logger = logging.getLogger(__name__)
router = APIRouter()

BACKEND_URL = settings.backend_url
_MAX_ATTEMPTS = 5
_BLOCK_MINUTES = 15
_auth_bearer = HTTPBearer()


# ── Pydantic models ───────────────────────────────────────────────────────────

class FCMTokenUpdate(BaseModel):
    user_id: str
    fcm_token: str

class ResendVerificationRequest(BaseModel):
    email: str

class RefreshRequest(BaseModel):
    refresh_token: str

class MFASetupRequest(BaseModel):
    friendly_name: str = "Δήμος Ηρακλείου"

class MFAVerifyRequest(BaseModel):
    factor_id: str
    code: str

class MFADisableRequest(BaseModel):
    factor_id: str
    code: str

class MFARecoveryRequest(BaseModel):
    email: str
    code: str


# ── HTML templates ────────────────────────────────────────────────────────────

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


def _new_device_html(ip: str, device: str, when: str) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <div style="background:#d97706;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2>&#9888;&#65039; Νέα σύνδεση από νέα συσκευή</h2>
      </div>
      <div style="padding:20px;border:1px solid #e5e7eb;border-radius:0 0 8px 8px">
        <p>Εντοπίστηκε νέα σύνδεση στον λογαριασμό σας στο σύστημα του Δήμου Ηρακλείου.</p>
        <table style="border-collapse:collapse;width:100%;margin-top:12px">
          <tr>
            <td style="padding:6px;color:#6b7280;width:130px">Συσκευή</td>
            <td style="padding:6px;font-weight:bold">{device}</td>
          </tr>
          <tr>
            <td style="padding:6px;color:#6b7280">Διεύθυνση IP</td>
            <td style="padding:6px;font-weight:bold">{ip}</td>
          </tr>
          <tr>
            <td style="padding:6px;color:#6b7280">Ώρα</td>
            <td style="padding:6px;font-weight:bold">{when}</td>
          </tr>
        </table>
        <p style="margin-top:16px;color:#dc2626;font-weight:bold">
          Αν δεν συνδεθήκατε εσείς, αλλάξτε αμέσως τον κωδικό σας.
        </p>
      </div>
    </div>
    """


# ── Shared helpers ────────────────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _parse_device_label(user_agent: str) -> str:
    ua = user_agent.lower()
    if "iphone" in ua or ("android" in ua and "mobile" in ua):
        return "Mobile"
    if "ipad" in ua or "tablet" in ua:
        return "Tablet"
    if "windows" in ua:
        return "Windows PC"
    if "macintosh" in ua or "mac os x" in ua:
        return "Mac"
    if "linux" in ua:
        return "Linux"
    return "Unknown Device"


def _make_user_client(access_token: str):
    """Per-request Supabase client scoped to the user's session (for MFA calls)."""
    try:
        client = create_client(settings.supabase_url, settings.supabase_service_key)
        client.auth.set_session(access_token, "")
        return client
    except Exception:
        raise HTTPException(status_code=401, detail="Μη έγκυρο token.")


# ── B. Brute-force / account lockout ─────────────────────────────────────────

def _check_lockout(email: str) -> None:
    """Raise 429 if >=5 failed attempts for this email in the last 15 min."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=_BLOCK_MINUTES)).isoformat()
    try:
        result = (
            get_supabase()
            .table("login_attempts")
            .select("id", count="exact")
            .eq("email", email)
            .eq("success", False)
            .gte("created_at", cutoff)
            .execute()
        )
        if (result.count or 0) >= _MAX_ATTEMPTS:
            raise HTTPException(
                status_code=429,
                detail="Ο λογαριασμός κλειδώθηκε προσωρινά. Παρακαλώ δοκιμάστε ξανά σε 15 λεπτά.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[LOCKOUT CHECK] {e}")


def _record_attempt(email: str, ip: str, success: bool) -> None:
    try:
        get_supabase().table("login_attempts").insert({
            "email": email,
            "ip": ip,
            "success": success,
        }).execute()
    except Exception as e:
        logger.warning(f"[ATTEMPT RECORD] {e}")


# ── C. Recovery code generation ───────────────────────────────────────────────

def _generate_recovery_codes(user_id: str) -> list:
    """Generate 10 codes, store SHA-256 hashes, return plaintexts once."""
    client = get_supabase()
    codes, rows = [], []
    for _ in range(10):
        code = secrets.token_hex(16)   # 128-bit entropy, 32 hex chars
        rows.append({
            "user_id":   user_id,
            "code_hash": hashlib.sha256(code.encode()).hexdigest(),
            "used":      False,
        })
        codes.append(code)
    # Rotate: delete old unused codes first
    client.table("mfa_recovery_codes").delete().eq("user_id", user_id).eq("used", False).execute()
    client.table("mfa_recovery_codes").insert(rows).execute()
    return codes


# ── D. Login session tracking ─────────────────────────────────────────────────

async def _record_login_session(user_id: str, ip: str, user_agent: str, email: str) -> None:
    """Insert session row; email the user if this is a new device. Never raises."""
    client = get_supabase()
    try:
        ua_stored = user_agent[:512]
        existing = (
            client.table("login_sessions")
            .select("id")
            .eq("user_id", user_id)
            .eq("user_agent", ua_stored)
            .limit(1)
            .execute()
        )
        is_new_device = not existing.data
        device_label = _parse_device_label(user_agent)

        client.table("login_sessions").insert({
            "user_id":      user_id,
            "ip":           ip,
            "user_agent":   ua_stored,
            "device_label": device_label,
        }).execute()

        if is_new_device and email:
            when = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
            try:
                await send_email(
                    to=email,
                    subject="Νέα σύνδεση από νέα συσκευή — Δήμος Ηρακλείου",
                    html=_new_device_html(ip, device_label, when),
                )
            except Exception as e:
                logger.warning(f"[NEW DEVICE EMAIL] {e}")
    except Exception as e:
        logger.warning(f"[LOGIN SESSION] {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Existing endpoints (unchanged behaviour)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/register")
async def register(user: UserRegister):
    try:
        result = supabase.auth.sign_up({"email": user.email, "password": user.password})

        if result.user:
            uid = result.user.id
            supabase.table("users").insert({
                "id": uid, "full_name": user.full_name,
                "phone": user.phone, "role": "citizen",
            }).execute()

            token = secrets.token_urlsafe(32)
            supabase.table("users").update({"verification_token": token}).eq("id", uid).execute()

            try:
                await send_email(
                    to=user.email,
                    subject="Επιβεβαίωση email — Δήμος Ηρακλείου",
                    html=_verification_html(token),
                )
            except Exception as e:
                logger.error(f"Verification email failed for {uid}: {e}")

        return {"message": "Εγγραφή επιτυχής! Ελέγξτε το email σας.", "user_id": result.user.id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/verify/{token}", response_class=HTMLResponse)
def verify_email(token: str):
    result = supabase.table("users").select("id").eq("verification_token", token).execute()
    if not result.data:
        raise HTTPException(status_code=400, detail="Μη έγκυρος ή ληγμένος σύνδεσμος.")
    uid = result.data[0]["id"]
    supabase.table("users").update({"email_verified": True, "verification_token": None}).eq("id", uid).execute()
    return """
    <html>
    <body style="font-family:Arial,sans-serif;max-width:600px;margin:60px auto;text-align:center">
      <h2>&#9989; Email επιβεβαιώθηκε!</h2>
      <p>Μπορείς τώρα να συνδεθείς στην εφαρμογή.</p>
    </body>
    </html>
    """


# ── POST /auth/login  (hooked: lockout + MFA check + session tracking) ────────

@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, user: UserLogin):
    ip = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "Unknown")

    # B — lockout check (email-based)
    _check_lockout(user.email)

    try:
        result = supabase.auth.sign_in_with_password({"email": user.email, "password": user.password})
    except Exception:
        _record_attempt(user.email, ip, False)
        raise HTTPException(status_code=401, detail="Λάθος email ή password")

    _record_attempt(user.email, ip, True)

    # Email verification gate
    user_row = supabase.table("users").select("id, email_verified, role").eq("id", result.user.id).execute()
    if user_row.data and not user_row.data[0].get("email_verified", False):
        raise HTTPException(status_code=403, detail="Παρακαλώ επιβεβαιώστε το email σας πρώτα.")

    user_profile = user_row.data[0] if user_row.data else {}

    # A — MFA enforcement for admins
    if user_profile.get("role") == "admin":
        try:
            aal = supabase.auth.mfa.get_authenticator_assurance_level()
            current_level = getattr(aal, "current_level", "aal1")
            next_level    = getattr(aal, "next_level",    "aal1")

            if next_level == "aal2" and current_level == "aal1":
                # Factor enrolled but TOTP challenge not yet completed
                factors   = supabase.auth.mfa.list_factors()
                totp_list = getattr(factors, "totp", []) or []
                verified  = [f for f in totp_list if getattr(f, "status", "") == "verified"]
                return {
                    "mfa_required": True,
                    "factor_id":    verified[0].id if verified else None,
                    "access_token": result.session.access_token,
                    "user_id":      result.user.id,
                }

            if next_level == "aal1":
                # No verified factor at all — soft-enforce setup
                factors   = supabase.auth.mfa.list_factors()
                totp_list = getattr(factors, "totp", []) or []
                if not any(getattr(f, "status", "") == "verified" for f in totp_list):
                    return {
                        "mfa_setup_required": True,
                        "access_token":  result.session.access_token,
                        "refresh_token": result.session.refresh_token,
                        "user_id":       result.user.id,
                        "email":         result.user.email,
                    }
        except Exception as mfa_err:
            logger.warning(f"[MFA ENFORCEMENT] {mfa_err}")

    # D — record session; fire-and-forget (must not block login on failure)
    asyncio.create_task(_record_login_session(
        user_id=result.user.id,
        ip=ip,
        user_agent=user_agent,
        email=result.user.email,
    ))

    return {
        "access_token":  result.session.access_token,
        "refresh_token": result.session.refresh_token,
        "user_id":       result.user.id,
        "email":         result.user.email,
    }


@router.post("/refresh")
@limiter.limit("30/minute")
def refresh_token(request: Request, payload: RefreshRequest):
    try:
        result = supabase.auth.refresh_session(payload.refresh_token)
        if not result.session:
            raise HTTPException(status_code=401, detail="Μη έγκυρο refresh token.")
        return {"access_token": result.session.access_token, "refresh_token": result.session.refresh_token}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Μη έγκυρο refresh token.")


@router.post("/logout")
def logout():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    return {"message": "Αποσύνδεση επιτυχής."}


@router.post("/resend-verification")
async def resend_verification(payload: ResendVerificationRequest):
    user_row = supabase.table("users").select("id, email_verified").eq("email", payload.email).execute()
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
    except Exception as e:
        logger.error(f"Resend verification email failed for {uid}: {e}")
    return {"message": "Ο σύνδεσμος επιβεβαίωσης εστάλη εκ νέου."}


@router.post("/fcm-token")
def update_fcm_token(data: FCMTokenUpdate):
    try:
        supabase.table("users").update({"fcm_token": data.fcm_token}).eq("id", data.user_id).execute()
        return {"message": "FCM token ενημερώθηκε!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# A. MFA (TOTP)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/mfa/setup")
async def mfa_setup(
    req: MFASetupRequest,
    credentials: HTTPAuthorizationCredentials = Security(_auth_bearer),
):
    """Enroll a TOTP factor. Returns the otpauth URI + base32 secret for QR rendering.
    Factor is NOT active until /mfa/verify completes the challenge."""
    user_client = _make_user_client(credentials.credentials)
    try:
        resp = user_client.auth.mfa.enroll({
            "factor_type": "totp",
            "friendly_name": req.friendly_name,
        })
        totp = resp.totp
        return {
            "factor_id": resp.id,
            "totp_uri":  totp.uri,
            "secret":    totp.secret,
            "qr_code":   totp.qr_code,   # SVG data URI — render directly in <img src>
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MFA SETUP] {e}")
        raise HTTPException(status_code=400, detail=f"Σφάλμα ρύθμισης MFA: {e}")


@router.post("/mfa/verify")
async def mfa_verify(
    req: MFAVerifyRequest,
    credentials: HTTPAuthorizationCredentials = Security(_auth_bearer),
):
    """Complete TOTP enrollment: create challenge → verify code → activate factor.
    Returns 10 single-use recovery codes (plaintext, shown once only)."""
    user_client = _make_user_client(credentials.credentials)
    try:
        challenge    = user_client.auth.mfa.challenge({"factor_id": req.factor_id})
        verify_resp  = user_client.auth.mfa.verify({
            "factor_id":    req.factor_id,
            "challenge_id": challenge.id,
            "code":         req.code,
        })

        user_resp      = user_client.auth.get_user()
        user_id        = user_resp.user.id
        recovery_codes = _generate_recovery_codes(user_id)
        new_session    = verify_resp.session

        return {
            "message":        "MFA ενεργοποιήθηκε επιτυχώς!",
            "recovery_codes": recovery_codes,
            "access_token":   new_session.access_token  if new_session else None,
            "refresh_token":  new_session.refresh_token if new_session else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[MFA VERIFY] {e}")
        raise HTTPException(status_code=400, detail="Μη έγκυρος κωδικός TOTP.")


@router.post("/mfa/disable")
async def mfa_disable(
    req: MFADisableRequest,
    credentials: HTTPAuthorizationCredentials = Security(_auth_bearer),
):
    """Verify a live TOTP code then unenroll the factor and delete recovery codes."""
    user_client = _make_user_client(credentials.credentials)
    try:
        challenge = user_client.auth.mfa.challenge({"factor_id": req.factor_id})
        user_client.auth.mfa.verify({
            "factor_id":    req.factor_id,
            "challenge_id": challenge.id,
            "code":         req.code,
        })
        user_client.auth.mfa.unenroll({"factor_id": req.factor_id})

        uid = user_client.auth.get_user().user.id
        get_supabase().table("mfa_recovery_codes").delete().eq("user_id", uid).execute()

        return {"message": "MFA απενεργοποιήθηκε."}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[MFA DISABLE] {e}")
        raise HTTPException(status_code=400, detail="Σφάλμα απενεργοποίησης MFA. Ελέγξτε τον κωδικό TOTP.")


@router.get("/mfa/status")
async def mfa_status(credentials: HTTPAuthorizationCredentials = Security(_auth_bearer)):
    """Return enrolled TOTP factors and whether MFA is currently active."""
    user_client = _make_user_client(credentials.credentials)
    try:
        factors   = user_client.auth.mfa.list_factors()
        totp_list = getattr(factors, "totp", []) or []
        enabled   = any(getattr(f, "status", "") == "verified" for f in totp_list)
        return {
            "enabled": enabled,
            "factors": [
                {
                    "id":            f.id,
                    "status":        getattr(f, "status", ""),
                    "friendly_name": getattr(f, "friendly_name", ""),
                    "factor_type":   getattr(f, "factor_type", "totp"),
                }
                for f in totp_list
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[MFA STATUS] {e}")
        raise HTTPException(status_code=400, detail="Σφάλμα ανάκτησης κατάστασης MFA.")


# ── C. Recovery code bypass ───────────────────────────────────────────────────

@router.post("/mfa/recovery")
async def mfa_recovery(req: MFARecoveryRequest):
    """Use a one-time recovery code to bypass the TOTP challenge.
    Looks up the user by email, hashes the supplied code and matches against stored hashes.
    Returns generic 400 for both bad email and bad code (no user enumeration)."""
    client = get_supabase()

    user_row = client.table("users").select("id").eq("email", req.email).execute()
    if not user_row.data:
        raise HTTPException(status_code=400, detail="Μη έγκυρο email ή κωδικός ανάκτησης.")

    user_id   = user_row.data[0]["id"]
    code_hash = hashlib.sha256(req.code.encode()).hexdigest()

    match = (
        client.table("mfa_recovery_codes")
        .select("id")
        .eq("user_id", user_id)
        .eq("code_hash", code_hash)
        .eq("used", False)
        .limit(1)
        .execute()
    )
    if not match.data:
        raise HTTPException(status_code=400, detail="Μη έγκυρο email ή κωδικός ανάκτησης.")

    client.table("mfa_recovery_codes").update({"used": True}).eq("id", match.data[0]["id"]).execute()

    logger.info(f"[MFA RECOVERY] Recovery code consumed for user_id={user_id}")
    return {"message": "Ο κωδικός ανάκτησης έγινε αποδεκτός. Μπορείτε να συνεχίσετε."}


# ── D. Login history ──────────────────────────────────────────────────────────

@router.get("/login-history")
async def login_history(user: dict = Depends(get_current_user)):
    """Last 10 login sessions for the authenticated user."""
    result = (
        get_supabase()
        .table("login_sessions")
        .select("id, ip, device_label, created_at")
        .eq("user_id", user["id"])
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    return {"sessions": result.data or []}


# ── E. Sign out everywhere ────────────────────────────────────────────────────

@router.post("/sessions/revoke-all")
async def revoke_all_sessions(
    credentials: HTTPAuthorizationCredentials = Security(_auth_bearer),
    _user: dict = Depends(get_current_user),  # confirms token is valid first
):
    """Force global sign-out of all devices via the service_role admin API."""
    try:
        get_supabase().auth.admin.sign_out(credentials.credentials, scope="global")
    except Exception as e:
        logger.error(f"[REVOKE ALL] {e}")
        raise HTTPException(status_code=500, detail="Σφάλμα κατά τον τερματισμό όλων των συνεδριών.")
    return {"message": "Όλες οι συνεδρίες τερματίστηκαν επιτυχώς."}
