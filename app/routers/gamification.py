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
    "volunteering":     25,
    "donation":         25,
}

BADGE_THRESHOLDS = [
    (1,  "Πρώτη Αναφορά"),
    (10, "10 Αναφορές"),
    (50, "Super Citizen"),
]


def _level_for(points: int) -> int:
    if points < 100:
        return 1
    if points < 250:
        return 2
    if points < 500:
        return 3
    if points < 1000:
        return 4
    if points < 2000:
        return 5
    return 6 + (points - 2000) // 1000


def _compute_badges(user_id: str, current_badges: list) -> list:
    print(f"[badges] Computing for user_id={user_id}, current_badges={current_badges}")
    result = supabase.table("reports").select("id", count="exact").eq("user_id", user_id).execute()
    total_reports = result.count or 0
    print(f"[badges] user_id={user_id} total_reports={total_reports}")

    new_badges = []
    if total_reports >= 1  and "Πρώτη Αναφορά" not in current_badges:
        new_badges.append("Πρώτη Αναφορά")
    if total_reports >= 10 and "10 Αναφορές"   not in current_badges:
        new_badges.append("10 Αναφορές")
    if total_reports >= 50 and "Super Citizen"  not in current_badges:
        new_badges.append("Super Citizen")

    print(f"[badges] new_badges={new_badges}")

    if new_badges:
        all_badges = current_badges + new_badges
        supabase.table("user_points").update({"badges": all_badges}).eq("user_id", user_id).execute()
        print(f"[badges] DB updated with all_badges={all_badges}")

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
    user_id = payload.user_id
    action = payload.action
    print(f"[AWARD XP] user_id={user_id}, action={action}")
    try:
        existing = supabase.table("user_points").select("*").eq("user_id", user_id).execute()
        print(f"[award] existing record found: {bool(existing.data)}")

        if existing.data:
            record = existing.data[0]
        else:
            print(f"[award] No record — inserting new user_points row for user_id={user_id}")
            init = supabase.table("user_points").insert({
                "user_id":      user_id,
                "points":       0,
                "badges":       [],
                "level":        1,
                "carbon_saved": 0.0,
            }).execute()
            record = init.data[0]

        current_points = record["points"]
        current_badges = record.get("badges") or []
        current_level  = record["level"]
        print(f"[award] current: points={current_points}, level={current_level}, badges={current_badges}")

        xp = XP_MAP[action]
        is_first_report = action == "first_report"
        if is_first_report and "Πρώτη Αναφορά" in current_badges:
            print("[award] first_report already awarded — skipping XP")
            xp = 0

        new_points = current_points + xp
        new_level  = _level_for(new_points)
        print(f"[award] xp_awarded={xp}, new_points={new_points}, new_level={new_level}")

        supabase.table("user_points").update({
            "points":     new_points,
            "level":      new_level,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("user_id", user_id).execute()
        print("[award] user_points updated in DB")

        new_badges = _compute_badges(user_id, current_badges)

        print(f"[AWARD XP] xp_awarded={xp}, total={new_points}, badges={new_badges}")
        return {
            "xp_awarded":   xp,
            "total_points": new_points,
            "level":        new_level,
            "new_badges":   new_badges,
            "first_report": is_first_report,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"award_points ERROR: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/{user_id}")
def get_user_stats(user_id: str):
    try:
        result = supabase.table("user_points").select("*").eq("user_id", user_id).execute()
        if not result.data:
            return {"user_id": user_id, "points": 0, "badges": [], "level": 1}
        row = result.data[0]
        return {
            "user_id": user_id,
            "points":  row.get("points", 0),
            "badges":  row.get("badges", []),
            "level":   row.get("level", 1),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaderboard")
def get_leaderboard():
    try:
        print("[leaderboard] Fetching top 50 from user_points...")
        points_resp = (
            supabase.table("user_points")
            .select("user_id, points, level, badges")
            .order("points", desc=True)
            .limit(50)
            .execute()
        )

        if not points_resp.data:
            return {"leaderboard": []}

        user_ids = [r["user_id"] for r in points_resp.data]
        users_resp = (
            supabase.table("users")
            .select("id, full_name, email")
            .in_("id", user_ids)
            .execute()
        )

        users_map = {u["id"]: u for u in (users_resp.data or [])}
        leaderboard = []
        for i, row in enumerate(points_resp.data):
            user = users_map.get(row["user_id"], {})
            leaderboard.append({
                "rank":      i + 1,
                "user_id":   row["user_id"],
                "full_name": user.get("full_name", "Ανώνυμος"),
                "points":    row["points"],
                "level":     row["level"],
                "badges":    row["badges"] or [],
            })

        print(f"[leaderboard] Returning {len(leaderboard)} entries")
        return {"leaderboard": leaderboard}

    except Exception as e:
        print(f"[LEADERBOARD ERROR] {e}")
        return {"leaderboard": []}
