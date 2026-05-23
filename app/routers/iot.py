from fastapi import APIRouter
from app.services.iot_simulator import simulate_readings, get_latest_readings
from app.database import supabase

router = APIRouter()

@router.get("/devices")
def get_devices():
    result = supabase.table("iot_devices")\
        .select("*")\
        .execute()
    return result.data

@router.get("/latest")
def get_latest():
    return get_latest_readings()

@router.post("/simulate")
def run_simulation():
    result = simulate_readings()
    return {
        "message": f"Simulation ολοκληρώθηκε!",
        "readings_count": len(result["readings"]),
        "alerts_count": len(result["alerts"]),
        "alerts": result["alerts"]
    }

@router.get("/alerts")
def get_alerts():
    result = supabase.table("iot_readings")\
        .select("*, iot_devices(name, type, location)")\
        .eq("alert", True)\
        .order("created_at", desc=True)\
        .limit(20)\
        .execute()
    return result.data

@router.get("/stats")
def get_stats():
    devices = supabase.table("iot_devices").select("*").execute()
    readings = supabase.table("iot_readings")\
        .select("*")\
        .eq("alert", True)\
        .execute()
    
    device_data = devices.data or []
    
    return {
        "total_devices": len(device_data),
        "active_devices": len([d for d in device_data if d["status"] == "active"]),
        "total_alerts": len(readings.data or []),
        "by_type": {
            "waste_bin":     len([d for d in device_data if d["type"] == "waste_bin"]),
            "street_light":  len([d for d in device_data if d["type"] == "street_light"]),
            "environment":   len([d for d in device_data if d["type"] == "environment"]),
            "water_pressure":len([d for d in device_data if d["type"] == "water_pressure"]),
            "traffic":       len([d for d in device_data if d["type"] == "traffic"]),
        }
    }