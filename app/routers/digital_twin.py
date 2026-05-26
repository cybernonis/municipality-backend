from fastapi import APIRouter
from app.database import supabase
from app.config import ANTHROPIC_API_KEY
import anthropic
import json
import time

router = APIRouter()
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def get_snapshot_data():
    reports = supabase.table("reports")\
        .select("id, category, severity, status, latitude, longitude")\
        .limit(50)\
        .execute()

    time.sleep(0.1)

    devices = supabase.table("iot_devices")\
        .select("id, name, type, latitude, longitude, status, battery_level")\
        .execute()

    time.sleep(0.1)

    crises = supabase.table("crisis_events")\
        .select("id, type, latitude, longitude, status, severity")\
        .eq("status", "active")\
        .limit(10)\
        .execute()

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
        }
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
        "id": r["id"],
        "lat": r["latitude"],
        "lng": r["longitude"],
        "category": r.get("category", "other"),
        "severity": r.get("severity", "medium"),
        "status": r.get("status", "submitted"),
        "created_at": r.get("created_at", ""),  # ← ΠΡΟΣΘΕΣΕ
    }
    for r in data["reports"]
],
        "iot_devices": [
            {
                "id": d["id"],
                "lat": d["latitude"],
                "lng": d["longitude"],
                "device_type": d["type"],
                "name": d["name"],
                "status": d["status"],
                "battery": d.get("battery_level", 100),
            }
            for d in data["iot_devices"]
            if d.get("latitude") and d.get("longitude")
        ],
        "crises": [
    {
        "id": c["id"],
        "lat": c["latitude"],
        "lng": c["longitude"],
        "crisis_type": c["type"],
        "severity": c.get("severity", "high"),
        "created_at": c.get("created_at", ""),  # ← ΠΡΟΣΘΕΣΕ
    }
    for c in data["crises"]
],
    }

@router.get("/heatmap")
def get_heatmap_data():
    reports = supabase.table("reports")\
        .select("latitude, longitude, severity")\
        .execute()

    return {
        "points": [
            {
                "lat": r["latitude"],
                "lng": r["longitude"],
                "intensity": 3 if r["severity"] == "high" else 2 if r["severity"] == "medium" else 1,
            }
            for r in (reports.data or [])
        ]
    }

@router.post("/simulate")
def simulate_scenario(scenario: dict):
    data = get_snapshot_data()
    summary = data["summary"]

    prompt = f"""
Είσαι AI σύστημα Digital Twin για τον Δήμο Ηρακλείου.

ΚΑΤΑΣΤΑΣΗ ΠΟΛΗΣ:
- Συνολικές αναφορές: {summary['total_reports']}
- Ανοιχτές: {summary['open_reports']}
- IoT συσκευές: {summary['iot_devices']}
- Ενεργές κρίσεις: {summary['active_crises']}

ΣΕΝΑΡΙΟ: {scenario.get('type', 'flood')} στην περιοχή {scenario.get('location', 'κέντρο')}
ΠΕΡΙΓΡΑΦΗ: {scenario.get('description', '')}

Απάντησε ΜΟΝΟ με έγκυρο JSON χωρίς markdown:
{{"impact_assessment":{{"severity":"high","affected_areas":["Κέντρο Ηρακλείου"],"affected_population":"5000 κάτοικοι","estimated_duration":"2-4 ώρες"}},"required_resources":[{{"type":"Πυροσβεστική","quantity":"3 οχήματα","priority":"high"}}],"recommended_actions":[{{"action":"Εκκένωση περιοχής","timeline":"Άμεσα","department":"Πολιτική Προστασία"}}],"summary":"Σύνοψη σεναρίου στα ελληνικά"}}
"""

    try:
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        text = message.content[0].text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        return json.loads(text)

    except Exception as e:
        return {
            "impact_assessment": {
                "severity": "high",
                "affected_areas": [scenario.get('location', 'Κέντρο')],
                "affected_population": "Άγνωστο",
                "estimated_duration": "2-4 ώρες"
            },
            "required_resources": [
                {"type": "Άμεση Βοήθεια", "quantity": "Κατά περίπτωση", "priority": "high"}
            ],
            "recommended_actions": [
                {"action": "Επικοινωνία με 112", "timeline": "Άμεσα", "department": "Πολιτική Προστασία"}
            ],
            "summary": f"Σενάριο {scenario.get('type')} στην περιοχή {scenario.get('location')}. Απαιτείται άμεση δράση."
        }