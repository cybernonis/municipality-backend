import httpx
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from math import radians, cos, sin, asin, sqrt
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

HERAKLION_LAT = 35.3387
HERAKLION_LON = 25.1442

OPENWEATHER_API_KEY = settings.openweather_api_key
TOMTOM_API_KEY = settings.tomtom_api_key

# In-memory cache: {key: {"data": ..., "expires_at": datetime}}
_cache: dict = {}


def _get_cached(key: str) -> Optional[dict]:
    entry = _cache.get(key)
    if entry and datetime.now(timezone.utc) < entry["expires_at"]:
        return entry["data"]
    return None


def _set_cached(key: str, data: dict, ttl_seconds: int):
    _cache[key] = {
        "data": data,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
    }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def _pm25_to_aqi(pm25: float) -> int:
    # US EPA simplified AQI breakpoints
    breakpoints = [
        (0.0, 12.0, 0, 50),
        (12.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 150.4, 151, 200),
        (150.5, 250.4, 201, 300),
    ]
    for c_low, c_high, i_low, i_high in breakpoints:
        if c_low <= pm25 <= c_high:
            return round(((i_high - i_low) / (c_high - c_low)) * (pm25 - c_low) + i_low)
    return 301


# ─────────────────────────────────────────────
# WEATHER — OpenWeatherMap (5-min cache)
# ─────────────────────────────────────────────
async def fetch_weather() -> dict:
    cached = _get_cached("weather")
    if cached:
        return cached

    fallback = {
        "temperature": 25.0,
        "feels_like": 27.0,
        "humidity": 60,
        "description": "Μη διαθέσιμο",
        "wind_speed": 3.0,
        "wind_kmh": 10.8,
        "rain_probability": 0.0,
        "rain_mm": 0.0,
        "alerts": [],
        "icon": "01d",
        "forecast_24h": [],
        "source": "fallback",
    }

    if not OPENWEATHER_API_KEY:
        logger.warning("OPENWEATHER_API_KEY not set — returning fallback weather")
        return fallback

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            current_resp, forecast_resp = await asyncio.gather(
                client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={
                        "lat": HERAKLION_LAT,
                        "lon": HERAKLION_LON,
                        "appid": OPENWEATHER_API_KEY,
                        "units": "metric",
                        "lang": "el",
                    },
                ),
                client.get(
                    "https://api.openweathermap.org/data/2.5/forecast",
                    params={
                        "lat": HERAKLION_LAT,
                        "lon": HERAKLION_LON,
                        "appid": OPENWEATHER_API_KEY,
                        "units": "metric",
                        "lang": "el",
                        "cnt": 8,
                    },
                ),
            )

        current = current_resp.json()
        forecast_raw = forecast_resp.json()

        forecast_24h = [
            {
                "time": item["dt_txt"],
                "temp": item["main"]["temp"],
                "rain_probability": item.get("pop", 0.0),
                "description": item["weather"][0]["description"] if item.get("weather") else "",
                "icon": item["weather"][0]["icon"] if item.get("weather") else "01d",
            }
            for item in forecast_raw.get("list", [])
        ]

        temp = current["main"]["temp"]
        wind_ms = current["wind"]["speed"]
        wind_kmh = round(wind_ms * 3.6, 1)
        rain_mm = current.get("rain", {}).get("1h", 0.0)
        rain_prob = forecast_24h[0]["rain_probability"] if forecast_24h else 0.0

        alerts = []
        if rain_mm > 30:
            alerts.append({"type": "flood", "message": "Κίνδυνος πλημμύρας — βροχόπτωση > 30mm"})
        if wind_kmh > 50:
            alerts.append({"type": "wind", "message": "Κίνδυνος πτώσης δέντρων — άνεμοι > 50 km/h"})
        if temp > 38:
            alerts.append({"type": "heat", "message": "Κίνδυνος υγείας — θερμοκρασία > 38°C"})
        if rain_prob > 0.5:
            alerts.append({"type": "rain", "message": "Πιθανή βροχόπτωση — κίνδυνος πλημμύρας"})

        result = {
            "temperature": temp,
            "feels_like": current["main"]["feels_like"],
            "humidity": current["main"]["humidity"],
            "description": current["weather"][0]["description"] if current.get("weather") else "Άγνωστο",
            "wind_speed": wind_ms,
            "wind_kmh": wind_kmh,
            "rain_probability": rain_prob,
            "rain_mm": rain_mm,
            "alerts": alerts,
            "icon": current["weather"][0]["icon"] if current.get("weather") else "01d",
            "forecast_24h": forecast_24h,
            "source": "openweathermap",
        }

        _set_cached("weather", result, 300)
        return result

    except Exception as e:
        logger.error(f"Weather API error: {e}")
        return fallback


# ─────────────────────────────────────────────
# TRAFFIC — TomTom (1-min cache)
# ─────────────────────────────────────────────
async def fetch_traffic() -> dict:
    cached = _get_cached("traffic")
    if cached:
        return cached

    fallback = {
        "congestion_level": "unknown",
        "congestion_percentage": 0,
        "incidents": [],
        "affected_roads": [],
        "source": "fallback",
    }

    if not TOMTOM_API_KEY:
        logger.warning("TOMTOM_API_KEY not set — returning fallback traffic")
        return fallback

    try:
        bbox = (
            f"{HERAKLION_LON - 0.1},{HERAKLION_LAT - 0.1},"
            f"{HERAKLION_LON + 0.1},{HERAKLION_LAT + 0.1}"
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.tomtom.com/traffic/services/5/incidentDetails",
                params={
                    "key": TOMTOM_API_KEY,
                    "bbox": bbox,
                    "fields": (
                        "{incidents{type,geometry{type,coordinates},"
                        "properties{iconCategory,magnitudeOfDelay,from,to,roadNumbers}}}"
                    ),
                    "language": "el-GR",
                    "t": "1111",
                    "timeValidityFilter": "present",
                },
            )
        data = resp.json()

        icon_to_type = {
            1: "accident", 2: "fog", 3: "dangerous_conditions", 4: "rain",
            5: "ice", 6: "jam", 7: "lane_closed", 8: "road_closed",
            9: "road_works", 10: "wind", 11: "flooding",
        }
        magnitude_to_severity = {0: "unknown", 1: "minor", 2: "moderate", 3: "major", 4: "critical"}

        incidents = []
        affected_roads = []

        for inc in data.get("incidents", []):
            props = inc.get("properties", {})
            geom = inc.get("geometry", {})
            coords = geom.get("coordinates", [[HERAKLION_LON, HERAKLION_LAT]])

            # Flatten nested coordinate arrays
            if coords and isinstance(coords[0], list):
                first = coords[0][0] if isinstance(coords[0][0], list) else coords[0]
                lat, lng = first[1], first[0]
            else:
                lat, lng = HERAKLION_LAT, HERAKLION_LON

            road = props.get("from", "") or (
                props["roadNumbers"][0] if props.get("roadNumbers") else ""
            )
            to_road = props.get("to", "")
            location_str = road + (f" → {to_road}" if to_road else "") or "Ηράκλειο"

            incidents.append({
                "type": icon_to_type.get(props.get("iconCategory", 0), "incident"),
                "location": location_str,
                "severity": magnitude_to_severity.get(props.get("magnitudeOfDelay", 0), "moderate"),
                "lat": lat,
                "lng": lng,
            })

            if road and road not in affected_roads:
                affected_roads.append(road)

        n = len(incidents)
        has_major = any(i["severity"] in ("major", "critical") for i in incidents)

        if n == 0:
            congestion_pct, congestion_level = 10, "low"
        elif n < 2:
            congestion_pct, congestion_level = 25, "low"
        elif n < 4:
            congestion_pct, congestion_level = 50, "moderate"
        else:
            congestion_pct, congestion_level = 75, "high"

        if has_major:
            congestion_pct = max(congestion_pct, 65)
            congestion_level = "high"

        result = {
            "congestion_level": congestion_level,
            "congestion_percentage": congestion_pct,
            "incidents": incidents,
            "affected_roads": affected_roads,
            "source": "tomtom",
        }

        _set_cached("traffic", result, 60)
        return result

    except Exception as e:
        logger.error(f"Traffic API error: {e}")
        return fallback


# ─────────────────────────────────────────────
# FIRE & HAZARDS — NASA FIRMS (15-min cache, no key)
# ─────────────────────────────────────────────
async def fetch_hazards() -> dict:
    cached = _get_cached("hazards")
    if cached:
        return cached

    fallback = {
        "fires": [],
        "nearby_fires": [],
        "flood_risk_areas": [],
        "auto_crisis": False,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": "fallback",
    }

    try:
        # NASA FIRMS bulk CSV for Europe — no API key required
        url = (
            "https://firms.modaps.eosdis.nasa.gov/data/active_fire/"
            "suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Europe_24h.csv"
        )
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, follow_redirects=True)
        text = resp.text

        fires = []
        lines = text.strip().split("\n")
        if len(lines) > 1:
            headers = [h.strip() for h in lines[0].split(",")]
            for line in lines[1:]:
                if not line.strip():
                    continue
                values = line.split(",")
                if len(values) < len(headers):
                    continue
                row = dict(zip(headers, values))
                try:
                    lat = float(row.get("latitude", 0))
                    lng = float(row.get("longitude", 0))
                    # Filter: Crete bounding box
                    if not (34.5 <= lat <= 36.5 and 23.5 <= lng <= 27.5):
                        continue

                    brightness = float(row.get("bright_ti4", row.get("brightness", 300)))
                    confidence_raw = row.get("confidence", "n").strip()
                    conf_map = {"l": 40, "n": 70, "h": 90}
                    confidence = conf_map.get(confidence_raw, 70)

                    acq_date = row.get("acq_date", "").strip()
                    acq_time = row.get("acq_time", "0000").strip().zfill(4)
                    detected_at = f"{acq_date}T{acq_time[:2]}:{acq_time[2:]}:00Z"

                    dist_km = _haversine_km(HERAKLION_LAT, HERAKLION_LON, lat, lng)
                    fires.append({
                        "lat": lat,
                        "lng": lng,
                        "confidence": confidence,
                        "brightness": brightness,
                        "detected_at": detected_at,
                        "distance_km": round(dist_km, 1),
                    })
                except (ValueError, KeyError):
                    continue

        nearby_fires = [f for f in fires if f["distance_km"] <= 50]

        result = {
            "fires": fires,
            "nearby_fires": nearby_fires,
            "flood_risk_areas": [],
            "auto_crisis": len(nearby_fires) > 0,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "source": "nasa_firms",
        }

        _set_cached("hazards", result, 900)
        return result

    except Exception as e:
        logger.error(f"Hazards/FIRMS API error: {e}")
        return fallback


# ─────────────────────────────────────────────
# AIR QUALITY — OpenAQ v2 (30-min cache, no key)
# ─────────────────────────────────────────────
async def fetch_air_quality() -> dict:
    cached = _get_cached("air_quality")
    if cached:
        return cached

    fallback = {
        "aqi": 45,
        "pm25": 10.0,
        "pm10": 20.0,
        "no2": 15.0,
        "o3": 60.0,
        "status": "Καλή",
        "color": "#00E400",
        "source": "fallback",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.openaq.org/v2/latest",
                params={
                    "coordinates": f"{HERAKLION_LAT},{HERAKLION_LON}",
                    "radius": 50000,
                    "limit": 10,
                    "order_by": "distance",
                    "sort": "asc",
                },
                headers={"Accept": "application/json"},
            )
        data = resp.json()

        pm25 = pm10 = no2 = o3 = None

        for location in data.get("results", []):
            for m in location.get("measurements", []):
                param = m.get("parameter", "")
                value = m.get("value", 0)
                if param == "pm25" and pm25 is None:
                    pm25 = round(value, 1)
                elif param == "pm10" and pm10 is None:
                    pm10 = round(value, 1)
                elif param == "no2" and no2 is None:
                    no2 = round(value, 1)
                elif param == "o3" and o3 is None:
                    o3 = round(value, 1)

        aqi = _pm25_to_aqi(pm25 or 10.0)

        if aqi <= 50:
            status, color = "Καλή", "#00E400"
        elif aqi <= 100:
            status, color = "Μέτρια", "#FFFF00"
        elif aqi <= 150:
            status, color = "Ανθυγιεινό για ευαίσθητες ομάδες", "#FF7E00"
        elif aqi <= 200:
            status, color = "Ανθυγιεινό", "#FF0000"
        else:
            status, color = "Πολύ ανθυγιεινό", "#8F3F97"

        result = {
            "aqi": aqi,
            "pm25": pm25 or 10.0,
            "pm10": pm10 or 20.0,
            "no2": no2 or 15.0,
            "o3": o3 or 60.0,
            "status": status,
            "color": color,
            "source": "openaq",
        }

        _set_cached("air_quality", result, 1800)
        return result

    except Exception as e:
        logger.error(f"Air quality API error: {e}")
        return fallback


# ─────────────────────────────────────────────
# EARTHQUAKES — USGS (30-min cache, no key)
# ─────────────────────────────────────────────
async def fetch_earthquakes() -> dict:
    cached = _get_cached("earthquakes")
    if cached:
        return cached

    fallback = {
        "earthquakes": [],
        "significant": [],
        "total": 0,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": "fallback",
    }

    try:
        start_time = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://earthquake.usgs.gov/fdsnws/event/1/query",
                params={
                    "format": "geojson",
                    "starttime": start_time,
                    "minlatitude": 33.5,
                    "maxlatitude": 37.0,
                    "minlongitude": 22.0,
                    "maxlongitude": 28.0,
                    "minmagnitude": 2.0,
                    "orderby": "time",
                },
            )
        data = resp.json()

        earthquakes = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            coords = feature.get("geometry", {}).get("coordinates", [HERAKLION_LON, HERAKLION_LAT, 10])

            lat, lng = coords[1], coords[0]
            depth_km = coords[2] if len(coords) > 2 else 10
            mag = props.get("mag", 0)
            time_ms = props.get("time", 0)
            time_str = (
                datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc).isoformat()
                if time_ms else ""
            )
            dist_km = _haversine_km(HERAKLION_LAT, HERAKLION_LON, lat, lng)

            earthquakes.append({
                "magnitude": mag,
                "depth_km": round(depth_km, 1),
                "lat": lat,
                "lng": lng,
                "time": time_str,
                "felt": props.get("felt") is not None,
                "place": props.get("place", "Κρήτη"),
                "distance_km": round(dist_km, 1),
            })

        significant = [e for e in earthquakes if e["magnitude"] >= 4.0]

        result = {
            "earthquakes": earthquakes,
            "significant": significant,
            "total": len(earthquakes),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "source": "usgs",
        }

        _set_cached("earthquakes", result, 1800)
        return result

    except Exception as e:
        logger.error(f"Earthquakes API error: {e}")
        return fallback


# ─────────────────────────────────────────────
# COMBINED — fetch everything concurrently
# ─────────────────────────────────────────────
async def fetch_all_external() -> dict:
    results = await asyncio.gather(
        fetch_weather(),
        fetch_traffic(),
        fetch_hazards(),
        fetch_air_quality(),
        fetch_earthquakes(),
        return_exceptions=True,
    )
    keys = ["weather", "traffic", "hazards", "air_quality", "earthquakes"]
    return {
        k: (v if isinstance(v, dict) else None)
        for k, v in zip(keys, results)
    }


# ─────────────────────────────────────────────
# THRESHOLD CHECK — returns alert messages
# ─────────────────────────────────────────────
async def check_thresholds() -> list[dict]:
    alerts = []
    try:
        weather = await fetch_weather()
        for a in weather.get("alerts", []):
            alerts.append({"source": "weather", **a})

        hazards = await fetch_hazards()
        if hazards.get("auto_crisis"):
            alerts.append({
                "source": "hazards",
                "type": "fire",
                "message": f"Ενεργή πυρκαγιά εντός 50km — {len(hazards['nearby_fires'])} εστίες",
            })

        earthquakes = await fetch_earthquakes()
        for eq in earthquakes.get("significant", []):
            alerts.append({
                "source": "earthquakes",
                "type": "earthquake",
                "message": f"Σεισμός {eq['magnitude']}R — {eq['place']} ({eq['distance_km']} km)",
            })

        aq = await fetch_air_quality()
        if aq.get("aqi", 0) > 100:
            alerts.append({
                "source": "air_quality",
                "type": "air",
                "message": f"Κακή ποιότητα αέρα — AQI {aq['aqi']}",
            })
    except Exception as e:
        logger.error(f"Threshold check error: {e}")

    return alerts
