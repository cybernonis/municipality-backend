import httpx
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Any

logger = logging.getLogger(__name__)

HER_LAT = 35.3387
HER_LNG = 25.1442

# {key: (data, expires_at)}
_cache: dict[str, tuple[Any, datetime]] = {}


def _cache_get(key: str) -> Optional[Any]:
    if key in _cache:
        data, expires = _cache[key]
        if datetime.utcnow() < expires:
            return data
        del _cache[key]
    return None


def _cache_set(key: str, data: Any, ttl_seconds: int):
    _cache[key] = (data, datetime.utcnow() + timedelta(seconds=ttl_seconds))


# ============================================
# 1. BEACH WATER QUALITY
# ============================================

HERAKLION_BEACHES = [
    {"id": "amoudara",    "name": "Αμμουδάρα",    "latitude": 35.3389, "longitude": 25.0589, "blue_flag": True},
    {"id": "karteros",    "name": "Καρτερός",      "latitude": 35.3294, "longitude": 25.2076, "blue_flag": True},
    {"id": "pagalochori", "name": "Παγκαλοχώρι",  "latitude": 35.3340, "longitude": 25.1900, "blue_flag": False},
    {"id": "amnisos",     "name": "Αμνισός",       "latitude": 35.3267, "longitude": 25.1980, "blue_flag": True},
]


async def get_beach_water_quality() -> dict:
    cached = _cache_get("beaches")
    if cached:
        return cached

    beaches_data = [
        {
            **beach,
            "quality": "excellent",
            "ecoli_cfu": 5,
            "enterococci_cfu": 8,
            "last_test": datetime.utcnow().date().isoformat(),
            "swimming_status": "ok",
            "temperature_c": 22.5,
            "source": "fallback",
        }
        for beach in HERAKLION_BEACHES
    ]

    result = {
        "beaches": beaches_data,
        "updated_at": datetime.utcnow().isoformat(),
        "next_update": "in 24 hours",
    }
    _cache_set("beaches", result, 86400)
    return result


# ============================================
# 2. WIND & MARINE (Open-Meteo Marine API)
# ============================================

async def _fetch_wind() -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": HER_LAT,
                    "longitude": HER_LNG,
                    "current": "wind_speed_10m,wind_direction_10m",
                },
            )
            data = resp.json()
            return {
                "speed": data["current"]["wind_speed_10m"],
                "direction": data["current"]["wind_direction_10m"],
            }
    except Exception:
        return {"speed": 10, "direction": 270}


async def get_marine_data() -> dict:
    cached = _cache_get("marine")
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://marine-api.open-meteo.com/v1/marine",
                params={
                    "latitude": HER_LAT,
                    "longitude": HER_LNG,
                    "current": "wave_height,wave_direction,wave_period,wind_wave_height,swell_wave_height",
                    "hourly": "wave_height,wave_period",
                    "timezone": "Europe/Athens",
                },
            )
            data = resp.json()

        wind = await _fetch_wind()
        current = data.get("current", {})
        wave_height = current.get("wave_height", 0) or 0

        if wave_height > 2.0:
            swim_status = "forbidden"
            alert_message = "Απαγόρευση κολύμβησης — επικίνδυνος κυματισμός"
        elif wave_height > 1.5:
            swim_status = "caution"
            alert_message = "Προσοχή — αυξημένος κυματισμός"
        else:
            swim_status = "ok"
            alert_message = None

        result = {
            "wave_height_m": wave_height,
            "wave_direction": current.get("wave_direction"),
            "wave_period_s": current.get("wave_period"),
            "swell_height_m": current.get("swell_wave_height"),
            "wind_speed_kmh": wind.get("speed", 0),
            "wind_direction": wind.get("direction", 0),
            "swim_status": swim_status,
            "alert_message": alert_message,
            "hourly_forecast": data.get("hourly", {}),
            "updated_at": datetime.utcnow().isoformat(),
        }
        _cache_set("marine", result, 1800)
        return result

    except Exception as e:
        logger.error(f"[MARINE] {e}")
        return {
            "wave_height_m": 0.5,
            "wind_speed_kmh": 12,
            "wind_direction": 270,
            "swim_status": "ok",
            "alert_message": None,
            "source": "fallback",
            "updated_at": datetime.utcnow().isoformat(),
        }


# ============================================
# 3. POLLEN & ALLERGENS (Open-Meteo Air Quality)
# ============================================

async def get_pollen_data() -> dict:
    cached = _cache_get("pollen")
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://air-quality-api.open-meteo.com/v1/air-quality",
                params={
                    "latitude": HER_LAT,
                    "longitude": HER_LNG,
                    "current": "alder_pollen,birch_pollen,grass_pollen,mugwort_pollen,olive_pollen,ragweed_pollen",
                    "timezone": "Europe/Athens",
                },
            )
            data = resp.json()

        current = data.get("current", {})
        olive = current.get("olive_pollen", 0) or 0
        grass = current.get("grass_pollen", 0) or 0

        alerts = []
        if olive > 50:
            alerts.append({
                "type": "olive_pollen_high",
                "severity": "high" if olive > 100 else "moderate",
                "message": f"Υψηλή συγκέντρωση γύρης ελιάς ({olive:.0f})",
                "advice": "Αλλεργικοί πολίτες, αποφύγετε εξωτερικές δραστηριότητες",
            })
        if grass > 50:
            alerts.append({
                "type": "grass_pollen_high",
                "severity": "moderate",
                "message": f"Υψηλή συγκέντρωση γύρης γρασιδιού ({grass:.0f})",
            })

        result = {
            "olive_pollen": olive,
            "grass_pollen": grass,
            "birch_pollen": current.get("birch_pollen"),
            "alder_pollen": current.get("alder_pollen"),
            "mugwort_pollen": current.get("mugwort_pollen"),
            "ragweed_pollen": current.get("ragweed_pollen"),
            "alerts": alerts,
            "updated_at": datetime.utcnow().isoformat(),
        }
        _cache_set("pollen", result, 3600)
        return result

    except Exception as e:
        logger.error(f"[POLLEN] {e}")
        return {
            "olive_pollen": 25,
            "grass_pollen": 15,
            "alerts": [],
            "source": "fallback",
            "updated_at": datetime.utcnow().isoformat(),
        }


# ============================================
# 4. UV INDEX & SOLAR (Open-Meteo)
# ============================================

async def get_uv_solar_data() -> dict:
    cached = _cache_get("uv")
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": HER_LAT,
                    "longitude": HER_LNG,
                    "current": "uv_index,uv_index_clear_sky",
                    "daily": "uv_index_max,sunrise,sunset",
                    "timezone": "Europe/Athens",
                },
            )
            data = resp.json()

        current = data.get("current", {})
        uv = current.get("uv_index", 0) or 0

        if uv >= 11:
            level, advice = "extreme", "Αποφύγετε εντελώς τον ήλιο 10:00-16:00"
        elif uv >= 8:
            level, advice = "very_high", "Χρειάζεται αντιηλιακή προστασία (SPF 50+)"
        elif uv >= 6:
            level, advice = "high", "Συνιστάται αντιηλιακό SPF 30+"
        elif uv >= 3:
            level, advice = "moderate", "Φοράτε καπέλο και γυαλιά"
        else:
            level, advice = "low", "Χωρίς ιδιαίτερη προστασία"

        daily = data.get("daily", {})
        result = {
            "uv_index_current": uv,
            "uv_index_clear_sky": current.get("uv_index_clear_sky"),
            "uv_max_today": (daily.get("uv_index_max") or [None])[0],
            "level": level,
            "advice": advice,
            "alert": uv > 8,
            "sunrise": (daily.get("sunrise") or [None])[0],
            "sunset": (daily.get("sunset") or [None])[0],
            "updated_at": datetime.utcnow().isoformat(),
        }
        _cache_set("uv", result, 1800)
        return result

    except Exception as e:
        logger.error(f"[UV] {e}")
        return {
            "uv_index_current": 5,
            "level": "moderate",
            "advice": "Φοράτε καπέλο",
            "alert": False,
            "source": "fallback",
            "updated_at": datetime.utcnow().isoformat(),
        }


# ============================================
# 5. CRUISE SHIP TRACKING (mock — MarineTraffic requires paid API)
# ============================================

_SHIPS_MOCK = [
    {
        "id": "msc-bellissima",
        "name": "MSC Bellissima",
        "type": "Cruise Ship",
        "flag": "Malta",
        "length_m": 315,
        "passengers": 4500,
        "status": "in_port",
        "arrival": "08:00",
        "departure": "18:00",
        "from": "Mykonos",
        "to": "Santorini",
        "latitude": 35.345,
        "longitude": 25.155,
    },
    {
        "id": "celebrity-edge",
        "name": "Celebrity Edge",
        "type": "Cruise Ship",
        "flag": "Bahamas",
        "length_m": 306,
        "passengers": 2900,
        "status": "approaching",
        "arrival": "14:00",
        "departure": "23:00",
        "from": "Athens",
        "to": "Rhodes",
        "latitude": 35.380,
        "longitude": 25.200,
    },
]


async def get_cruise_ships() -> dict:
    cached = _cache_get("ships")
    if cached:
        return cached

    result = {
        "ships": _SHIPS_MOCK,
        "total_today": len(_SHIPS_MOCK),
        "total_passengers": sum(s["passengers"] for s in _SHIPS_MOCK),
        "updated_at": datetime.utcnow().isoformat(),
        "source": "mock",
    }
    _cache_set("ships", result, 900)
    return result


# ============================================
# AUTO-REFRESH helpers (called from main.py startup)
# ============================================

async def refresh_all_external_data_v2():
    """Prime all v2 caches concurrently. Swallows individual failures."""
    await asyncio.gather(
        get_beach_water_quality(),
        get_marine_data(),
        get_pollen_data(),
        get_uv_solar_data(),
        get_cruise_ships(),
        return_exceptions=True,
    )
