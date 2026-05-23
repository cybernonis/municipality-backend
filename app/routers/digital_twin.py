from fastapi import APIRouter
from app.database import supabase
from app.config import ANTHROPIC_API_KEY
import anthropic
import json

router = APIRouter()
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

@router.get("/snapshot")
def get_city_snapshot():
    """Πλήρης snapshot της πόλης για το Digital Twin"""
    
    # Reports
    reports = supabase.table("reports")\
        .select("id, category, severity, status, latitude, longitude, address, created_at")\
        .execute()
    
    # IoT devices + latest readings
    devices = supabase.table("iot_devices")\
        .select("id, name, type, latitude, longitude, status, battery_level")\
        .execute()
    
    # IoT readings (alerts only)
    alerts = supabase.table("iot_readings")\
        .select("device_id, metric, value, unit, alert")\
        .eq("alert", True)\
        .order("created_at", desc=True)\
        .limit(50)\
        .execute()
    
    # Crisis events
    crises = supabase.table("crisis_events")\
        .select("id, type, latitude, longitude, status, severity")\
        .eq("status", "active")\
        .execute()

    return {
        "reports": reports.data or [],
        "iot_devices": devices.data or [],
        "iot_alerts": alerts.data or [],
        "active_crises": crises.data or [],
        "summary": {
            "total_reports": len(reports.data or []),
            "open_reports": len([r for r in (reports.data or []) if r["status"] != "completed"]),
            "iot_devices": len(devices.data or []),
            "active_alerts": len(alerts.data or []),
            "active_crises": len(crises.data or []),
        }
    }

@router.get("/heatmap")
def get_heatmap_data():
    """Δεδομένα για heatmap"""
    reports = supabase.table("reports")\
        .select("latitude, longitude, severity, category, status")\
        .execute()
    
    points = []
    for r in (reports.data or []):
        intensity = 3 if r["severity"] == "high" else 2 if r["severity"] == "medium" else 1
        points.append({
            "lat": r["latitude"],
            "lng": r["longitude"],
            "intensity": intensity,
            "category": r["category"],
            "status": r["status"]
        })
    
    return {"points": points}

@router.post("/simulate")
def simulate_scenario(scenario: dict):
    """Simulation 'τι θα γίνει αν...'"""
    
    snapshot = get_city_snapshot()
    
    prompt = f"""
Είσαι AI σύστημα Digital Twin για τον Δήμο Ηρακλείου.

ΤΡΕΧΟΥΣΑ ΚΑΤΑΣΤΑΣΗ ΠΟΛΗΣ:
{json.dumps(snapshot['summary'], ensure_ascii=False)}

ΣΕΝΑΡΙΟ ΠΡΟΣΟΜΟΙΩΣΗΣ:
{json.dumps(scenario, ensure_ascii=False)}

Ανάλυσε το σενάριο και δώσε:
1. Πιθανές επιπτώσεις
2. Επηρεαζόμενες περιοχές
3. Απαιτούμενοι πόροι
4. Χρόνος αντιμετώπισης
5. Συστάσεις

Απάντησε ΜΟΝΟ με JSON:
{{
  "impact_assessment": {{
    "severity": "critical|high|medium|low",
    "affected_areas": ["string"],
    "affected_population": "string",
    "estimated_duration": "string"
  }},
  "required_resources": [
    {{"type": "string", "quantity": "string", "priority": "string"}}
  ],
  "recommended_actions": [
    {{"action": "string", "timeline": "string", "department": "string"}}
  ],
  "summary": "string στα ελληνικά"
}}
"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    result = json.loads(message.content[0].text)
    return result

@router.get("/layers")
def get_map_layers():
    """Όλα τα layers για το χάρτη"""
    snapshot = get_city_snapshot()
    
    layers = {
        "reports": [
            {
                "id": r["id"],
                "lat": r["latitude"],
                "lng": r["longitude"],
                "type": "report",
                "category": r["category"],
                "severity": r["severity"],
                "status": r["status"],
            }
            for r in snapshot["reports"]
        ],
        "iot_devices": [
            {
                "id": d["id"],
                "lat": d["latitude"],
                "lng": d["longitude"],
                "type": "iot",
                "device_type": d["type"],
                "name": d["name"],
                "status": d["status"],
                "battery": d["battery_level"],
            }
            for d in snapshot["iot_devices"]
            if d.get("latitude") and d.get("longitude")
        ],
        "crises": [
            {
                "id": c["id"],
                "lat": c["latitude"],
                "lng": c["longitude"],
                "type": "crisis",
                "crisis_type": c["type"],
                "severity": c["severity"],
            }
            for c in snapshot["active_crises"]
        ],
    }
    
    return layers