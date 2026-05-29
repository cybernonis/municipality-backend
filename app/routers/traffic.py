import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Tuneable thresholds ──────────────────────────────────────────
CACHE_TTL       = 120   # seconds between HERE refreshes
JAM_MEDIUM      = 4.0   # avg_jam_factor threshold for "medium"
JAM_HIGH        = 7.0   # avg_jam_factor threshold for "high"
HOTSPOT_MIN_JAM = 4.0   # minimum jamFactor to qualify as a hotspot
HOTSPOT_LIMIT   = 5     # maximum hotspots returned

HERE_FLOW_URL = (
    "https://data.traffic.hereapi.com/v7/flow"
    "?locationReferencing=shape"
    "&in=circle:35.3387,25.1442;r=5000"
    "&apiKey={api_key}"
)

# ── In-memory cache ──────────────────────────────────────────────
# TODO: Replace with Redis-backed cache when running multiple Railway workers —
#       this dict is per-process, so parallel workers each maintain their own copy.
_cache: dict[str, Any] = {}
_lock = asyncio.Lock()


def _congestion_level(avg: float) -> str:
    if avg >= JAM_HIGH:
        return "high"
    if avg >= JAM_MEDIUM:
        return "medium"
    return "low"


async def _fetch_from_here(api_key: str) -> dict:
    url = HERE_FLOW_URL.format(api_key=api_key)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    raw = resp.json()

    segments = []
    hotspot_candidates = []

    for result in raw.get("results", []):
        current_flow = result.get("currentFlow")
        if not current_flow:
            continue
        jam_factor = current_flow.get("jamFactor")
        if jam_factor is None:
            continue

        location = result.get("location", {})
        description = location.get("description") or "Άγνωστος δρόμος"
        links = location.get("shape", {}).get("links", [])

        points = [
            {"lat": pt["lat"], "lng": pt["lng"]}
            for link in links
            for pt in link.get("points", [])
        ]
        if not points:
            continue

        segments.append({"points": points, "jamFactor": round(jam_factor, 1)})

        if jam_factor >= HOTSPOT_MIN_JAM:
            hotspot_candidates.append({
                "description": description,
                "jamFactor": round(jam_factor, 1),
            })

    avg_jam = (
        round(sum(s["jamFactor"] for s in segments) / len(segments), 1)
        if segments else 0.0
    )
    hotspots = sorted(hotspot_candidates, key=lambda h: h["jamFactor"], reverse=True)[:HOTSPOT_LIMIT]

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
            logger.info(f"[traffic/live] Cache refreshed — {len(data['segments'])} segments")
            return data
        except Exception as e:
            logger.error(f"[traffic/live] HERE API error: {e}")
            if cached:
                logger.warning("[traffic/live] Serving stale cache after fetch error")
                return cached["data"]
            raise


@router.get("/live")
async def get_traffic_live():
    api_key = os.getenv("HERE_API_KEY")
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
