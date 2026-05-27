import asyncio
import json
import logging
import re

import anthropic
from fastapi import APIRouter, HTTPException

from app.config import ANTHROPIC_API_KEY
from app.database import supabase
from app.services.external_service import fetch_traffic, fetch_weather

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def get_smart_tips():
    def _get_client():
        return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        weather, traffic = await asyncio.gather(fetch_weather(), fetch_traffic())

        reports_result = supabase.table("reports").select(
            "category, severity, address, status"
        ).in_("status", ["submitted", "in_progress"]).limit(20).execute()
        active_reports = reports_result.data or []

        weather_alerts = (
            ", ".join(a["message"] for a in weather.get("alerts", [])) or "Κανένα"
        )
        incidents = traffic.get("incidents", [])
        affected_roads = ", ".join(traffic.get("affected_roads", [])) or "Κανένας"

        report_lines = "\n".join(
            f"- {r.get('category', 'N/A')} ({r.get('severity', 'N/A')}) @ {r.get('address', 'Άγνωστη')}"
            for r in active_reports[:10]
        ) or "Καμία ενεργή αναφορά"

        context = (
            f"Τρέχουσες συνθήκες στο Ηράκλειο:\n\n"
            f"ΚΑΙΡΟΣ: {weather.get('temperature', 'N/A')}°C, {weather.get('description', '')}, "
            f"άνεμος {weather.get('wind_kmh', 'N/A')} km/h, βροχή {weather.get('rain_mm', 0)} mm\n"
            f"Alerts: {weather_alerts}\n\n"
            f"ΚΥΚΛΟΦΟΡΙΑ: επίπεδο={traffic.get('congestion_level', 'N/A')}, "
            f"{len(incidents)} περιστατικά, δρόμοι: {affected_roads}\n\n"
            f"ΕΝΕΡΓΕΣ ΑΝΑΦΟΡΕΣ ({len(active_reports)}):\n{report_lines}"
        )

        prompt = (
            "Βάσει των παραπάνω δεδομένων, δώσε 4-5 έξυπνες πρακτικές συμβουλές για τους πολίτες "
            "του Ηρακλείου για σήμερα. Κάθε συμβουλή να είναι σύντομη (1-2 προτάσεις).\n"
            "Απάντησε ΜΟΝΟ με JSON:\n"
            '{"tips":[{"icon":"emoji","title":"Τίτλος","body":"1-2 προτάσεις","priority":"high|medium|low"}],'
            '"summary":"Γενική εκτίμηση κατάστασης 1-2 προτάσεις"}'
        )

        client = _get_client()
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=800,
            messages=[{"role": "user", "content": context + "\n\n" + prompt}],
        )

        raw = response.content[0].text
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group()) if match else {"tips": [], "summary": ""}

        return {
            "tips": data.get("tips", []),
            "summary": data.get("summary", ""),
            "meta": {
                "weather_temp": weather.get("temperature"),
                "traffic_level": traffic.get("congestion_level"),
                "active_reports": len(active_reports),
            },
        }
    except Exception as e:
        logger.error(f"Smart tips error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
