from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional
from app.database import supabase
from app.services.ai_service import classify_image
import uuid

router = APIRouter()

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
        # 1. Διάβασε την εικόνα
        image_bytes = await image.read()
        print(f"📸 Got image: {len(image_bytes)} bytes")

        # 2. Ανέβασε στο Supabase Storage
        file_ext = image.filename.split(".")[-1] if image.filename else "jpg"
        file_name = f"{uuid.uuid4()}.{file_ext}"
        supabase.storage.from_("report-images").upload(
            path=file_name,
            file=image_bytes,
            file_options={"content-type": image.content_type or "image/jpeg"}
        )
        image_url = supabase.storage.from_("report-images").get_public_url(file_name)
        print(f"✅ Image URL: {image_url}")

        # 3. AI Classification
        ai_result = await classify_image(image_bytes, description)
        print(f"🤖 AI Result: {ai_result}")

        # 4. Βρες department
        dept = supabase.table("departments")\
            .select("id")\
            .eq("slug", ai_result["department"])\
            .execute()
        department_id = dept.data[0]["id"] if dept.data else None

        # 5. Αποθήκευσε report
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
        import traceback
        print("❌ ERROR:", str(e))
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/")
def get_all_reports():
    result = supabase.table("reports")\
        .select("*, departments(name)")\
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