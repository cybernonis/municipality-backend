from fastapi import APIRouter, HTTPException
from app.models.schemas import UserRegister, UserLogin
from app.database import supabase

router = APIRouter()

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