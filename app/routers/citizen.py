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

    # ─── USER: PENDING REPORTS ──────────────────────────
    pending_reports = signals.get("user_pending_reports", 0)
    if pending_reports > 0:
        cards.append({
            "id": "pending_reports",
            "priority": 65,
            "icon": "📋",
            "title": f"Έχεις {pending_reports} εκκρεμή αναφορά"
                     + ("" if pending_reports == 1 else "ς"),
            "message": "Δες τη πρόοδό τους και την εκτιμώμενη επίλυση.",
            "color": "#0277BD",
            "actions": [
                {"label": "📋 Οι αναφορές μου", "type": "internal", "value": "view_my_reports"},
            ],
        })

    # ─── UPCOMING APPOINTMENT ───────────────────────────
    appt = signals.get("next_appointment")
    if appt:
        appt_date_str = appt.get("appointment_date", "")
        try:
            appt_date = datetime.fromisoformat(appt_date_str.replace("Z", "+00:00"))
            days_until = (appt_date.date() - datetime.now(timezone.utc).date()).days
            when = "σήμερα" if days_until == 0 else \
                   "αύριο" if days_until == 1 else \
                   f"σε {days_until} μέρες"
            cards.append({
                "id": "upcoming_appointment",
                "priority": 80,
                "icon": "📅",
                "title": f"Ραντεβού {when}",
                "message": f"{appt.get('service_type', 'Δημοτική υπηρεσία')} στις {appt_date.strftime('%H:%M')}",
                "color": "#00897B",
                "actions": [
                    {"label": "📅 Λεπτομέρειες", "type": "internal", "value": "view_appointments"},
                ],
            })
        except Exception:
            pass

    # ─── AIR QUALITY ────────────────────────────────────
    aqi = signals.get("air_quality_index")
    if aqi is not None:
        if aqi > 100:
            cards.append({
                "id": "air_quality_bad",
                "priority": 78,
                "icon": "🌫️",
                "title": "Χαμηλή Ποιότητα Αέρα",
                "message": f"Δείκτης AQI: {int(aqi)}. Αν είσαι ευαίσθητος, μείνε σε εσωτερικό χώρο.",
                "color": "#6A1B9A",
                "actions": [],
            })
        elif aqi < 50 and 9 <= hour <= 18:
            cards.append({
                "id": "air_quality_good",
                "priority": 15,
                "icon": "🌿",
                "title": "Καλή Ποιότητα Αέρα",
                "message": "Ιδανική μέρα για περπάτημα ή ποδήλατο στο κέντρο.",
                "color": "#388E3C",
                "actions": [],
            })

    # ─── UV INDEX ───────────────────────────────────────
    uv = signals.get("uv_index")
    if uv is not None and uv > 7 and 10 <= hour <= 16:
        cards.append({
            "id": "uv_high",
            "priority": 72,
            "icon": "☀️",
            "title": f"Υψηλός Δείκτης UV ({int(uv)})",
            "message": "Έντονη ηλιακή ακτινοβολία. Βάλε αντηλιακό, καπέλο και γυαλιά.",
            "color": "#F57F17",
            "actions": [],
        })

    # ─── SUNSET ─────────────────────────────────────────
    sunset_str = signals.get("sunset_today")
    if sunset_str:
        try:
            sunset_dt = datetime.fromisoformat(sunset_str.replace("Z", "+00:00"))
            now_utc = datetime.now(timezone.utc)
            sunset_with_tz = sunset_dt if sunset_dt.tzinfo else sunset_dt.replace(tzinfo=timezone.utc)
            minutes_until_sunset = (sunset_with_tz - now_utc).total_seconds() / 60
            if 30 <= minutes_until_sunset <= 90:
                cards.append({
                    "id": "sunset_soon",
                    "priority": 35,
                    "icon": "🌅",
                    "title": "Ηλιοβασίλεμα σε λίγο",
                    "message": f"Στις {sunset_dt.strftime('%H:%M')}. Ιδανικό για βόλτα στη παραλία!",
                    "color": "#EF6C00",
                    "actions": [],
                })
        except Exception:
            pass

    # ─── SEA / SWIMMING ─────────────────────────────────
    month = now.month
    temp = signals.get("weather_temp", 0)
    if 5 <= month <= 10 and temp and temp > 22 and 9 <= hour <= 19:
        sea_temps = {5: 19, 6: 22, 7: 25, 8: 26, 9: 25, 10: 22}
        sea_temp = sea_temps.get(month, 20)
        cards.append({
            "id": "swimming_good",
            "priority": 28,
            "icon": "🌊",
            "title": "Καλή Μέρα για Κολύμβι",
            "message": f"Θάλασσα ~{sea_temp}°C. Παραλίες κοντά: Αμμουδάρα, Καρτερός, Αμνισός.",
            "color": "#0288D1",
            "actions": [
                {"label": "🏖️ Αμμουδάρα", "type": "url", "value": "https://maps.google.com/?q=Ammoudara+Beach+Heraklion"},
                {"label": "🏖️ Καρτερός", "type": "url", "value": "https://maps.google.com/?q=Karteros+Beach"},
            ],
        })

    # ─── UPCOMING EVENTS ────────────────────────────────
    events_data = signals.get("upcoming_events", [])
    if events_data:
        event = events_data[0]
        cards.append({
            "id": "event_today",
            "priority": 40,
            "icon": "🎉",
            "title": "Εκδήλωση",
            "message": (event.get("title", "Δες λεπτομέρειες")[:80]),
            "color": "#7B1FA2",
            "actions": [
                {"label": "📢 Λεπτομέρειες", "type": "internal", "value": "view_announcements"},
            ],
        })

    # ─── PAYMENT REMINDER ───────────────────────────────
    day_of_month = now.day
    if 20 <= day_of_month <= 31:
        cards.append({
            "id": "month_end_payments",
            "priority": 22,
            "icon": "💰",
            "title": "Τέλος Μήνα",
            "message": "Έλεγξε αν έχεις εκκρεμείς πληρωμές δημοτικών τελών.",
            "color": "#00838F",
            "actions": [
                {"label": "💳 ePay", "type": "url", "value": "https://e-services.heraklion.gr/"},
            ],
        })

    cards.sort(key=lambda c: -c["priority"])
    return cards[:4]


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

    # ─── AIR QUALITY ────────────────────────────────
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            aq_response = await client.get(
                "https://air-quality-api.open-meteo.com/v1/air-quality",
                params={
                    "latitude": 35.3387,
                    "longitude": 25.1442,
                    "current": "european_aqi,uv_index,pm10,pm2_5",
                },
            )
            if aq_response.status_code == 200:
                aq_data = aq_response.json()
                current = aq_data.get("current", {})
                signals["air_quality_index"] = current.get("european_aqi")
                signals["uv_index"] = current.get("uv_index")
                signals["pm25"] = current.get("pm2_5")
                signals["pm10"] = current.get("pm10")
    except Exception as e:
        print(f"[smart-advice] Air quality fetch failed: {e}")

    # ─── SUNSET ─────────────────────────────────────
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            sun_response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": 35.3387,
                    "longitude": 25.1442,
                    "daily": "sunrise,sunset",
                    "timezone": "Europe/Athens",
                },
            )
            if sun_response.status_code == 200:
                sun_data = sun_response.json()
                daily = sun_data.get("daily", {})
                sunsets = daily.get("sunset", [])
                sunrises = daily.get("sunrise", [])
                if sunsets:
                    signals["sunset_today"] = sunsets[0]
                if sunrises:
                    signals["sunrise_today"] = sunrises[0]
    except Exception as e:
        print(f"[smart-advice] Sunset fetch failed: {e}")

    # ─── UPCOMING APPOINTMENTS ──────────────────────
    if user_id:
        try:
            from datetime import timedelta as _td
            future_threshold = (datetime.now(timezone.utc) + _td(days=7)).isoformat()
            appointments = (
                supabase.table("appointments")
                .select("id, appointment_date, status, service_type")
                .eq("user_id", user_id)
                .gte("appointment_date", datetime.now(timezone.utc).isoformat())
                .lte("appointment_date", future_threshold)
                .order("appointment_date", desc=False)
                .limit(1)
                .execute()
            )
            if appointments.data:
                signals["next_appointment"] = appointments.data[0]
        except Exception as e:
            print(f"[smart-advice] Appointments fetch failed: {e}")

    # ─── USER PENDING REPORTS ───────────────────────
    if user_id:
        try:
            pending = (
                supabase.table("reports")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .in_("status", ["submitted", "assigned", "in_progress"])
                .execute()
            )
            signals["user_pending_reports"] = pending.count or 0
        except Exception:
            signals["user_pending_reports"] = 0

    # ─── EVENT ANNOUNCEMENTS ────────────────────────
    try:
        today_iso = datetime.now(timezone.utc).date().isoformat()
        events = (
            supabase.table("announcements")
            .select("id, title, content, expires_at")
            .or_("category.eq.event,category.eq.cultural,category.eq.sports")
            .gte("expires_at", today_iso)
            .order("created_at", desc=True)
            .limit(2)
            .execute()
        )
        if events.data:
            signals["upcoming_events"] = events.data
    except Exception as e:
        print(f"[smart-advice] Events fetch failed: {e}")

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
