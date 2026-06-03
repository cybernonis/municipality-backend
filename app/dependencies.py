import logging
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database import get_supabase

logger = logging.getLogger(__name__)
_bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> dict:
    token = credentials.credentials
    client = get_supabase()
    try:
        user_resp = client.auth.get_user(token)
        if not user_resp or not user_resp.user:
            raise HTTPException(status_code=401, detail="Μη έγκυρο token.")
        uid = user_resp.user.id
        profile = (
            client.table("users")
            .select("id, full_name, role, email_verified")
            .eq("id", uid)
            .single()
            .execute()
        )
        if not profile.data:
            raise HTTPException(status_code=401, detail="Χρήστης δεν βρέθηκε.")
        return profile.data
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[AUTH] Token validation failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=401, detail="Μη έγκυρο token.")


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Απαιτούνται δικαιώματα διαχειριστή.")
    return user


async def require_worker(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("admin", "worker"):
        raise HTTPException(status_code=403, detail="Απαιτούνται δικαιώματα εργαζομένου.")
    return user
