from fastapi import APIRouter, HTTPException
from app.services.predictive_service import predict_maintenance, get_historical_data
from app.database import supabase

router = APIRouter()

@router.get("/analyze")
def analyze():
    try:
        result = predict_maintenance()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
def get_history():
    result = supabase.table("ai_predictions")\
        .select("*")\
        .eq("type", "predictive_maintenance")\
        .order("created_at", desc=True)\
        .limit(10)\
        .execute()
    return result.data

@router.get("/quick-stats")
def quick_stats():
    return get_historical_data()