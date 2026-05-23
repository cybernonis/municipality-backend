import anthropic
import json
from app.database import supabase
from app.config import ANTHROPIC_API_KEY
from datetime import datetime, timezone, timedelta

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def get_historical_data() -> dict:
    reports = supabase.table("reports")\
        .select("category, severity, status, address, created_at")\
        .execute()
    
    data = reports.data or []
    
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

    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent = [r for r in data if r.get("created_at", "") > week_ago]

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
    hist = get_historical_data()
    
    prompt = (
        "Είσαι AI σύστημα Predictive Maintenance για τον Δήμο Ηρακλείου.\n\n"
        f"ΙΣΤΟΡΙΚΑ ΔΕΔΟΜΕΝΑ:\n"
        f"- Συνολικές αναφορές: {hist['total_reports']}\n"
        f"- Τελευταίες 7 μέρες: {hist['recent_7days']}\n"
        f"- Ποσοστό επίλυσης: {hist['completion_rate']}%\n\n"
        f"ΑΝΑΦΟΡΕΣ ΑΝΑ ΚΑΤΗΓΟΡΙΑ:\n"
        f"{json.dumps(hist['by_category'], ensure_ascii=False, indent=2)}\n\n"
        f"TOP ΠΕΡΙΟΧΕΣ ΜΕ ΠΡΟΒΛΗΜΑΤΑ:\n"
        f"{json.dumps(hist['top_problem_areas'], ensure_ascii=False, indent=2)}\n\n"
        "Βάσει αυτών των δεδομένων, δώσε μου:\n"
        "1. Προβλέψεις για τις επόμενες 30 μέρες\n"
        "2. Περιοχές υψηλού κινδύνου\n"
        "3. Κατηγορίες που χρειάζονται προσοχή\n"
        "4. Συστάσεις για προληπτική συντήρηση\n"
        "5. Budget allocation πρόταση\n\n"
        'Απάντησε ΜΟΝΟ με JSON:\n'
        '{\n'
        '  "predictions": [\n'
        '    {\n'
        '      "category": "string",\n'
        '      "risk_level": "high|medium|low",\n'
        '      "predicted_increase": "percentage string",\n'
        '      "reasoning": "string στα ελληνικά",\n'
        '      "recommended_action": "string στα ελληνικά"\n'
        '    }\n'
        '  ],\n'
        '  "high_risk_areas": [\n'
        '    {\n'
        '      "area": "string",\n'
        '      "risk_score": "0-100",\n'
        '      "main_issue": "string"\n'
        '    }\n'
        '  ],\n'
        '  "budget_recommendations": [\n'
        '    {\n'
        '      "department": "string",\n'
        '      "priority": "high|medium|low",\n'
        '      "recommendation": "string στα ελληνικά",\n'
        '      "estimated_savings": "string"\n'
        '    }\n'
        '  ],\n'
        '  "summary": "string στα ελληνικά"\n'
        '}'
    )

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    result = json.loads(message.content[0].text)
    
    supabase.table("ai_predictions").insert({
        "id": __import__("uuid").uuid4().__str__(),
        "type": "predictive_maintenance",
        "area": "Ηράκλειο",
        "confidence": 0.85,
        "recommendation": result.get("summary", ""),
    }).execute()
    
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "historical_data": hist,
        "predictions": result
    }