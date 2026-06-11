import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Security, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.database import supabase
from app.services.storage_service import upload_image

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crew", tags=["Crew Portal"])

_bearer = HTTPBearer()
_JWT_ALGO = "HS256"
_TOKEN_TTL_HOURS = 12

_ALLOWED_TRANSITIONS = {
    "assigned":    "in_progress",
    "in_progress": "resolved",
}


# ── Auth ──────────────────────────────────────────────────────────────────────

@router.post("/login")
def crew_login(payload: dict = Body(...)):
    crew_id = (payload.get("crew_id") or "").strip()
    pin = (payload.get("pin") or "").strip()

    if not crew_id or not pin:
        raise HTTPException(status_code=400, detail="crew_id και pin είναι υποχρεωτικά")

    result = supabase.table("crews").select("id, name, pin").eq("id", crew_id).execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="Άγνωστο συνεργείο")

    crew = result.data[0]
    stored_pin = crew.get("pin") or ""
    if not stored_pin or stored_pin != pin:
        raise HTTPException(status_code=401, detail="Λάθος PIN")

    exp = datetime.now(timezone.utc) + timedelta(hours=_TOKEN_TTL_HOURS)
    token = jwt.encode(
        {"crew_id": crew["id"], "scope": "crew", "exp": exp},
        settings.secret_key,
        algorithm=_JWT_ALGO,
    )
    return {"access_token": token, "crew_id": crew["id"], "crew_name": crew["name"]}


def get_current_crew(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> str:
    token = credentials.credentials
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[_JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token έχει λήξει")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Μη έγκυρο token")
    if data.get("scope") != "crew":
        raise HTTPException(status_code=403, detail="Απαγορεύεται")
    return data["crew_id"]


# ── Reports ───────────────────────────────────────────────────────────────────

_REPORT_SELECT = (
    "id, description, address, latitude, longitude, category, severity, status,"
    " crew_id, department_id, user_id, assigned_to, auto_assigned,"
    " ai_confidence, image_url, created_at,"
    " departments(id, name, slug), crews(id, name, specialty, leader_name)"
)


@router.get("/reports")
def crew_reports(crew_id: str = Depends(get_current_crew)):
    result = (
        supabase.table("reports")
        .select(_REPORT_SELECT)
        .eq("crew_id", crew_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@router.get("/reports/{report_id}")
@router.get("/reports/{report_id}/")
def get_crew_report(report_id: str, crew_id: str = Depends(get_current_crew)):
    result = (
        supabase.table("reports")
        .select(_REPORT_SELECT)
        .eq("id", report_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Αναφορά δεν βρέθηκε")
    report = result.data[0]
    if report.get("crew_id") != crew_id:
        raise HTTPException(status_code=404, detail="Αναφορά δεν βρέθηκε")
    return report


@router.patch("/reports/{report_id}/status")
@router.patch("/reports/{report_id}/status/")
def update_report_status(
    report_id: str,
    payload: dict = Body(...),
    crew_id: str = Depends(get_current_crew),
):
    new_status = (payload.get("status") or "").strip()
    if not new_status:
        raise HTTPException(status_code=400, detail="status είναι υποχρεωτικό")

    report_res = supabase.table("reports").select("id, crew_id, status").eq("id", report_id).execute()
    if not report_res.data:
        raise HTTPException(status_code=404, detail="Αναφορά δεν βρέθηκε")

    report = report_res.data[0]
    if report.get("crew_id") != crew_id:
        raise HTTPException(status_code=403, detail="Η αναφορά δεν ανήκει στο συνεργείο σας")

    current = report.get("status")
    if _ALLOWED_TRANSITIONS.get(current) != new_status:
        raise HTTPException(
            status_code=400,
            detail=f"Μη επιτρεπτή μετάβαση κατάστασης: {current} → {new_status}",
        )

    supabase.table("reports").update({"status": new_status}).eq("id", report_id).execute()
    supabase.table("report_updates").insert({
        "report_id": report_id,
        "status": new_status,
        "comment": f"Συνεργείο → {new_status}",
    }).execute()

    return {"success": True, "report_id": report_id, "status": new_status}


@router.post("/reports/{report_id}/note")
@router.post("/reports/{report_id}/note/")
async def add_crew_note(
    report_id: str,
    text: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    crew_id: str = Depends(get_current_crew),
):
    try:
        report_res = supabase.table("reports").select("id, crew_id").eq("id", report_id).execute()
        if not report_res.data:
            raise HTTPException(status_code=404, detail="Αναφορά δεν βρέθηκε")
        if report_res.data[0].get("crew_id") != crew_id:
            raise HTTPException(status_code=403, detail="Η αναφορά δεν ανήκει στο συνεργείο σας")

        if not text and not photo:
            raise HTTPException(status_code=400, detail="Απαιτείται κείμενο ή φωτογραφία")

        photo_url: Optional[str] = None
        if photo:
            photo_url = await upload_image(photo)

        if photo_url:
            comment = f"{text}\n[photo: {photo_url}]".strip() if text else f"[photo: {photo_url}]"
        else:
            comment = text or ""

        supabase.table("report_updates").insert({
            "report_id": report_id,
            "status": "note",
            "comment": comment,
        }).execute()

        return {"success": True, "photo_url": photo_url, "comment": comment}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[CREW NOTE] report_id=%s error=%s", report_id, exc)
        raise HTTPException(status_code=500, detail="Σφάλμα κατά την αποθήκευση της σημείωσης")


@router.patch("/reports/{report_id}/blocker")
@router.patch("/reports/{report_id}/blocker/")
def set_blocker(
    report_id: str,
    payload: dict = Body(...),
    crew_id: str = Depends(get_current_crew),
):
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason είναι υποχρεωτικό")

    report_res = supabase.table("reports").select("id, crew_id").eq("id", report_id).execute()
    if not report_res.data:
        raise HTTPException(status_code=404, detail="Αναφορά δεν βρέθηκε")
    if report_res.data[0].get("crew_id") != crew_id:
        raise HTTPException(status_code=403, detail="Η αναφορά δεν ανήκει στο συνεργείο σας")

    supabase.table("report_updates").insert({
        "report_id": report_id,
        "status": "blocked",
        "comment": f"BLOCKER: {reason}",
    }).execute()

    return {"success": True, "report_id": report_id, "blocker": reason}
