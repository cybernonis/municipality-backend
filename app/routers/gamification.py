import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_supabase

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


class AwardRequest(BaseModel):
    user_id: str
    action: str


@router.post("/award")
async def award_points(payload: AwardRequest):
    if payload.action not in XP_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Άγνωστη action. Επιτρεπτές: {list(XP_MAP)}",
        )

    user_id = payload.user_id
    action  = payload.action
    print(f"[AWARD XP] user_id={user_id}, action={action}")

    try:
        client = get_supabase()

        # 1. Διάβασε τρέχον record
        existing = client.table("user_points").select("*").eq("user_id", user_id).execute()
        print(f"[UPSERT] Existing record: {existing.data}")

        current_points = 0
        current_badges: list = []

        if existing.data:
            current_points = existing.data[0].get("points", 0) or 0
            current_badges = existing.data[0].get("badges") or []

        # 2. Υπολόγισε νέα XP
        xp = XP_MAP[action]
        is_first_report = action == "first_report"
        if is_first_report and "Πρώτη Αναφορά" in current_badges:
            print("[AWARD XP] first_report already awarded — skipping XP")
            xp = 0

        new_total = current_points + xp
        new_level = _level_for(new_total)

        # 3. Υπολόγισε badges από reports count
        reports_resp = (
            client.table("reports")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        count = reports_resp.count or 0
        print(f"[AWARD XP] reports count={count}")

        new_badges = list(current_badges)
        if count >= 1  and "Πρώτη Αναφορά" not in new_badges:
            new_badges.append("Πρώτη Αναφορά")
        if count >= 10 and "10 Αναφορές"   not in new_badges:
            new_badges.append("10 Αναφορές")
        if count >= 50 and "Super Citizen"  not in new_badges:
            new_badges.append("Super Citizen")

        added_badges = [b for b in new_badges if b not in current_badges]

        # 4. UPSERT στο Supabase
        print(f"[UPSERT] Writing user_id={user_id}, points={new_total}, level={new_level}, badges={new_badges}")

        if existing.data:
            result = (
                client.table("user_points")
                .update({
                    "points": new_total,
                    "level":  new_level,
                    "badges": new_badges,
                })
                .eq("user_id", user_id)
                .execute()
            )
        else:
            result = (
                client.table("user_points")
                .insert({
                    "user_id":      user_id,
                    "points":       new_total,
                    "level":        new_level,
                    "badges":       new_badges,
                    "carbon_saved": 0,
                })
                .execute()
            )

        print(f"[UPSERT] Result data: {result.data}")
        print(f"[AWARD XP] xp_awarded={xp}, total={new_total}, badges={added_badges}")

        return {
            "xp_awarded":   xp,
            "total_points": new_total,
            "level":        new_level,
            "new_badges":   added_badges,
            "first_report": count == 1,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"award_points ERROR: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user-points/{user_id}")
async def get_user_points(user_id: str):
    try:
        client = get_supabase()
        result = client.table("user_points").select("*").eq("user_id", user_id).execute()

        if not result.data:
            return {
                "user_id":      user_id,
                "points":       0,
                "level":        1,
                "badges":       [],
                "carbon_saved": 0,
            }

        row = result.data[0]
        return {
            "user_id":      row["user_id"],
            "points":       row.get("points", 0) or 0,
            "level":        row.get("level", 1) or 1,
            "badges":       row.get("badges") or [],
            "carbon_saved": row.get("carbon_saved", 0) or 0,
        }

    except Exception as e:
        print(f"[USER POINTS ERROR] {e}")
        return {"user_id": user_id, "points": 0, "level": 1, "badges": [], "carbon_saved": 0}


@router.get("/stats/{user_id}")
async def get_user_stats(user_id: str):
    try:
        client = get_supabase()
        result = client.table("user_points").select("*").eq("user_id", user_id).execute()
        if not result.data:
            return {"user_id": user_id, "points": 0, "badges": [], "level": 1}
        row = result.data[0]
        return {
            "user_id": user_id,
            "points":  row.get("points", 0) or 0,
            "badges":  row.get("badges") or [],
            "level":   row.get("level", 1) or 1,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaderboard")
async def get_leaderboard():
    try:
        client = get_supabase()
        print("[LEADERBOARD] Starting query...")

        # RLS / connectivity check — αν count==0 ενώ έχουμε records → RLS block
        test = client.table("user_points").select("count", count="exact").execute()
        print(f"[LEADERBOARD] Table count: {test.count}")

        points_resp = (
            client.table("user_points")
            .select("user_id, points, level, badges")
            .order("points", desc=True)
            .limit(50)
            .execute()
        )

        print(f"[LEADERBOARD] Raw data: {points_resp.data}")
        print(f"[LEADERBOARD] Count: {len(points_resp.data) if points_resp.data else 0}")

        if not points_resp.data:
            print("[LEADERBOARD] No data found — returning empty list")
            return {"leaderboard": []}

        user_ids = [r["user_id"] for r in points_resp.data]
        print(f"[LEADERBOARD] User IDs: {user_ids}")

        users_resp = (
            client.table("user_profiles")
            .select("id, full_name, email")
            .in_("id", user_ids)
            .execute()
        )

        print(f"[LEADERBOARD] Users found: {users_resp.data}")

        users_map = {u["id"]: u for u in (users_resp.data or [])}

        leaderboard = []  # ΠΑΝΤΑ list, ποτέ dict
        for i, row in enumerate(points_resp.data):
            user = users_map.get(row.get("user_id"), {})
            entry = {
                "rank":      i + 1,
                "user_id":   row.get("user_id", ""),
                "full_name": user.get("full_name", "Ανώνυμος"),
                "points":    row.get("points", 0) or 0,
                "level":     row.get("level", 1) or 1,
                "badges":    row.get("badges") or [],
            }
            leaderboard.append(entry)
            print(f"[LEADERBOARD] Entry {i + 1}: {entry}")

        print(f"[LEADERBOARD] Final list length: {len(leaderboard)}")
        return {"leaderboard": leaderboard}

    except Exception as e:
        print(f"[LEADERBOARD ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return {"leaderboard": []}
