import logging
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database import get_supabase
from app.services.rbac import has_permission

logger = logging.getLogger(__name__)
_bearer = HTTPBearer()


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _write_audit(
    user_id: str, role: str, action: str, resource: str, allowed: bool, ip: str
) -> None:
    try:
        get_supabase().table("permission_audit").insert({
            "user_id":  user_id,
            "role":     role,
            "action":   action,
            "resource": resource,
            "allowed":  allowed,
            "ip":       ip,
        }).execute()
    except Exception as e:
        logger.warning(f"[RBAC AUDIT] insert failed: {e}")


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


async def require_admin(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    if user.get("role") != "admin":
        _write_audit(user["id"], user.get("role", ""), "access", "admin", False, _get_ip(request))
        raise HTTPException(status_code=403, detail="Απαιτούνται δικαιώματα διαχειριστή.")
    return user


async def require_worker(
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    if user.get("role") not in ("admin", "worker"):
        _write_audit(user["id"], user.get("role", ""), "access", "worker", False, _get_ip(request))
        raise HTTPException(status_code=403, detail="Απαιτούνται δικαιώματα εργαζομένου.")
    return user


def require_permission(permission: str):
    """Dependency factory. Always writes a permission_audit row (allow and deny)."""
    resource, _, action = permission.partition(":")

    async def _check(
        request: Request,
        user: dict = Depends(get_current_user),
    ) -> dict:
        role = user.get("role", "")
        allowed = has_permission(role, permission)
        _write_audit(user["id"], role, action, resource, allowed, _get_ip(request))
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail="Δεν έχετε δικαίωμα για αυτή την ενέργεια.",
            )
        return user

    return _check
