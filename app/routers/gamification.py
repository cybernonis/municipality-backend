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
    """Count reports WHERE user_id = X and award threshold badges."""
    print(f"[badges] Computing for user_id={user_id}, current={current_badges}")
    result = supabase.table("reports").select("id", count="exact").eq("user_id", user_id).execute()
    total_reports = result.count or 0
    print(f"[badges] user_id={user_id} total_reports={total_reports}")

    new_badges = [
        badge
        for threshold, badge in BADGE_THRESHOLDS
        if total_reports >= threshold and badge not in current_badges
    ]
    print(f"[badges] new_badges={new_badges}")

    if new_badges:
        all_badges = current_badges + new_badges
        supabase.table("user_points").update({"badges": all_badges}).eq("user_id", user_id).execute()
        print(f"[badges] DB updated all_badges={all_badges}")

    return new_badges


def _get_or_create_user_points(user_id: str) -> dict:
    """Fetch existing row or upsert defaults; always returns a dict."""
    existing = supabase.table("user_points").select("*").eq("user_id", user_id).execute()
    if existing.data:
        print(f"[award] Existing record for user_id={user_id}")
        return existing.data[0]

    print(f"[award] No record — upserting defaults for user_id={user_id}")
    defaults = {
        "user_id":      user_id,
        "points":       0,
        "badges":       [],
        "level":        1,
        "carbon_saved": 0.0,
    }
    # upsert prevents race-condition failure if row was created between SELECT and INSERT
    result = supabase.table("user_points").upsert(defaults, on_conflict="user_id").execute()
    if result.data:
        return result.data[0]

    # Some Supabase configs return empty on upsert — re-fetch to confirm
    refetch = supabase.table("user_points").select("*").eq("user_id", user_id).execute()
    if refetch.data:
        return refetch.data[0]

    logger.warning(f"[award] upsert returned no data for user_id={user_id} — using in-memory defaults")
    return defaults


def _update_points(user_id: str, new_points: int, new_level: int) -> None:
    """Update points + level; falls back without updated_at if column missing."""
    update_data: dict = {
        "points": new_points,
        "level":  new_level,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        supabase.table("user_points").update(update_data).eq("user_id", user_id).execute()
        print(f"[award] user_points updated: points={new_points}, level={new_level}")
    except Exception as err:
        logger.warning(f"[award] update with updated_at failed ({err}) — retrying without")
        del update_data["updated_at"]
        supabase.table("user_points").update(update_data).eq("user_id", user_id).execute()
        print(f"[award] user_points updated (no updated_at): points={new_points}, level={new_level}")


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
    print(f"[award] START user_id={payload.user_id} action={payload.action}")
    try:
        record = _get_or_create_user_points(payload.user_id)

        current_points = record.get("points") or 0
        current_badges = record.get("badges") or []
        current_level  = record.get("level") or 1
        print(f"[award] current: points={current_points}, level={current_level}, badges={current_badges}")

        xp = XP_MAP[payload.action]
        if payload.action == "first_report" and "Πρώτη Αναφορά" in current_badges:
            print("[award] first_report already awarded — skipping XP")
            xp = 0

        new_points = current_points + xp
        new_level  = _level_for(new_points)
        print(f"[award] xp_awarded={xp}, new_points={new_points}, new_level={new_level}")

        _update_points(payload.user_id, new_points, new_level)

        new_badges = _compute_badges(payload.user_id, current_badges)
        all_badges = current_badges + new_badges

        print(f"[award] DONE xp={xp}, total={new_points}, new_badges={new_badges}")
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
        logger.exception(f"[award] Unexpected error for user_id={payload.user_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaderboard")
def get_leaderboard():
    try:
        print("[leaderboard] Fetching top 10 from user_points...")
        points_result = (
            supabase.table("user_points")
            .select("user_id, points, badges, level")
            .order("points", desc=True)
            .limit(10)
            .execute()
        )
        rows = points_result.data or []
        print(f"[leaderboard] Got {len(rows)} rows")

        user_ids = [row["user_id"] for row in rows]
        name_map: dict = {}
        if user_ids:
            try:
                users_result = (
                    supabase.table("users")
                    .select("id, full_name")
                    .in_("id", user_ids)
                    .execute()
                )
                name_map = {
                    u["id"]: u.get("full_name") or "Ανώνυμος"
                    for u in (users_result.data or [])
                }
                print(f"[leaderboard] Resolved {len(name_map)} display names")
            except Exception as name_err:
                print(f"[leaderboard] WARNING: could not fetch user names: {name_err}")

        leaderboard = [
            {
                "rank":         rank,
                "user_id":      row["user_id"],
                "display_name": name_map.get(row["user_id"], "Ανώνυμος"),
                "points":       row["points"],
                "badges":       row.get("badges") or [],
                "level":        row["level"],
            }
            for rank, row in enumerate(rows, start=1)
        ]
        return {"leaderboard": leaderboard, "total": len(leaderboard)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[leaderboard] Unexpected error")
        raise HTTPException(status_code=500, detail=str(e))
