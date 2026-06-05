from fastapi import APIRouter, HTTPException
from app.database import supabase

router = APIRouter()


@router.get("/")
def get_departments():
    result = supabase.table("departments").select("*").execute()
    return result.data


@router.get("/{department_id}/detail")
def get_department_detail(department_id: str):
    """Πλήρες detail τμήματος: στοιχεία + συνεργεία με workload + stats."""
    dept = supabase.table("departments").select("*").eq("id", department_id).execute()
    if not dept.data:
        raise HTTPException(status_code=404, detail="Δεν βρέθηκε τμήμα")

    dept_data = dept.data[0]

    crews = (
        supabase.table("crews").select("*")
        .eq("department_id", department_id)
        .order("name")
        .execute()
        .data or []
    )
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
            print(f"[DEPT_DETAIL] count error: {e}")
            crew["active_reports_count"] = 0
            crew["completed_reports_count"] = 0

    dept_data["crews"] = crews

    try:
        all_reports = supabase.table("reports").select("id, status").eq(
            "department_id", department_id
        ).execute()
        reports = all_reports.data or []
        dept_data["stats"] = {
            "total_reports":       len(reports),
            "pending_reports":     sum(1 for r in reports if r.get("status") in ("submitted", "assigned")),
            "in_progress_reports": sum(1 for r in reports if r.get("status") == "in_progress"),
            "completed_reports":   sum(1 for r in reports if r.get("status") == "completed"),
            "total_crews":         len(crews),
            "total_members":       sum(c.get("members_count", 0) for c in crews),
        }
    except Exception as e:
        print(f"[DEPT_DETAIL] stats error: {e}")
        dept_data["stats"] = {
            "total_reports": 0, "pending_reports": 0,
            "in_progress_reports": 0, "completed_reports": 0,
            "total_crews": len(crews),
            "total_members": sum(c.get("members_count", 0) for c in crews),
        }

    return dept_data