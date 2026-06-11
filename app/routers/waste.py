import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/waste", tags=["Waste"])


class WasteBin(BaseModel):
    sensor_id: str
    location: str
    latitude: float
    longitude: float
    fill_level: int


class RouteAssignPayload(BaseModel):
    crew_id: str
    bins: List[WasteBin]


@router.post("/routes/assign")
def assign_waste_route(payload: RouteAssignPayload):
    if not payload.bins:
        raise HTTPException(status_code=400, detail="Δεν δόθηκαν κάδοι")

    crew = (
        supabase.table("crews")
        .select("id, department_id")
        .eq("id", payload.crew_id)
        .execute()
    )
    if not crew.data:
        raise HTTPException(status_code=404, detail="Συνεργείο δεν βρέθηκε")

    department_id: Optional[str] = crew.data[0].get("department_id")

    # Fallback: resolve sanitation dept if crew has no department set
    if not department_id:
        dept = (
            supabase.table("departments")
            .select("id")
            .eq("slug", "sanitation")
            .execute()
        )
        department_id = dept.data[0]["id"] if dept.data else None

    now = datetime.now(timezone.utc)

    rows = []
    for i, bin_ in enumerate(payload.bins):
        if bin_.fill_level > 80:
            severity = "high"
        elif bin_.fill_level >= 50:
            severity = "medium"
        else:
            severity = "low"

        # Increment by 1 second per bin so DB insertion order matches route order
        created_at = (now + timedelta(seconds=i)).isoformat()

        rows.append({
            "id":            str(uuid.uuid4()),
            "image_url":     "",
            "description":   f"Άδειασμα κάδου {bin_.sensor_id} — {bin_.location} ({bin_.fill_level}%)",
            "address":       bin_.location,
            "latitude":      bin_.latitude,
            "longitude":     bin_.longitude,
            "category":      "waste",
            "severity":      severity,
            "ai_confidence": 1.0,
            "status":        "assigned",
            "crew_id":       payload.crew_id,
            "department_id": department_id,
            "auto_assigned": True,
            "created_at":    created_at,
        })

    result = supabase.table("reports").insert(rows).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Αποτυχία αποθήκευσης στη βάση δεδομένων")

    logger.info("[WASTE] Assigned %d stops to crew %s", len(rows), payload.crew_id)
    return {"assigned": len(result.data), "crew_id": payload.crew_id}
