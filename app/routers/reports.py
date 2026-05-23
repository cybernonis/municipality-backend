from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional
from app.database import supabase
from app.services.ai_service import classify_image
from app.services.storage_service import upload_image
import uuid

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
async def create_report(
    latitude: float = Form(...),
    longitude: float = Form(...),
    description: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
    image: UploadFile = File(...)
):
    try:
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
        return {"message": "Αναφορά υποβλήθηκε!", "report": result.data[0]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{report_id}")
def update_report(report_id: str, update: dict):
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

        return {"message": "Ενημερώθηκε!", "report": result.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))