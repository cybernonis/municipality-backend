from fastapi import APIRouter, HTTPException
from app.database import supabase
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import uuid

router = APIRouter()

class PerformanceCreate(BaseModel):
    report_id: str
    worker_id: str
    assigned_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    citizen_rating: Optional[int] = None

class RatingCreate(BaseModel):
    report_id: str
    rating: int  # 1-5

def calculate_speed_score(actual_hours: float, target_hours: float) -> float:
    ratio = actual_hours / target_hours if target_hours > 0 else 1
    if ratio <= 0.5:  return 100
    if ratio <= 0.75: return 90
    if ratio <= 1.0:  return 75
    if ratio <= 1.25: return 50
    if ratio <= 1.5:  return 25
    return 0

def calculate_quality_score(rating: Optional[int]) -> float:
    if rating is None: return 60  # default
    scores = {1: 0, 2: 30, 3: 60, 4: 80, 5: 100}
    return scores.get(rating, 60)

def calculate_total_score(speed: float, quality: float) -> float:
    return round(speed * 0.4 + quality * 0.35 + 75 * 0.25, 1)

@router.get("/leaderboard")
def get_leaderboard():
    # Πάρε όλα τα performance records
    records = supabase.table("performance_records")\
        .select("*, users(full_name, department_id)")\
        .execute()

    if not records.data:
        return []

    # Ομαδοποίησε ανά worker
    workers = {}
    for r in records.data:
        wid = r["worker_id"]
        if wid not in workers:
            workers[wid] = {
                "worker_id": wid,
                "name": r.get("users", {}).get("full_name", "Άγνωστος") if r.get("users") else "Άγνωστος",
                "records": [],
                "total_score": 0,
                "avg_rating": 0,
                "on_time_count": 0,
                "total_count": 0,
            }
        workers[wid]["records"].append(r)
        workers[wid]["total_count"] += 1
        if r.get("on_time"): workers[wid]["on_time_count"] += 1

    # Υπολόγισε scores
    leaderboard = []
    for wid, data in workers.items():
        records_list = data["records"]
        avg_score = sum(r.get("total_score", 0) or 0 for r in records_list) / len(records_list)
        ratings = [r["citizen_rating"] for r in records_list if r.get("citizen_rating")]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        on_time_pct = round(data["on_time_count"] / data["total_count"] * 100) if data["total_count"] > 0 else 0

        leaderboard.append({
            "worker_id": wid,
            "name": data["name"],
            "total_score": round(avg_score, 1),
            "avg_rating": round(avg_rating, 1),
            "on_time_percentage": on_time_pct,
            "total_tickets": data["total_count"],
        })

    leaderboard.sort(key=lambda x: x["total_score"], reverse=True)
    return leaderboard

@router.post("/rate")
def rate_report(rating_data: RatingCreate):
    if not 1 <= rating_data.rating <= 5:
        raise HTTPException(status_code=400, detail="Rating 1-5")

    # Βρες το report
    report = supabase.table("reports")\
        .select("*, sla_rules(target_hours)")\
        .eq("id", rating_data.report_id)\
        .execute()

    if not report.data:
        raise HTTPException(status_code=404, detail="Report not found")

    r = report.data[0]

    # Υπολόγισε χρόνο επίλυσης
    created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    actual_hours = (now - created).total_seconds() / 3600

    # Βρες SLA target
    sla = supabase.table("sla_rules")\
        .select("target_hours")\
        .eq("category", r.get("category", "other"))\
        .eq("severity", r.get("severity", "medium"))\
        .execute()

    target_hours = sla.data[0]["target_hours"] if sla.data else 48
    on_time = actual_hours <= target_hours

    # Υπολόγισε scores
    speed = calculate_speed_score(actual_hours, target_hours)
    quality = calculate_quality_score(rating_data.rating)
    total = calculate_total_score(speed, quality)

    # Αποθήκευσε
    perf_data = {
        "id": str(uuid.uuid4()),
        "report_id": rating_data.report_id,
        "worker_id": r.get("assigned_to") or "unassigned",
        "completed_at": now.isoformat(),
        "citizen_rating": rating_data.rating,
        "speed_score": speed,
        "quality_score": quality,
        "total_score": total,
        "on_time": on_time,
    }

    supabase.table("performance_records").insert(perf_data).execute()

    # Badge logic
    if rating_data.rating == 5 and on_time and r.get("assigned_to"):
        supabase.table("badges").insert({
            "id": str(uuid.uuid4()),
            "worker_id": r["assigned_to"],
            "badge_type": "top_rated",
        }).execute()

    return {
        "message": "Αξιολόγηση καταχωρήθηκε!",
        "speed_score": speed,
        "quality_score": quality,
        "total_score": total,
        "on_time": on_time,
    }

@router.get("/worker/{worker_id}")
def get_worker_stats(worker_id: str):
    records = supabase.table("performance_records")\
        .select("*")\
        .eq("worker_id", worker_id)\
        .execute()

    badges = supabase.table("badges")\
        .select("*")\
        .eq("worker_id", worker_id)\
        .execute()

    if not records.data:
        return {"worker_id": worker_id, "total_tickets": 0, "badges": []}

    data = records.data
    ratings = [r["citizen_rating"] for r in data if r.get("citizen_rating")]
    on_time = [r for r in data if r.get("on_time")]

    return {
        "worker_id": worker_id,
        "total_tickets": len(data),
        "avg_score": round(sum(r.get("total_score", 0) or 0 for r in data) / len(data), 1),
        "avg_rating": round(sum(ratings) / len(ratings), 1) if ratings else 0,
        "on_time_percentage": round(len(on_time) / len(data) * 100),
        "badges": badges.data or [],
    }