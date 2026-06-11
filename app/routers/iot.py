import math
import logging
from datetime import datetime, timezone
from typing import Optional, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.database import supabase, get_supabase
from app.services.iot_simulator import simulate_readings, get_latest_readings

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════
# ΥΠΑΡΧΟΝΤΑ endpoints (iot_devices / iot_readings)
# ═══════════════════════════════════════════════════════════

@router.get("/devices")
def get_devices():
    result = supabase.table("iot_devices").select("*").execute()
    return result.data


@router.get("/latest")
def get_latest():
    return get_latest_readings()


@router.post("/simulate")
def run_simulation():
    result = simulate_readings()
    return {
        "message":        "Simulation ολοκληρώθηκε!",
        "readings_count": len(result["readings"]),
        "alerts_count":   len(result["alerts"]),
        "alerts":         result["alerts"],
    }


@router.get("/alerts")
def get_alerts():
    result = (
        supabase.table("iot_readings")
        .select("*, iot_devices(name, type, location)")
        .eq("alert", True)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return result.data


@router.get("/stats")
def get_stats():
    devices  = supabase.table("iot_devices").select("*").execute()
    readings = supabase.table("iot_readings").select("*").eq("alert", True).execute()
    device_data = devices.data or []
    return {
        "total_devices":  len(device_data),
        "active_devices": len([d for d in device_data if d["status"] == "active"]),
        "total_alerts":   len(readings.data or []),
        "by_type": {
            "waste_bin":      len([d for d in device_data if d["type"] == "waste_bin"]),
            "street_light":   len([d for d in device_data if d["type"] == "street_light"]),
            "environment":    len([d for d in device_data if d["type"] == "environment"]),
            "water_pressure": len([d for d in device_data if d["type"] == "water_pressure"]),
            "traffic":        len([d for d in device_data if d["type"] == "traffic"]),
        },
    }


# ═══════════════════════════════════════════════════════════
# GATEWAYS (iot_gateways table)
# ═══════════════════════════════════════════════════════════

@router.get("/gateways")
async def list_gateways():
    try:
        client = get_supabase()
        result = client.table("iot_gateways").select("*").execute()
        gateways = result.data or []
        print(f"[GATEWAYS] Found {len(gateways)} gateways")

        for gw in gateways:
            count_resp = (
                client.table("iot_sensors")
                .select("id", count="exact")
                .eq("gateway_id", gw["gateway_id"])
                .execute()
            )
            gw["connected_sensors"] = count_resp.count or 0

        return {"gateways": gateways}
    except Exception as e:
        print(f"[GATEWAYS LIST ERROR] {e}")
        return {"gateways": []}


class GatewayCreate(BaseModel):
    gateway_id:        str
    name:              str
    latitude:          float
    longitude:         float
    address:           Optional[str] = None
    neighborhood:      Optional[str] = None
    coverage_radius_m: Optional[int] = 2000
    protocol:          Optional[str] = "LoRaWAN"
    status:            Optional[str] = "online"
    ip_address:        Optional[str] = None
    notes:             Optional[str] = None


@router.post("/gateways")
async def create_gateway(payload: GatewayCreate):
    try:
        client = get_supabase()
        row = {
            "gateway_id":        payload.gateway_id,
            "name":              payload.name,
            "latitude":          payload.latitude,
            "longitude":         payload.longitude,
            "address":           payload.address,
            "neighborhood":      payload.neighborhood,
            "coverage_radius_m": payload.coverage_radius_m,
            "protocol":          payload.protocol,
            "status":            payload.status,
            "ip_address":        payload.ip_address,
            "notes":             payload.notes,
            "is_virtual":        True,
        }
        result = client.table("iot_gateways").insert(row).execute()
        if not result.data:
            raise HTTPException(status_code=400, detail="Αποτυχία εγκατάστασης gateway")
        print(f"[GATEWAYS] Created gateway_id={payload.gateway_id}")
        return {"gateway": result.data[0], "message": "Το gateway εγκαταστάθηκε επιτυχώς"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[GATEWAY CREATE ERROR] {e}")
        raise HTTPException(status_code=400, detail=f"Σφάλμα: {str(e)}")


class GatewayUpdate(BaseModel):
    name:              Optional[str]  = None
    status:            Optional[str]  = None
    address:           Optional[str]  = None
    neighborhood:      Optional[str]  = None
    coverage_radius_m: Optional[int]  = None
    protocol:          Optional[str]  = None
    ip_address:        Optional[str]  = None
    firmware_version:  Optional[str]  = None
    signal_strength:   Optional[int]  = None
    battery_percent:   Optional[int]  = None
    notes:             Optional[str]  = None


@router.patch("/gateways/{gateway_id}")
async def update_gateway(gateway_id: str, payload: GatewayUpdate):
    try:
        client = get_supabase()
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(status_code=400, detail="Δεν δόθηκε κανένα πεδίο προς ενημέρωση")

        result = client.table("iot_gateways").update(updates).eq("gateway_id", gateway_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Gateway δεν βρέθηκε")
        return {"gateway": result.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/gateways/{gateway_id}")
async def delete_gateway(gateway_id: str):
    try:
        client = get_supabase()
        # Unlink sensors πρώτα
        client.table("iot_sensors").update({"gateway_id": None}).eq("gateway_id", gateway_id).execute()
        client.table("iot_gateways").delete().eq("gateway_id", gateway_id).execute()
        print(f"[GATEWAYS] Deleted gateway_id={gateway_id}")
        return {"message": "Διαγράφηκε"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/gateways/{gateway_id}/sensors")
async def get_gateway_sensors(gateway_id: str):
    try:
        client = get_supabase()
        result = client.table("iot_sensors").select("*").eq("gateway_id", gateway_id).execute()
        return {"sensors": result.data or []}
    except Exception as e:
        print(f"[GATEWAY SENSORS ERROR] {e}")
        return {"sensors": []}


# ═══════════════════════════════════════════════════════════
# SENSORS (iot_sensors table)
# ═══════════════════════════════════════════════════════════

def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi   = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _find_nearest_gateway(lat: float, lng: float, gateways: list) -> Optional[str]:
    if not gateways:
        return None
    nearest = min(gateways, key=lambda g: _haversine_m(lat, lng, g["latitude"], g["longitude"]))
    return nearest["gateway_id"]


class SensorCreate(BaseModel):
    sensor_id:    str
    type:         str
    subtype:      Optional[str]         = None
    latitude:     float
    longitude:    float
    address:      Optional[str]         = None
    neighborhood: Optional[str]         = None
    zone:         Optional[str]         = None
    metadata:     Optional[Any]         = None
    status:       Optional[str]         = "active"
    gateway_id:   Optional[str]         = None


@router.post("/sensors")
async def create_sensor(payload: SensorCreate):
    try:
        client = get_supabase()

        # Auto-assign κοντινότερο online gateway αν δεν δόθηκε
        gateway_id = payload.gateway_id
        if not gateway_id:
            gw_resp = (
                client.table("iot_gateways")
                .select("gateway_id, latitude, longitude")
                .eq("status", "online")
                .execute()
            )
            if gw_resp.data:
                gateway_id = _find_nearest_gateway(payload.latitude, payload.longitude, gw_resp.data)
                print(f"[SENSORS] Auto-assigned gateway={gateway_id} to sensor={payload.sensor_id}")

        row = {
            "sensor_id":    payload.sensor_id,
            "type":         payload.type,
            "subtype":      payload.subtype,
            "latitude":     payload.latitude,
            "longitude":    payload.longitude,
            "address":      payload.address,
            "neighborhood": payload.neighborhood,
            "zone":         payload.zone,
            "metadata":     payload.metadata or {},
            "status":       payload.status,
            "gateway_id":   gateway_id,
            "is_virtual":   True,
        }

        result = client.table("iot_sensors").insert(row).execute()
        if not result.data:
            raise HTTPException(status_code=400, detail="Αποτυχία εγκατάστασης sensor")

        print(f"[SENSORS] Created sensor_id={payload.sensor_id} gateway={gateway_id}")
        return {
            "sensor":           result.data[0],
            "gateway_assigned": gateway_id,
            "message":          "Η συσκευή εγκαταστάθηκε επιτυχώς",
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SENSOR CREATE ERROR] {e}")
        raise HTTPException(status_code=400, detail=f"Σφάλμα: {str(e)}")


# Aliases so callers using either name get the same rows
_SENSOR_TYPE_ALIASES: dict[str, str] = {
    "smart_waste_bin": "waste_bin",
    "smart_parking":   "parking",
    "smart_flood":     "flood",
}


@router.get("/sensors")
async def list_sensors(type: Optional[str] = Query(None, description="Filter by sensor type")):
    try:
        client = get_supabase()
        query = client.table("iot_sensors").select("*")
        if type:
            canonical = _SENSOR_TYPE_ALIASES.get(type, type)
            query = query.eq("type", canonical)
        result = query.execute()
        return {"sensors": result.data or [], "total": len(result.data or [])}
    except Exception as e:
        print(f"[SENSORS LIST ERROR] {e}")
        return {"sensors": [], "total": 0}
