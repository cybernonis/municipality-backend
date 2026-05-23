import anthropic
import json
from app.database import supabase
from app.config import ANTHROPIC_API_KEY
from datetime import datetime, timezone, timedelta

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def get_historical_data() -> dict:
    """Συλλέγει ιστορικά δεδομένα για ανάλυση"""
    
    # Όλες οι αναφορές
    reports = supabase.table("reports")\
        .select("category, severity, status, latitude, longitude, address, created_at")\
        .execute()
    
    data = reports.data or []
    
    # Ανάλυση ανά κατηγορία
    by_category = {}
    for r in data:
        cat = r.get("category", "other")
        if cat not in by_category:
            by_category[cat] = {"total": 0, "high": 0, "completed": 0}
        by_category[cat]["total"] += 1
        if r.get("severity") == "high":
            by_category[cat]["high"] += 1
        if r.get("status") == "completed":
            by_category[cat]["completed"] += 1

    # Αναφορές τελευταίων 7 ημερών
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent = [r for r in data if r.get("created_at", "") > week_ago]

    # Top περιοχές
    areas = {}
    for r in data:
        addr = r.get("address", "Άγνωστο")
        areas[addr] = areas.get(addr, 0) + 1
    
    top_areas = sorted(areas.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "total_reports": len(data),
        "recent_7days": len(recent),
        "by_category": by_category,
        "top_problem_areas": top_areas,
        "completion_rate": round(
            len([r for r in data if r.get("status") == "completed"]) / len(data) * 100
            if data else 0
        ),
    }

def predict_maintenance() -> dict:
    """Χρησιμοποιεί Claude για predictive maintenance"""
    
    hist = get_historical_data()
    
    prompt = f"""
Είσαι AI σύστημα Predictive Maintenance για τον Δήμο Ηρακλείου.

ΙΣΤΟΡΙΚΑ ΔΕΔΟΜΕΝΑ:
- Συνολικές αναφορές: {hist['total_reports']}
- Τελευταίες 7 μέρες: {hist['recent_7days']}
- Ποσοστό επίλυσης: {hist['completion_rate']}%

ΑΝΑΦΟΡΕΣ ΑΝΑ ΚΑΤΗΓΟΡΙΑ:
{json.dumps(hist['by_category'], ensure_ascii=False, indent=2)}

TOP ΠΕΡΙΟΧΕΣ ΜΕ ΠΡΟΒΛΗΜΑΤΑ:
{json.dumps(hist['top_problem_areas'], ensure_ascii=False, indent=2)}

Βάσει αυτών των δεδομένων, δώσε μου:
1.