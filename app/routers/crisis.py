from fastapi import APIRouter, HTTPException
from app.database import supabase
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import uuid
import logging

print("CRISIS ROUTER LOADED v2", flush=True)

logger = logging.getLogger(__name__)

router = APIRouter()

CRISIS_TYPES = {
    'fire':          {'label': 'Φωτιά',                    'icon': '🔥', 'severity': 'critical'},
    'flood':         {'label': 'Πλημμύρα',                 'icon': '🌊', 'severity': 'critical'},
    'power_outage':  {'label': 'Διακοπή Ρεύματος',        'icon': '⚡', 'severity': 'high'},
    'collapse':      {'label': 'Κατάρρευση Κτιρίου',      'icon': '🏗',  'severity': 'critical'},
    'accident':      {'label': 'Τροχαίο Ατύχημα',         'icon': '🚗', 'severity': 'high'},
    'natural':       {'label': 'Φυσική Καταστροφή',       'icon': '🌪',  'severity': 'critical'},
    'medical':       {'label': 'Ιατρική Έκτακτη Ανάγκη',  'icon': '🏥', 'severity': 'critical'},
    'other':         {'label': 'Άλλο Επείγον',             'icon': '⚠',  'severity': 'high'},
}

class CrisisCreate(BaseModel):
    user_id: Optional[str] = None
    type: str
    description: Optional[str] = None
    latitude: float
    longitude: float
    address: Optional[str] = None

class CrisisUpdate(BaseModel):
    status: Optional[str] = None
    message: Optional[str] = None
    updated_by: Optional[str] = None

@router.get("/types")
def get_crisis_types():
    return [
        {"key": k, "label": v["label"], "icon": v["icon"], "severity": v["severity"]}
        for k, v in CRISIS_TYPES.items()
    ]

@router.get("/contacts")
def get_emergency_contacts():
    result = supabase.table("emergency_contacts")\
        .select("*")\
        .eq("active", True)\
        .execute()
    return result.data

@router.post("/report")
async def report_crisis(crisis: CrisisCreate):
    from app.services.email_service import send_crisis_email
   

    

    crisis_type = CRISIS_TYPES.get(crisis.type, CRISIS_TYPES['other'])

    data = {
        "id": str(uuid.uuid4()),
        "user_id": crisis.user_id,
        "type": crisis.type,
        "description": crisis.description,
        "latitude": crisis.latitude,
        "longitude": crisis.longitude,
        "address": crisis.address,
        "severity": crisis_type["severity"],
        "status": "active",
    }

    result = supabase.table("crisis_events").insert(data).execute()

    # Email alert στον admin
    import os
    logger.info(f"DEBUG: BREVO_API_KEY={bool(os.getenv('BREVO_API_KEY'))} ADMIN={os.getenv('ADMIN_EMAIL')}")
    try:
        await send_crisis_email(
            crisis_type=crisis_type["label"],
            location=crisis.address or f"{crisis.latitude:.4f}, {crisis.longitude:.4f}",
            description=crisis.description or "Χωρίς περιγραφή"
        )
    except Exception as e:
        logger.error(f"Crisis email error: {e}")

    return {
        "message": "Η αναφορά έκτακτης ανάγκης καταχωρήθηκε!",
        "crisis_id": data["id"],
        "emergency_contacts": [
            {"name": "ΕΚΑΒ", "phone": "166"},
            {"name": "Πυροσβεστική", "phone": "199"},
            {"name": "Αστυνομία", "phone": "100"},
            {"name": "Άμεση Βοήθεια", "phone": "112"},
        ]
    }

@router.get("/active")
def get_active_crises():
    result = supabase.table("crisis_events")\
        .select("*")\
        .eq("status", "active")\
        .order("created_at", desc=True)\
        .execute()
    return result.data

@router.get("/all")
def get_all_crises():
    result = supabase.table("crisis_events")\
        .select("*")\
        .order("created_at", desc=True)\
        .execute()
    return result.data

@router.patch("/{crisis_id}")
def update_crisis(crisis_id: str, update: CrisisUpdate):
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if update.status:
        update_data["status"] = update.status
        if update.status == "resolved":
            update_data["resolved_at"] = datetime.now(timezone.utc).isoformat()

    supabase.table("crisis_events")\
        .update(update_data)\
        .eq("id", crisis_id)\
        .execute()

    if update.message:
        supabase.table("crisis_updates").insert({
            "id": str(uuid.uuid4()),
            "crisis_id": crisis_id,
            "message": update.message,
            "updated_by": update.updated_by,
        }).execute()

    return {"message": "Ενημερώθηκε!"}

@router.get("/{crisis_id}")
def get_crisis(crisis_id: str):
    crisis = supabase.table("crisis_events")\
        .select("*")\
        .eq("id", crisis_id)\
        .execute()

    updates = supabase.table("crisis_updates")\
        .select("*")\
        .eq("crisis_id", crisis_id)\
        .order("created_at", desc=True)\
        .execute()

    if not crisis.data:
        raise HTTPException(status_code=404, detail="Δεν βρέθηκε")

    return {
        "crisis": crisis.data[0],
        "updates": updates.data
    }