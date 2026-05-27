import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import supabase

logger = logging.getLogger(__name__)
router = APIRouter()

XP_MAP = {
    "report_submitted": 10,
    "report_resolved":  50,
    "first_report":     100,
    "rating_given":     5,
}

BADGE_THRESHOLDS = [
    (1,  "Πρώτη Αναφορά"),
    (10, "10 Αναφορές"),
    (50, "Super Citizen"),
]


def _level_for(points: int) -> int:
    return max(1, points // 100 + 1)


def _compute_badges(user_id: str, current_badges: list) -> list:
    result = supabase.table("reports").select("id", count="exact").eq("citizen_id", user_id).execute()
    total_reports = result.count or 0

    new_badges = []
    if total_reports >= 1  and "Πρώτη Αναφορά" not in current_badges:
        new_badges.append("Πρώτη Αναφορά")
    if total_reports >= 10 and "10 Αναφορές"   not in current_badges:
        new_badges.append("10 Αναφορές")
    if total_reports >= 50 and "Super Citizen"  not in current_badges:
        new_badges.append("Super Citizen")

    print(f"[badges] user_id={user_id} total_reports={total_reports} "
          f"current={current_badges} new={new_badges}")

    if new_badges:
        all_badges = current_badges + new_badges
        supabase.table("user_points").update({"badges": all_badges}).eq("user_id", user_id).execute()

    return new_badges


class AwardRequest(BaseModel):
    user_id: str
    action: str


@router.post("/award")
def award_points(payload: AwardRequest):
    if payload.action not in XP_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Άγνωστη action. Επιτρεπτές: {list(XP_MAP)}",
        )
    try:
        existing = supabase.table("user_points").select("*").eq("user_id", payload.user_id).execute()

        if existing.data:
            record = existing.data[0]
        else:
            init = supabase.table("user_points").insert({
                "user_id": payload.user_id,
                "points": 0,
                "badges": [],
                "level": 1,
                "carbon_saved": 0.0,
            }).execute()
            record = init.data[0]

        current_points  = record["points"]
        current_badges  = record.get("badges") or []
        current_level   = record["level"]

        xp = XP_MAP[payload.action]
        # first_report is one-time only
        if payload.action == "first_report" and "Πρώτη Αναφορά" in current_badges:
            xp = 0

        new_points = current_points + xp
        new_level  = _level_for(new_points)

        supabase.table("user_points").update({
            "points":     new_points,
            "level":      new_level,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("user_id", payload.user_id).execute()

        # badges αποθηκεύονται εντός _compute_badges αν υπάρχουν νέα
        new_badges = _compute_badges(payload.user_id, current_badges)
        all_badges = current_badges + new_badges

        return {
            "user_id":      payload.user_id,
            "action":       payload.action,
            "xp_awarded":   xp,
            "total_points": new_points,
            "level":        new_level,
            "leveled_up":   new_level > current_level,
            "new_badges":   new_badges,
            "all_badges":   all_badges,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaderboard")
def get_leaderboard():
    try:
        result = (
            supabase.table("user_points")
            .select("user_id, points, badges, level, users(full_name)")
            .order("points", desc=True)
            .limit(10)
            .execute()
        )
        leaderboard = [
            {
                "rank":         rank,
                "user_id":      row["user_id"],
                "display_name": (row.get("users") or {}).get("full_name", "Ανώνυμος"),
                "points":       row["points"],
                "badges":       row.get("badges") or [],
                "level":        row["level"],
            }
            for rank, row in enumerate(result.data or [], start=1)
        ]
        return {"leaderboard": leaderboard, "total": len(leaderboard)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
