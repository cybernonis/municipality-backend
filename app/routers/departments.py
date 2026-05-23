from fastapi import APIRouter
from app.database import supabase

router = APIRouter()

@router.get("/")
def get_departments():
    result = supabase.table("departments").select("*").execute()
    return result.data