import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()

_DEFAULT_COORDS = {"type": "Point", "coordinates": [25.1442, 35.3387]}


def _normalize(row: dict) -> dict:
    return {
        "id":          row.get("id"),
        "road_name":   row.get("road_name", ""),
        "reason":      row.get("reason"),
        "start_date":  str(row.get("start_date", "")),
        "end_date":    str(row.get("end_date")) if row.get("end_date") else None,
        "status":      row.get("status", "active"),
        "coordinates": row.get("coordinates") or _DEFAULT_COORDS,
        "created_at":  str(row.get("created_at", "")),
    }


async def _push_closed_road(road_name: str, road_id: str):
    try:
        client = get_supabase()
        users_result = client.table("users").select("fcm_token").execute()
        tokens = [u["fcm_token"] for u in (users_result.data or []) if u.get("fcm_token")]
        if tokens:
            from app.services.notification_service import send_push_to_multiple
            asyncio.create_task(send_push_to_multiple(
                tokens=tokens,
                title=f"🚧 Κλειστός δρόμος: {road_name}",
                body="Δείτε τις λεπτομέρειες στην εφαρμογή.",
                data={"type": "closed_road", "road_id": road_id},
            ))
        print(f"[CLOSED ROADS] Push sent to {len(tokens)} devices for road_id={road_id}")
    except Exception as e:
        logger.error(f"[CLOSED ROADS] Push notification error: {e}")


class ClosedRoadCreate(BaseModel):
    road_name:   str
    reason:      Optional[str] = None
    start_date:  str
    end_date:    Optional[str] = None
    coordinates: Optional[Any] = None


class ClosedRoadUpdate(BaseModel):
    road_name:   Optional[str] = None
    reason:      Optional[str] = None
    start_date:  Optional[str] = None
    end_date:    Optional[str] = None
    status:      Optional[str] = None
    coordinates: Optional[Any] = None


@router.get("/")
def get_active_closed_roads():
    """Επιστρέφει ΜΟΝΟ active κλειστούς δρόμους (για mobile app)."""
    try:
        client = get_supabase()
        now = datetime.now(timezone.utc).isoformat()

        result = (
            client.table("closed_roads")
            .select("*")
            .eq("status", "active")
            .or_(f"end_date.is.null,end_date.gt.{now}")
            .order("start_date", desc=True)
            .execute()
        )

        data = [_normalize(row) for row in (result.data or [])]
        print(f"[CLOSED ROADS] Active roads: {len(data)}")
        return {"data": data}

    except Exception as e:
        logger.error(f"[CLOSED ROADS] get_active error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: /all πρέπει να είναι ΠΡΙΝ το /{id} για να μην υπάρξει routing conflict
@router.get("/all")
def get_all_closed_roads():
    """Επιστρέφει ΟΛΟΥΣ τους κλειστούς δρόμους (για admin dashboard)."""
    try:
        client = get_supabase()

        result = (
            client.table("closed_roads")
            .select("*", count="exact")
            .order("start_date", desc=True)
            .execute()
        )

        data = [_normalize(row) for row in (result.data or [])]
        total = result.count or len(data)
        print(f"[CLOSED ROADS] All roads: {total}")
        return {"data": data, "total": total}

    except Exception as e:
        logger.error(f"[CLOSED ROADS] get_all error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_closed_road(payload: ClosedRoadCreate):
    try:
        client = get_supabase()

        row = {
            "road_name":   payload.road_name,
            "reason":      payload.reason,
            "start_date":  payload.start_date,
            "status":      "active",
            "coordinates": payload.coordinates or _DEFAULT_COORDS,
        }
        if payload.end_date:
            row["end_date"] = payload.end_date

        result = client.table("closed_roads").insert(row).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Αποτυχία αποθήκευσης στη βάση δεδομένων")

        created = result.data[0]
        print(f"[CLOSED ROADS] Created id={created['id']} road={payload.road_name}")

        await _push_closed_road(payload.road_name, created["id"])

        return {"message": "Επιτυχής δημιουργία", "data": _normalize(created)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CLOSED ROADS] create error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{road_id}")
def update_closed_road(road_id: str, payload: ClosedRoadUpdate):
    try:
        client = get_supabase()

        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        if not updates:
            raise HTTPException(status_code=400, detail="Δεν δόθηκε κανένα πεδίο προς ενημέρωση")

        updates["updated_at"] = datetime.now(timezone.utc).isoformat()

        result = (
            client.table("closed_roads")
            .update(updates)
            .eq("id", road_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Ο κλειστός δρόμος δεν βρέθηκε")

        print(f"[CLOSED ROADS] Updated id={road_id} fields={list(updates.keys())}")
        return {"message": "Επιτυχής ενημέρωση", "data": _normalize(result.data[0])}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CLOSED ROADS] update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{road_id}")
def delete_closed_road(road_id: str):
    """Soft delete — θέτει status='inactive'."""
    try:
        client = get_supabase()

        result = (
            client.table("closed_roads")
            .update({
                "status":     "inactive",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("id", road_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Ο κλειστός δρόμος δεν βρέθηκε")

        print(f"[CLOSED ROADS] Soft-deleted id={road_id}")
        return {"message": "Ο δρόμος αφαιρέθηκε"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CLOSED ROADS] delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
