import asyncio

from fastapi import APIRouter
from app.services.external_service import (
    fetch_weather,
    fetch_traffic,
    fetch_hazards,
    fetch_air_quality,
    fetch_earthquakes,
    fetch_all_external,
)
from app.services.external_data import (
    get_beach_water_quality,
    get_marine_data,
    get_pollen_data,
    get_uv_solar_data,
    get_cruise_ships,
)

router = APIRouter()


@router.get("/weather")
async def get_weather():
    return await fetch_weather()


@router.get("/traffic")
async def get_traffic():
    return await fetch_traffic()


@router.get("/hazards")
async def get_hazards():
    return await fetch_hazards()


@router.get("/air-quality")
async def get_air_quality():
    return await fetch_air_quality()


@router.get("/earthquakes")
async def get_earthquakes():
    return await fetch_earthquakes()


@router.get("/all")
async def get_all_external():
    """Returns all external data sources in one call (concurrent fetching)."""
    return await fetch_all_external()


# ── Phase 10 v2 endpoints ────────────────────────────────────────────────────

@router.get("/beaches")
async def beaches():
    return await get_beach_water_quality()


@router.get("/marine")
async def marine():
    return await get_marine_data()


@router.get("/pollen")
async def pollen():
    return await get_pollen_data()


@router.get("/uv-solar")
async def uv_solar():
    return await get_uv_solar_data()


@router.get("/ships")
async def ships():
    return await get_cruise_ships()


@router.get("/summary")
async def external_summary():
    """Όλα τα v2 data sources σε ένα concurrent call."""
    beaches_data, marine_data, pollen_data, uv_data, ships_data = await asyncio.gather(
        get_beach_water_quality(),
        get_marine_data(),
        get_pollen_data(),
        get_uv_solar_data(),
        get_cruise_ships(),
    )

    alerts = []
    if marine_data.get("alert_message"):
        alerts.append({"type": "marine", "message": marine_data["alert_message"]})
    for p_alert in pollen_data.get("alerts", []):
        alerts.append({"type": "pollen", "message": p_alert["message"]})
    if uv_data.get("alert"):
        alerts.append({
            "type": "uv",
            "message": f"Δείκτης UV: {uv_data['uv_index_current']} ({uv_data['level']})",
        })

    return {
        "beaches": beaches_data,
        "marine": marine_data,
        "pollen": pollen_data,
        "uv": uv_data,
        "ships": ships_data,
        "alerts": alerts,
    }
