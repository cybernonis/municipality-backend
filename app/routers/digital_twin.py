from fastapi import APIRouter
from app.database import supabase
from app.config import ANTHROPIC_API_KEY
import anthropic
import json
import time
import random

router = APIRouter()


# ── ΚΑΝΟΝΑΣ #1: ο Anthropic client ΠΑΝΤΑ μέσα σε function, ΠΟΤΕ global ──
def get_client():
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ─────────────────────────────────────────────────────────────────────────────
#  Snapshot / Layers / Heatmap (αμετάβλητα)
# ─────────────────────────────────────────────────────────────────────────────
def get_snapshot_data():
    reports = supabase.table("reports") \
        .select("id, category, severity, status, latitude, longitude") \
        .limit(50).execute()
    time.sleep(0.1)
    devices = supabase.table("iot_devices") \
        .select("id, name, type, latitude, longitude, status, battery_level") \
        .execute()
    time.sleep(0.1)
    crises = supabase.table("crisis_events") \
        .select("id, type, latitude, longitude, status, severity") \
        .eq("status", "active").limit(10).execute()

    reports_data = reports.data or []
    devices_data = devices.data or []
    crises_data = crises.data or []
    return {
        "reports": reports_data,
        "iot_devices": devices_data,
        "crises": crises_data,
        "summary": {
            "total_reports": len(reports_data),
            "open_reports": len([r for r in reports_data if r["status"] != "completed"]),
            "iot_devices": len(devices_data),
            "active_alerts": 0,
            "active_crises": len(crises_data),
        },
    }


@router.get("/snapshot")
def get_city_snapshot():
    return get_snapshot_data()


@router.get("/layers")
def get_map_layers():
    data = get_snapshot_data()
    return {
        "reports": [
            {
                "id": r["id"], "lat": r["latitude"], "lng": r["longitude"],
                "category": r.get("category", "other"),
                "severity": r.get("severity", "medium"),
                "status": r.get("status", "submitted"),
                "created_at": r.get("created_at", ""),
            }
            for r in data["reports"] if r.get("latitude") and r.get("longitude")
        ],
        "iot_devices": [
            {
                "id": d["id"], "lat": d["latitude"], "lng": d["longitude"],
                "device_type": d["type"], "name": d["name"],
                "status": d["status"], "battery": d.get("battery_level", 100),
            }
            for d in data["iot_devices"] if d.get("latitude") and d.get("longitude")
        ],
        "crises": [
            {
                "id": c["id"], "lat": c["latitude"], "lng": c["longitude"],
                "crisis_type": c["type"], "severity": c.get("severity", "high"),
                "created_at": c.get("created_at", ""),
            }
            for c in data["crises"]
        ],
    }


@router.get("/heatmap")
def get_heatmap_data():
    reports = supabase.table("reports").select("latitude, longitude, severity").execute()
    return {
        "points": [
            {
                "lat": r["latitude"], "lng": r["longitude"],
                "intensity": 3 if r["severity"] == "high" else 2 if r["severity"] == "medium" else 1,
            }
            for r in (reports.data or [])
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Crisis simulation  (POST /digital-twin/simulate)
#  Body: { "type": "flood|fire|earthquake|heatwave|frost", "params": {...} }
#  Επιστρέφει: { risk_score, affected, severity, summary, actions[], areas[], zones[] }
# ─────────────────────────────────────────────────────────────────────────────
CRISIS_LABELS = {
    "flood": "Πλημμύρα", "fire": "Πυρκαγιά", "earthquake": "Σεισμός",
    "heatwave": "Καύσωνας", "frost": "Παγετός",
}


def _compute_risk(ctype: str, p: dict) -> int:
    if ctype == "flood":
        lvl = p.get("floodLevel", "strong")
        return {"catastrophic": 9, "extreme": 7, "strong": 5, "moderate": 3}.get(lvl, 4)
    if ctype == "fire":
        return {"high": 8, "medium": 6, "low": 4}.get(p.get("fireDrought", "medium"), 5)
    if ctype == "earthquake":
        mag = float(p.get("quakeMag", 6.0) or 6.0)
        return max(1, min(10, round((mag - 4) * 2.5)))
    if ctype == "heatwave":
        peak = float(p.get("heatPeak", 40) or 40)
        return 7 if peak > 42 else 5 if peak > 38 else 3
    if ctype == "frost":
        return 6 if float(p.get("frostTemp", -3) or -3) < -5 else 3
    return 5


def _compute_zones(ctype: str, p: dict):
    if ctype == "flood":
        radii = [4500, 2500, 1000] if p.get("floodLevel") == "catastrophic" else [2500, 1500, 600]
    elif ctype == "fire":
        radii = [900, 500, 200]
    elif ctype == "earthquake":
        mag = float(p.get("quakeMag", 6.0) or 6.0)
        radii = [round((mag - 4) * 1600), round((mag - 4) * 1000), round((mag - 4) * 400)]
    elif ctype == "heatwave":
        radii = [5000, 3000, 1500]
    elif ctype == "frost":
        radii = [3000, 2000, 1000]
    else:
        radii = [2000, 1200, 500]
    radii = [max(200, r) for r in radii]
    levels = ["red", "yellow", "green"]
    return [{"level": levels[i], "radius": radii[i]} for i in range(len(radii))]


@router.post("/simulate")
def simulate_scenario(payload: dict):
    ctype = (payload or {}).get("type", "flood")
    params = (payload or {}).get("params", {}) or {}

    risk = _compute_risk(ctype, params)
    zones = _compute_zones(ctype, params)
    affected = round(risk * 3200 + random.random() * 4000)
    severity = "Κρίσιμο" if risk >= 8 else "Υψηλό" if risk >= 6 else "Μέτριο" if risk >= 4 else "Χαμηλό"
    label = CRISIS_LABELS.get(ctype, ctype)

    # defaults (fallback αν αποτύχει ο Claude)
    summary = f"Προσομοίωση {label}. Επίπεδο κινδύνου: {risk}/10 ({severity})."
    actions = ["Ενεργοποίηση πρωτοκόλλου έκτακτης ανάγκης", "Ειδοποίηση πολιτών", "Συντονισμός Πολιτικής Προστασίας"]
    areas = ["Κέντρο Ηρακλείου", "Παραλιακή Ζώνη", "Λιμάνι"]

    prompt = f"""Είσαι AI σύστημα Digital Twin Πολιτικής Προστασίας για τον Δήμο Ηρακλείου.

ΣΕΝΑΡΙΟ: {label}
ΠΑΡΑΜΕΤΡΟΙ: {json.dumps(params, ensure_ascii=False)}
ΥΠΟΛΟΓΙΣΜΕΝΟ ΕΠΙΠΕΔΟ ΚΙΝΔΥΝΟΥ: {risk}/10 ({severity})
ΕΚΤΙΜΩΜΕΝΟΙ ΠΛΗΓΕΝΤΕΣ: ~{affected}

Δώσε συγκεκριμένες, ρεαλιστικές οδηγίες για το Ηράκλειο.
Απάντησε ΜΟΝΟ με έγκυρο JSON, χωρίς markdown, στη μορφή:
{{"summary":"σύντομη σύνοψη 1-2 προτάσεων στα ελληνικά","recommended_actions":["δράση 1","δράση 2","δράση 3","δράση 4"],"affected_areas":["περιοχή 1","περιοχή 2"]}}"""

    try:
        client = get_client()
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data = json.loads(text)
        summary = data.get("summary") or summary
        actions = data.get("recommended_actions") or data.get("actions") or actions
        areas = data.get("affected_areas") or data.get("areas") or areas
    except Exception:
        pass  # κρατάμε τα defaults

    return {
        "risk_score": risk,
        "affected": affected,
        "severity": severity,
        "summary": summary,
        "actions": actions,
        "areas": areas,
        "zones": zones,
    }