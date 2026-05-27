import logging
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import supabase

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_STATUSES = {"pending", "confirmed", "cancelled", "completed"}


class AppointmentCreate(BaseModel):
    citizen_id: str
    department_id: str
    scheduled_at: datetime
    reason: Optional[str] = None
    notes: Optional[str] = None


@router.post("/")
def create_appointment(payload: AppointmentCreate):
    try:
        # Verify department exists
        dept = supabase.table("departments").select("id, name").eq("id", payload.department_id).execute()
        if not dept.data:
            raise HTTPException(status_code=404, detail="Τμήμα δεν βρέθηκε")

        appointment = {
            "id": str(uuid.uuid4()),
            "citizen_id": payload.citizen_id,
            "department_id": payload.department_id,
            "scheduled_at": payload.scheduled_at.isoformat(),
            "reason": payload.reason,
            "notes": payload.notes,
            "status": "pending",
        }
        result = supabase.table("appointments").insert(appointment).execute()
        return {"message": "Ραντεβού κρατήθηκε!", "appointment": result.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
def get_appointments(
    department_id: Optional[str] = Query(None),
    citizen_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    try:
        if status and status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Μη έγκυρο status. Επιτρεπτά: {sorted(VALID_STATUSES)}")

        query = supabase.table("appointments").select("*, departments(name)", count="exact")
        if department_id:
            query = query.eq("department_id", department_id)
        if citizen_id:
            query = query.eq("citizen_id", citizen_id)
        if status:
            query = query.eq("status", status)

        offset = (page - 1) * per_page
        result = query.order("scheduled_at").range(offset, offset + per_page - 1).execute()

        return {
            "data": result.data,
            "total": result.count or 0,
            "page": page,
            "per_page": per_page,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{appointment_id}")
def update_appointment_status(appointment_id: str, status: str):
    try:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Μη έγκυρο status. Επιτρεπτά: {sorted(VALID_STATUSES)}")

        result = supabase.table("appointments").update({"status": status}).eq("id", appointment_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Ραντεβού δεν βρέθηκε")
        return {"message": "Ενημερώθηκε!", "appointment": result.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
