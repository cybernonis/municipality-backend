import asyncio
import logging
import uuid
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form

from app.config import ANTHROPIC_API_KEY
from app.database import supabase
from app.dependencies import require_permission
from app.limiter import limiter
from app.services.ai_service import classify_image, CATEGORIES
from app.services.storage_service import upload_image
from app.utils.sanitize import sanitize_text

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/")
def get_all_reports():
    result = supabase.table("reports")\
        .select("*, departments(name)")\
        .order("created_at", desc=True)\
        .execute()
    return result.data

@router.get("/my")
def get_my_reports(user_id: str):
    result = supabase.table("reports")\
        .select("*, departments(name)")\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .execute()
    return result.data

@router.get("/{report_id}")
def get_report(report_id: str):
    result = supabase.table("reports")\
        .select("*, departments(name), report_updates(*)")\
        .eq("id", report_id)\
        .execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Δεν βρέθηκε")
    return result.data[0]

@router.post("/")
@limiter.limit("20/minute")
async def create_report(
    request: Request,
    latitude: float = Form(...),
    longitude: float = Form(...),
    description: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
):
    try:
        if description:
            description = sanitize_text(description)
        if address:
            address = sanitize_text(address)

        image_url = ""
        ai_result = {"category": "other", "severity": "medium", "confidence": 0.0, "department": "technical_services"}

        if image is not None:
            image_url = await upload_image(image)
            await image.seek(0)
            image_bytes = await image.read()
            ai_result = await classify_image(image_bytes, description)

        dept = supabase.table("departments")\
            .select("id")\
            .eq("slug", ai_result["department"])\
            .execute()

        department_id = dept.data[0]["id"] if dept.data else None

        report_data = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "image_url": image_url,
            "description": description,
            "latitude": latitude,
            "longitude": longitude,
            "address": address,
            "category": ai_result["category"],
            "severity": ai_result["severity"],
            "ai_confidence": ai_result["confidence"],
            "department_id": department_id,
            "status": "submitted"
        }

        result = supabase.table("reports").insert(report_data).execute()

        # Broadcast WebSocket
        try:
            from app.main import manager
            asyncio.create_task(manager.broadcast({
                "type": "new_report",
                "data": {
                    "id": report_data["id"],
                    "category": report_data["category"],
                    "severity": report_data["severity"],
                    "latitude": report_data["latitude"],
                    "longitude": report_data["longitude"],
                    "status": report_data["status"],
                }
            }))
        except Exception as e:
            logger.error(f"WebSocket broadcast error: {e}")

        # Email για high/critical severity
        if report_data["severity"] in ["high", "critical"]:
            try:
                from app.services.email_service import send_high_severity_email
                asyncio.create_task(send_high_severity_email(
                    report_id=report_data["id"][:8],
                    category=report_data["category"],
                    description=description or "Χωρίς περιγραφή",
                    address=address or f"{latitude:.4f}, {longitude:.4f}"
                ))
            except Exception as e:
                logger.error(f"High severity email error: {e}")

        return {"message": "Αναφορά υποβλήθηκε!", "report": result.data[0]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{report_id}")
async def update_report(report_id: str, update: dict):
    try:
        result = supabase.table("reports")\
            .update({"status": update.get("status")})\
            .eq("id", report_id)\
            .execute()

        if update.get("comment"):
            supabase.table("report_updates").insert({
                "report_id": report_id,
                "status": update.get("status"),
                "comment": update.get("comment"),
            }).execute()

        # Push notification στον πολίτη
        try:
            report = result.data[0] if result.data else None
            if report and report.get("user_id") and update.get("status"):
                user = supabase.table("users")\
                    .select("fcm_token")\
                    .eq("id", report["user_id"])\
                    .execute()
                if user.data and user.data[0].get("fcm_token"):
                    from app.services.notification_service import notify_report_status_change
                    await notify_report_status_change(
                        fcm_token=user.data[0]["fcm_token"],
                        report_id=report_id,
                        status=update.get("status")
                    )
        except Exception as e:
            logger.error(f"Push notification error: {e}")

        return {"message": "Ενημερώθηκε!", "report": result.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{report_id}/auto-assign")
async def auto_assign_report(report_id: str, _user: dict = Depends(require_permission("reports:assign"))):
    def _get_client():
        return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        report_result = supabase.table("reports").select("*").eq("id", report_id).execute()
        if not report_result.data:
            raise HTTPException(status_code=404, detail="Αναφορά δεν βρέθηκε")
        report = report_result.data[0]

        category = report.get("category") or "other"
        dept_slug = CATEGORIES.get(category, "technical_services")

        dept_result = supabase.table("departments").select("id, name").eq("slug", dept_slug).execute()
        if not dept_result.data:
            raise HTTPException(status_code=404, detail=f"Τμήμα '{dept_slug}' δεν βρέθηκε")
        department = dept_result.data[0]

        # Βρες υπάλληλο με τα λιγότερα ενεργά assignments στο τμήμα
        staff_result = supabase.table("users").select("id, full_name") \
            .eq("department_id", department["id"]).neq("role", "citizen").execute()

        assigned_staff_id = None
        assigned_staff_name = None
        current_min = float("inf")

        for member in (staff_result.data or []):
            active_count = supabase.table("reports").select("id", count="exact") \
                .eq("assigned_to", member["id"]) \
                .in_("status", ["submitted", "in_progress"]).execute()
            load = active_count.count or 0
            if load < current_min:
                current_min = load
                assigned_staff_id = member["id"]
                assigned_staff_name = member["full_name"]

        # Claude για αιτιολόγηση
        ai_context = (
            f"Αναφορά: κατηγορία={category}, σοβαρότητα={report.get('severity','medium')}, "
            f"περιγραφή={report.get('description','')}\n"
            f"Ανάθεση στο τμήμα: {department['name']}"
            + (f", υπάλληλος: {assigned_staff_name}" if assigned_staff_name else "")
            + "\nΔώσε 1 σύντομη πρόταση αιτιολόγησης στα ελληνικά."
        )
        client = _get_client()
        ai_resp = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=120,
            messages=[{"role": "user", "content": ai_context}],
        )
        reasoning = ai_resp.content[0].text.strip()

        update_data: dict = {"department_id": department["id"], "status": "assigned"}
        if assigned_staff_id:
            update_data["assigned_to"] = assigned_staff_id

        result = supabase.table("reports").update(update_data).eq("id", report_id).execute()

        comment = f"AI Auto-assign → {department['name']}"
        if assigned_staff_name:
            comment += f" / {assigned_staff_name}"
        comment += f". {reasoning}"
        supabase.table("report_updates").insert({
            "report_id": report_id,
            "status": "assigned",
            "comment": comment,
        }).execute()

        return {
            "message": "Αυτόματη ανάθεση ολοκληρώθηκε!",
            "department": department["name"],
            "assigned_to": assigned_staff_name,
            "reasoning": reasoning,
            "report": result.data[0],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{report_id}")
def delete_report(report_id: str, _user: dict = Depends(require_permission("reports:delete"))):
    try:
        supabase.table("reports")\
            .delete()\
            .eq("id", report_id)\
            .execute()
        return {"message": "Διαγράφηκε!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))