import time
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.database import get_supabase
from app.dependencies import require_admin, require_permission
from app.services.ai_actions import parse_admin_intent, execute_action, ACTIONS_REGISTRY

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-actions", tags=["AI Actions"])


class IntentRequest(BaseModel):
    message:  str
    user_id:  str
    context:  dict = {}


class ExecuteRequest(BaseModel):
    action:          str
    params:          dict
    user_id:         str
    confirmation_id: str  # audit_id from /parse


@router.post("/parse")
async def parse_intent(req: IntentRequest, _admin: dict = Depends(require_admin)):
    """Step 1 — Parse admin message → return intent + audit_id"""
    start = time.time()
    try:
        intent = await parse_admin_intent(req.message, req.context)
    except Exception as e:
        logger.error(f"[AI ACTIONS /parse] {e}")
        raise HTTPException(status_code=500, detail=f"Σφάλμα ανάλυσης: {str(e)}")

    client = get_supabase()
    audit_row = {
        "user_id":      req.user_id,
        "action_type":  intent.get("action", "UNKNOWN"),
        "user_message": req.message,
        "ai_intent":    intent,
        "params":       intent.get("params", {}),
        "status":       "pending",
        "duration_ms":  int((time.time() - start) * 1000),
    }
    try:
        audit = client.table("ai_action_logs").insert(audit_row).execute()
        audit_id = audit.data[0]["id"]
    except Exception as e:
        logger.error(f"[AI ACTIONS] audit log insert failed: {e}")
        audit_id = None

    action = intent.get("action")
    meta   = ACTIONS_REGISTRY.get(action, {})

    return {
        "audit_id":             audit_id,
        "intent":               intent,
        "requires_confirmation": meta.get("requires_confirmation", False),
        "destructive":          meta.get("destructive", False),
        "read_only":            meta.get("read_only", False),
    }


@router.post("/execute")
async def execute_intent(req: ExecuteRequest, _user: dict = Depends(require_permission("ai_actions:execute"))):
    """Step 2 — Execute confirmed intent"""
    start  = time.time()
    client = get_supabase()

    # Mark as executing
    if req.confirmation_id:
        try:
            client.table("ai_action_logs").update({
                "confirmed": True,
                "status":    "executing",
            }).eq("id", req.confirmation_id).execute()
        except Exception:
            pass

    result = await execute_action(
        action=req.action,
        params=req.params,
        user_id=req.user_id,
        audit_id=req.confirmation_id,
    )

    # Update audit log with final status
    if req.confirmation_id:
        try:
            client.table("ai_action_logs").update({
                "status":        "success" if result["success"] else "failed",
                "result":        result.get("result"),
                "error_message": result.get("error"),
                "duration_ms":   int((time.time() - start) * 1000),
            }).eq("id", req.confirmation_id).execute()
        except Exception as e:
            logger.error(f"[AI ACTIONS] audit log update failed: {e}")

    return result


@router.get("/actions")
def list_available_actions():
    """List all available actions with metadata"""
    return {
        "actions": [
            {"name": name, **meta}
            for name, meta in ACTIONS_REGISTRY.items()
        ],
        "total": len(ACTIONS_REGISTRY),
    }


@router.get("/history/{user_id}")
def action_history(user_id: str, limit: int = 50):
    """Ιστορικό AI ενεργειών χρήστη"""
    try:
        client = get_supabase()
        result = (
            client.table("ai_action_logs")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return {"history": result.data or [], "total": len(result.data or [])}
    except Exception as e:
        logger.error(f"[AI ACTIONS /history] {e}")
        return {"history": [], "total": 0}
