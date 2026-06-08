"""Citizen-facing endpoints — smart advice, recommendations."""
from fastapi import APIRouter, Query
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.database import supabase

router = APIRouter(prefix="/citizen", tags=["citizen"])

_advice_cache: dict = {}
CACHE_TTL_MINUTES = 30


def _get_cache_key(user_id: Optional[str], lat: float, lng: float) -> str:
    return f"{user_id or 'anonymous'}:{round(lat, 2)}:{round(lng, 2)}"


def _build_rule_based_advice(signals: dict) -> list[dict]:
    cards = []
    now = datetime.now(timezone.utc)
    hour = now.hour

    # ── CRISIS ────────────────────────────────────────────────────
    if signals.get("active_crisis"):
        cards.append({
            "id": "crisis",
            "priority": 100,
            "icon": "🚨",
            "title": "Έκτακτη Ανακοίνωση",
            "message": signals["active_crisis"].get("message", "Δες λεπτομέρειες.")[:120],
            "color": "#D32F2F",
            "actions": [
                {"label": "📢 Λεπτομέρειες", "type": "internal", "value": "view_announcements"},
                {"label": "📞 199", "type": "url", "value": "tel:199"},
            ],
        })

    # ── TRAFFIC ──────────────────────────────────────────────────
    congestion = signals.get("traffic_congestion_pct", 0)
    if congestion > 70:
        cards.append({
            "id": "traffic_high",
            "priority": 90,
            "icon": "🚦",
            "title": "Έντονη Κυκλοφορία",
            "message": "Πολύ έντονη κίνηση στο κέντρο. Προτείνω εναλλακτικές:",
            "color": "#E53935",
            "actions": [
                {"label": "🚌 Λεωφορείο", "type": "url", "value": "https://www.astiko-irakleiou.gr/"},
                {"label": "🚕 Ταξί", "type": "url", "value": "tel:2810210102"},
                {"label": "🗺️ Χάρτης", "type": "internal", "value": "view_traffic_map"},
            ],
        })
    elif congestion > 50:
        cards.append({
            "id": "traffic_medium",
            "priority": 60,
            "icon": "🚙",
            "title": "Μέτρια Κυκλοφορία",
            "message": "Αρκετή κίνηση. Υπολόγισε +10 λεπτά στη διαδρομή σου.",
            "color": "#FB8C00",
            "actions": [
                {"label": "🗺️ Χάρτης", "type": "internal", "value": "view_traffic_map"},
                {"label": "🚌 Λεωφορείο", "type": "url", "value": "https://www.astiko-irakleiou.gr/"},
            ],
        })

    # ── HEAT ──────────────────────────────────────────────────────
    temp = signals.get("weather_temp")
    if temp is not None and temp > 35:
        cards.append({
            "id": "heat_wave",
            "priority": 85,
            "icon": "🌡️",
            "title": "Καύσωνας",
            "message": f"Πολύ ζέστη ({int(temp)}°C). Μείνε ασφαλής.",
            "color": "#E64A19",
            "actions": [
                {"label": "💧 Σημεία Νερού", "type": "internal", "value": "view_water_spots"},
                {"label": "🌳 Σκιαζόμενοι Χώροι", "type": "internal", "value": "view_shade_spots"},
            ],
        })

    # ── RAIN ──────────────────────────────────────────────────────
    if signals.get("weather_rain"):
        cards.append({
            "id": "weather_rain",
            "priority": 80,
            "icon": "🌧️",
            "title": "Βροχή",
            "message": "Έχει βροχή. Πρόσεξε λακκούβες και ολισθηρότητα.",
            "color": "#1976D2",
            "actions": [
                {"label": "⚠️ Αναφορά Λακκούβας", "type": "internal", "value": "report_pothole"},
                {"label": "🌦️ Πρόγνωση", "type": "url", "value": "https://www.meteo.gr/cf-el.cfm?city_id=8"},
            ],
        })

    # ── WIND ──────────────────────────────────────────────────────
    if signals.get("weather_strong_wind"):
        cards.append({
            "id": "strong_wind",
            "priority": 75,
            "icon": "💨",
            "title": "Ισχυροί Άνεμοι",
            "message": f"Άνεμοι {signals['weather_wind_kmh']} km/h. Πρόσεχε.",
            "color": "#455A64",
            "actions": [
                {"label": "⚠️ Αναφορά Κλαδιού", "type": "internal", "value": "report_fallen_tree"},
            ],
        })

    # ── CLOSED ROADS ──────────────────────────────────────────────
    closed_roads = signals.get("closed_roads_count", 0)
    if closed_roads > 0:
        cards.append({
            "id": "closed_roads",
            "priority": 70,
            "icon": "🚧",
            "title": f"{closed_roads} Κλειστοί Δρόμοι",
            "message": "Δες ποιοι δρόμοι είναι κλειστοί πριν ξεκινήσεις.",
            "color": "#F57C00",
            "actions": [
                {"label": "🗺️ Δες όλους", "type": "internal", "value": "view_closed_roads"},
            ],
        })

    # ── SERVICE HOURS ─────────────────────────────────────────────
    if hour >= 19 or hour < 7:
        cards.append({
            "id": "after_hours",
            "priority": 30,
            "icon": "🌙",
            "title": "Εκτός Ωραρίου",
            "message": "ΚΕΠ κλειστά. Οι online υπηρεσίες λειτουργούν 24/7.",
            "color": "#5E35B1",
            "actions": [
                {"label": "💻 Online Υπηρεσίες", "type": "internal", "value": "view_services"},
                {"label": "📞 Επικοινωνία", "type": "url", "value": "tel:2810399100"},
            ],
        })
    elif 7 <= hour < 9:
        cards.append({
            "id": "morning",
            "priority": 25,
            "icon": "☀️",
            "title": "Καλημέρα!",
            "message": "Οι υπηρεσίες ανοίγουν σε λίγο.",
            "color": "#FB8C00",
            "actions": [
                {"label": "🏛️ Υπηρεσίες", "type": "internal", "value": "view_services"},
            ],
        })

    # ── WEEKEND ───────────────────────────────────────────────────
    if now.weekday() >= 5:
        cards.append({
            "id": "weekend_events",
            "priority": 20,
            "icon": "🎉",
            "title": "Σαββατοκύριακο",
            "message": "Δες εκδηλώσεις και ανακοινώσεις!",
            "color": "#7B1FA2",
            "actions": [
                {"label": "📢 Ανακοινώσεις", "type": "internal", "value": "view_announcements"},
            ],
        })

    cards.sort(key=lambda c: -c["priority"])
    return cards[:3]


async def _gather_signals(user_id: Optional[str]) -> dict:
    from app.services.external_service import fetch_weather, fetch_traffic

    signals = {}

    # Live traffic (already cached by external_service)
    try:
        traffic = await fetch_traffic()
        signals["traffic_congestion_pct"] = traffic.get("congestion_percentage", 0)
        signals["traffic_level"] = traffic.get("congestion_level", "unknown")
    except Exception:
        signals["traffic_congestion_pct"] = 0

    # Live weather (already cached by external_service)
    try:
        weather = await fetch_weather()
        signals["weather_temp"] = weather.get("temperature")
        signals["weather_rain"] = weather.get("rain_mm", 0) > 0.1 or weather.get("rain_probability", 0) > 0.5
        wind_kmh = weather.get("wind_kmh", 0)
        signals["weather_strong_wind"] = wind_kmh > 50
        signals["weather_wind_kmh"] = int(wind_kmh)
        signals["weather_description"] = weather.get("description", "")
    except Exception:
        pass

    # Active closed roads
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        roads = (
            supabase.table("closed_roads")
            .select("id")
            .eq("status", "active")
            .or_(f"end_date.is.null,end_date.gt.{now_iso}")
            .execute()
        )
        signals["closed_roads_count"] = len(roads.data or [])
    except Exception:
        signals["closed_roads_count"] = 0

    # Latest urgent announcement
    try:
        urgent = (
            supabase.table("announcements")
            .select("id, title, content")
            .eq("is_urgent", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if urgent.data:
            signals["active_crisis"] = {
                "title": urgent.data[0]["title"],
                "message": (urgent.data[0].get("content") or "")[:200],
            }
    except Exception:
        signals["active_crisis"] = None

    return signals


@router.get("/smart-advice")
async def get_smart_advice(
    user_id: Optional[str] = Query(None),
    lat: float = Query(35.3387),
    lng: float = Query(25.1442),
):
    """Smart contextual advice cards for citizens. Hybrid rules-based with 30-min caching."""
    cache_key = _get_cache_key(user_id, lat, lng)

    if cache_key in _advice_cache:
        cached = _advice_cache[cache_key]
        if datetime.now(timezone.utc) - cached["timestamp"] < timedelta(minutes=CACHE_TTL_MINUTES):
            return cached["data"]

    try:
        signals = await _gather_signals(user_id)
        cards = _build_rule_based_advice(signals)

        result = {
            "cards": cards,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "signals_used": list(signals.keys()),
            "cache_ttl_minutes": CACHE_TTL_MINUTES,
        }

        _advice_cache[cache_key] = {
            "data": result,
            "timestamp": datetime.now(timezone.utc),
        }

        # Prevent unbounded growth
        if len(_advice_cache) > 500:
            oldest = sorted(_advice_cache, key=lambda k: _advice_cache[k]["timestamp"])[:100]
            for k in oldest:
                del _advice_cache[k]

        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "cards": [{
                "id": "fallback",
                "priority": 10,
                "icon": "👋",
                "title": "Καλώς ήρθες!",
                "message": "Δες τι μπορούμε να κάνουμε μαζί για τον Δήμο.",
                "color": "#1E3A5F",
                "action": None,
            }],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        }


@router.get("/smart-advice/clear-cache")
def clear_advice_cache():
    """Manual cache clear (admin debugging)."""
    count = len(_advice_cache)
    _advice_cache.clear()
    return {"cleared": count}
