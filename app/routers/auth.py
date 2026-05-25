from fastapi import APIRouter, HTTPException
from app.models.schemas import UserRegister, UserLogin
from app.database import supabase
from pydantic import BaseModel

router = APIRouter()

class FCMTokenUpdate(BaseModel):
    user_id: str
    fcm_token: str

@router.post("/register")
def register(user: UserRegister):
    try:
        result = supabase.auth.sign_up({
            "email": user.email,
            "password": user.password,
        })

        if result.user:
            supabase.table("users").insert({
                "id": result.user.id,
                "full_name": user.full_name,
                "phone": user.phone,
                "role": "citizen"
            }).execute()

        return {"message": "Εγγραφή επιτυχής!", "user_id": result.user.id}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login")
def login(user: UserLogin):
    try:
        result = supabase.auth.sign_in_with_password({
            "email": user.email,
            "password": user.password,
        })
        return {
            "access_token": result.session.access_token,
            "user_id": result.user.id,
            "email": result.user.email
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail="Λάθος email ή password")

@router.post("/fcm-token")
def update_fcm_token(data: FCMTokenUpdate):
    try:
        supabase.table("users")\
            .update({"fcm_token": data.fcm_token})\
            .eq("id", data.user_id)\
            .execute()
        return {"message": "FCM token ενημερώθηκε!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))