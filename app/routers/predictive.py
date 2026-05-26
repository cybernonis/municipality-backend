from fastapi import APIRouter, HTTPException
from app.services.predictive_service import predict_maintenance, get_historical_data
from app.database import supabase

router = APIRouter()

@router.get("/analyze")
def analyze():
    try:
        result = predict_maintenance()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
def get_history():
    result = supabase.table("ai_predictions")\
        .select("*")\
        .eq("type", "predictive_maintenance")\
        .order("created_at", desc=True)\
        .limit(10)\
        .execute()
    return result.data

@router.get("/quick-stats")
def quick_stats():
    return get_historical_data()

@router.get("/heatmap")
async def predictive_heatmap():
    try:
        from app.database import supabase
        from app.config import ANTHROPIC_API_KEY
        import anthropic
        import json

        # Πάρε τα τελευταία reports
        reports = supabase.table("reports")\
            .select("category, severity, latitude, longitude, created_at, status")\
            .order("created_at", desc=True)\
            .limit(100)\
            .execute()

        # Πάρε external data για καιρό
        from app.services.external_service import fetch_weather
        weather = await fetch_weather()

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Ομαδοποίηση ανά περιοχή
        area_stats: dict = {}
        for r in (reports.data or []):
            lat = round(r.get("latitude", 0), 2)
            lng = round(r.get("longitude", 0), 2)
            key = f"{lat},{lng}"
            if key not in area_stats:
                area_stats[key] = {"lat": lat, "lng": lng, "count": 0, "high": 0, "categories": []}
            area_stats[key]["count"] += 1
            if r.get("severity") == "high":
                area_stats[key]["high"] += 1
            area_stats[key]["categories"].append(r.get("category", "other"))

        prompt = f"""
Είσαι AI σύστημα πρόβλεψης προβλημάτων για τον Δήμο Ηρακλείου.

ΔΕΔΟΜΕΝΑ ΑΝΑΦΟΡΩΝ ανά περιοχή (lat,lng):
{json.dumps(list(area_stats.values())[:20], ensure_ascii=False)}

ΚΑΙΡΟΣ ΤΩΡΑ:
- Θερμοκρασία: {weather.get('temperature')}°C
- Άνεμος: {weather.get('wind_kmh')} km/h
- Βροχή: {weather.get('rain_probability', 0)*100:.0f}%
- Alerts: {[a['type'] for a in weather.get('alerts', [])]}

Ανάλυσε τα δεδομένα και πρόβλεψε ΠΟΙΕΣ ΠΕΡΙΟΧΕΣ έχουν υψηλό κίνδυνο προβλημάτων τις επόμενες 24-48 ώρες.

Απάντησε ΜΟΝΟ με έγκυρο JSON:
{{
  "hotspots": [
    {{"lat": 35.33, "lng": 25.14, "risk": 0.9, "category": "road_damage", "reason": "Λόγω βροχής και ιστορικού", "predicted_issues": 5}},
    ...
  ],
  "summary": "Σύνοψη πρόβλεψης στα ελληνικά",
  "risk_level": "high",
  "weather_impact": "Η βροχή αυξάνει τον κίνδυνο..."
}}
"""

        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )

        text = message.content[0].text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))