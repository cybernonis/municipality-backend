from fastapi import APIRouter
from app.services.external_service import (
    fetch_weather,
    fetch_traffic,
    fetch_hazards,
    fetch_air_quality,
    fetch_earthquakes,
    fetch_all_external,
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
