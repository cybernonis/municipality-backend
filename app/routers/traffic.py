import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Tuneable thresholds ──────────────────────────────────────────
CACHE_TTL        = 120    # seconds between HERE flow refreshes
JAM_MEDIUM       = 4.0   # avg_jam_factor >= this → "medium"
JAM_HIGH         = 7.0   # avg_jam_factor >= this → "high"
RED_THRESHOLD    = 8.0   # jamFactor threshold for "red" hotspots (primary)
RED_FALLBACK     = 7.0   # fallback threshold when no segments reach RED_THRESHOLD
HOTSPOT_LIMIT    = 6     # top N hotspots returned after dedup
GEOCODE_CACHE_TTL = 86_400  # 24 h — street names don't change

HERE_FLOW_URL = (
    "https://data.traffic.hereapi.com/v7/flow"
    "?locationReferencing=shape"
    "&in=circle:35.3387,25.1442;r=5000"
    "&apiKey={api_key}"
)
HERE_REVGEO_URL = "https://revgeocode.search.hereapi.com/v1/revgeocode"

# ── In-memory caches ─────────────────────────────────────────────
# TODO: Replace with Redis-backed cache when running multiple Railway workers —
#       this dict is per-process, so parallel workers each maintain their own copy.
_cache: dict[str, Any] = {}
_geo_cache: dict[str, dict] = {}   # coord_key → {"name": str, "cached_at": datetime}
_lock = asyncio.Lock()


# ── Helpers ───────────────────────────────────────────────────────

def _congestion_level(avg: float) -> str:
    if avg >= JAM_HIGH:
        return "high"
    if avg >= JAM_MEDIUM:
        return "medium"
    return "low"


def _coord_key(lat: float, lng: float) -> str:
    return f"{lat:.4f},{lng:.4f}"


async def _reverse_geocode(client: httpx.AsyncClient, api_key: str, lat: float, lng: float) -> str:
    key = _coord_key(lat, lng)
    entry = _geo_cache.get(key)
    if entry:
        age = (datetime.now(timezone.utc) - entry["cached_at"]).total_seconds()
        if age < GEOCODE_CACHE_TTL:
            return entry["name"]

    name = "Άγνωστος δρόμος"
    try:
        resp = await client.get(
            HERE_REVGEO_URL,
            params={"at": f"{lat},{lng}", "lang": "el-GR", "apiKey": api_key},
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if items:
            name = (
                items[0].get("address", {}).get("street")
                or items[0].get("title")
                or "Άγνωστος δρόμος"
            )
    except Exception as e:
        logger.warning(f"[traffic/live] revgeocode failed ({lat},{lng}): {e}")

    _geo_cache[key] = {"name": name, "cached_at": datetime.now(timezone.utc)}
    return name


async def _resolve_street(client: httpx.AsyncClient, api_key: str, candidate: dict) -> str:
    # Prefer the flow description if HERE already gave us one
    if candidate["flow_description"]:
        return candidate["flow_description"]
    return await _reverse_geocode(client, api_key, candidate["lat"], candidate["lng"])


# ── Main fetch ────────────────────────────────────────────────────

async def _fetch_from_here(api_key: str) -> dict:
    # Phase 1 — fetch flow data
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(HERE_FLOW_URL.format(api_key=api_key))
        resp.raise_for_status()
    raw = resp.json()

    segments: list[dict] = []
    raw_candidates: list[dict] = []

    for result in raw.get("results", []):
        current_flow = result.get("currentFlow")
        if not current_flow:
            continue
        jam_factor = current_flow.get("jamFactor")
        if jam_factor is None:
            continue

        location = result.get("location", {})
        flow_description = (location.get("description") or "").strip()
        links = location.get("shape", {}).get("links", [])

        points = [
            {"lat": pt["lat"], "lng": pt["lng"]}
            for link in links
            for pt in link.get("points", [])
        ]
        if not points:
            continue

        mid = points[len(points) // 2]
        segments.append({"points": points, "jamFactor": round(jam_factor, 1)})
        raw_candidates.append({
            "flow_description": flow_description,
            "jamFactor": round(jam_factor, 1),
            "lat": mid["lat"],
            "lng": mid["lng"],
        })

    # Phase 2 — select red segments (primary threshold, then fallback)
    red = [c for c in raw_candidates if c["jamFactor"] >= RED_THRESHOLD]
    if not red:
        red = [c for c in raw_candidates if c["jamFactor"] >= RED_FALLBACK]

    # Phase 3 — parallel reverse geocode for red segments
    hotspots: list[dict] = []
    if red:
        async with httpx.AsyncClient(timeout=5.0) as geo_client:
            resolved = await asyncio.gather(
                *[_resolve_street(geo_client, api_key, c) for c in red],
                return_exceptions=True,
            )

        # Dedupe by street name — keep the segment with the highest jamFactor
        seen: dict[str, dict] = {}
        for candidate, name in zip(red, resolved):
            if isinstance(name, Exception):
                name = "Άγνωστος δρόμος"
            existing = seen.get(name)
            if not existing or candidate["jamFactor"] > existing["jamFactor"]:
                seen[name] = {
                    "description": name,
                    "jamFactor": candidate["jamFactor"],
                    "lat": round(candidate["lat"], 6),
                    "lng": round(candidate["lng"], 6),
                }

        hotspots = sorted(seen.values(), key=lambda h: h["jamFactor"], reverse=True)[:HOTSPOT_LIMIT]

    avg_jam = (
        round(sum(s["jamFactor"] for s in segments) / len(segments), 1)
        if segments else 0.0
    )

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "congestion_level": _congestion_level(avg_jam),
        "avg_jam_factor": avg_jam,
        "segments": segments,
        "hotspots": hotspots,
    }


async def _get_traffic_data(api_key: str) -> dict:
    async with _lock:
        now = datetime.now(timezone.utc)
        cached = _cache.get("traffic")

        if cached:
            age = (now - cached["fetched_at"]).total_seconds()
            if age < CACHE_TTL:
                return cached["data"]

        try:
            data = await _fetch_from_here(api_key)
            _cache["traffic"] = {"data": data, "fetched_at": now}
            logger.info(
                f"[traffic/live] Cache refreshed — {len(data['segments'])} segments, "
                f"{len(data['hotspots'])} hotspots"
            )
            return data
        except Exception as e:
            logger.error(f"[traffic/live] HERE API error: {e}")
            if cached:
                logger.warning("[traffic/live] Serving stale cache after fetch error")
                return cached["data"]
            raise


@router.get("/live")
async def get_traffic_live():
    api_key = settings.here_api_key
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Traffic service unavailable: HERE_API_KEY not configured",
        )
    try:
        return await _get_traffic_data(api_key)
    except Exception as e:
        logger.error(f"[traffic/live] Unhandled error: {e}")
        raise HTTPException(status_code=502, detail="Traffic data temporarily unavailable")
