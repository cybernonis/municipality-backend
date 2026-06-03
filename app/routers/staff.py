from fastapi import APIRouter, Depends, HTTPException
from app.database import supabase
from app.dependencies import require_permission
from pydantic import BaseModel
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

STAFF_ROLES = ["admin", "manager", "worker", "inspector"]

class StaffCreate(BaseModel):
    email: str
    password: str
    full_name: str
    phone: Optional[str] = None
    role: str = "worker"
    department_id: Optional[str] = None

class StaffUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    department_id: Optional[str] = None

@router.get("/")
def get_all_staff():
    try:
        result = supabase.table("users")\
            .select("*, departments(name)")\
            .neq("role", "citizen")\
            .order("created_at", desc=True)\
            .execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/by-department/{department_id}")
def get_staff_by_department(department_id: str):
    try:
        result = supabase.table("users")\
            .select("*")\
            .eq("department_id", department_id)\
            .neq("role", "citizen")\
            .execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
def create_staff(staff: StaffCreate):
    try:
        if staff.role not in STAFF_ROLES:
            raise HTTPException(status_code=400, detail=f"Μη έγκυρος ρόλος. Επιτρεπτοί: {STAFF_ROLES}")

        # Δημιουργία στο Supabase Auth
        result = supabase.auth.admin.create_user({
            "email": staff.email,
            "password": staff.password,
            "email_confirm": True,
        })

        if not result.user:
            raise HTTPException(status_code=400, detail="Αποτυχία δημιουργίας χρήστη")

        # Εισαγωγή στον πίνακα users
        supabase.table("users").insert({
            "id": result.user.id,
            "full_name": staff.full_name,
            "phone": staff.phone,
            "role": staff.role,
            "department_id": staff.department_id,
        }).execute()

        return {
            "message": "Ο υπάλληλος δημιουργήθηκε επιτυχώς!",
            "user_id": result.user.id,
            "email": staff.email,
            "role": staff.role,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.patch("/{staff_id}")
def update_staff(staff_id: str, update: StaffUpdate):
    try:
        update_data = {k: v for k, v in update.dict().items() if v is not None}

        if not update_data:
            raise HTTPException(status_code=400, detail="Δεν υπάρχουν δεδομένα για ενημέρωση")

        if "role" in update_data and update_data["role"] not in STAFF_ROLES:
            raise HTTPException(status_code=400, detail=f"Μη έγκυρος ρόλος. Επιτρεπτοί: {STAFF_ROLES}")

        result = supabase.table("users")\
            .update(update_data)\
            .eq("id", staff_id)\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Ο υπάλληλος δεν βρέθηκε")

        return {"message": "Ο υπάλληλος ενημερώθηκε!", "staff": result.data[0]}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{staff_id}")
def delete_staff(staff_id: str, _user: dict = Depends(require_permission("users:delete"))):
    try:
        # Διαγραφή από Auth
        supabase.auth.admin.delete_user(staff_id)

        # Διαγραφή από users table
        supabase.table("users")\
            .delete()\
            .eq("id", staff_id)\
            .execute()

        return {"message": "Ο υπάλληλος διαγράφηκε!"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{staff_id}")
def get_staff(staff_id: str):
    try:
        result = supabase.table("users")\
            .select("*, departments(name)")\
            .eq("id", staff_id)\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Ο υπάλληλος δεν βρέθηκε")

        return result.data[0]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))