import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.database import supabase
from app.dependencies import get_current_user

router = APIRouter(prefix="/crews", tags=["Crews"])


@router.get("/")
def list_crews(
    department_id: Optional[str] = Query(None),
    active_only: bool = Query(False),
):
    """Λίστα συνεργείων με workload metrics."""
    query = supabase.table("crews").select("*, departments(id, name, slug)")

    if department_id:
        query = query.eq("department_id", department_id)
    if active_only:
        query = query.eq("is_active", True)

    crews = (query.order("name").execute().data) or []

    for crew in crews:
        try:
            active = supabase.table("reports").select("id", count="exact").eq(
                "crew_id", crew["id"]
            ).in_("status", ["assigned", "in_progress"]).execute()
            completed = supabase.table("reports").select("id", count="exact").eq(
                "crew_id", crew["id"]
            ).eq("status", "completed").execute()
            crew["active_reports_count"] = active.count or 0
            crew["completed_reports_count"] = completed.count or 0
        except Exception as e:
            print(f"[CREWS] count error crew_id={crew['id']}: {e}")
            crew["active_reports_count"] = 0
            crew["completed_reports_count"] = 0

    return crews


@router.get("/{crew_id}")
def get_crew(crew_id: str):
    """Λεπτομέρειες συνεργείου με stats."""
    result = supabase.table("crews").select(
        "*, departments(id, name, slug)"
    ).eq("id", crew_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Δεν βρέθηκε συνεργείο")

    crew = result.data[0]

    try:
        active = supabase.table("reports").select("id", count="exact").eq(
            "crew_id", crew_id
        ).in_("status", ["assigned", "in_progress"]).execute()
        completed = supabase.table("reports").select("id", count="exact").eq(
            "crew_id", crew_id
        ).eq("status", "completed").execute()
        crew["stats"] = {
            "active_reports": active.count or 0,
            "completed_reports": completed.count or 0,
            "total_reports": (active.count or 0) + (completed.count or 0),
        }
    except Exception as e:
        print(f"[CREWS] stats error crew_id={crew_id}: {e}")
        crew["stats"] = {"active_reports": 0, "completed_reports": 0, "total_reports": 0}

    return crew


@router.post("/")
async def create_crew(
    payload: dict = Body(...),
    _user: dict = Depends(get_current_user),
):
    """Δημιουργία νέου συνεργείου (admin/manager)."""
    if _user.get("role") not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Δεν έχετε δικαίωμα")

    name = (payload.get("name") or "").strip()
    department_id = payload.get("department_id")

    if not name:
        raise HTTPException(status_code=400, detail="Παρακαλώ εισάγετε όνομα συνεργείου")
    if not department_id:
        raise HTTPException(status_code=400, detail="Παρακαλώ επιλέξτε τμήμα")

    dept = supabase.table("departments").select("id").eq("id", department_id).execute()
    if not dept.data:
        raise HTTPException(status_code=404, detail="Δεν βρέθηκε τμήμα")

    row = {
        "id":            str(uuid.uuid4()),
        "name":          name,
        "department_id": department_id,
        "specialty":     payload.get("specialty"),
        "leader_name":   payload.get("leader_name"),
        "leader_phone":  payload.get("leader_phone"),
        "members_count": int(payload.get("members_count", 1)),
        "is_active":     payload.get("is_active", True),
    }

    result = supabase.table("crews").insert(row).execute()
    return result.data[0] if result.data else None


@router.patch("/{crew_id}")
async def update_crew(
    crew_id: str,
    payload: dict = Body(...),
    _user: dict = Depends(get_current_user),
):
    """Ενημέρωση συνεργείου."""
    if _user.get("role") not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Δεν έχετε δικαίωμα")

    allowed = {
        "name", "specialty", "leader_name", "leader_phone",
        "members_count", "is_active", "department_id",
    }
    update_data = {k: v for k, v in payload.items() if k in allowed}

    if not update_data:
        raise HTTPException(status_code=400, detail="Καμία αλλαγή για ενημέρωση")

    result = supabase.table("crews").update(update_data).eq("id", crew_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Δεν βρέθηκε συνεργείο")

    return result.data[0]


@router.delete("/{crew_id}")
async def delete_crew(
    crew_id: str,
    _user: dict = Depends(get_current_user),
):
    """Διαγραφή συνεργείου (μπλοκάρει αν υπάρχουν ενεργές αναφορές)."""
    if _user.get("role") not in ["admin", "manager"]:
        raise HTTPException(status_code=403, detail="Δεν έχετε δικαίωμα")

    active = supabase.table("reports").select("id", count="exact").eq(
        "crew_id", crew_id
    ).in_("status", ["assigned", "in_progress"]).execute()

    if (active.count or 0) > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Το συνεργείο έχει {active.count} ενεργές αναφορές. "
                   "Παρακαλώ μεταφέρετέ τες πρώτα.",
        )

    supabase.table("crews").delete().eq("id", crew_id).execute()
    return {"success": True}


@router.get("/{crew_id}/reports")
def get_crew_reports(
    crew_id: str,
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """Αναφορές συγκεκριμένου συνεργείου."""
    query = supabase.table("reports").select("*, departments(name)").eq("crew_id", crew_id)

    if status:
        query = query.eq("status", status)

    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data or []
