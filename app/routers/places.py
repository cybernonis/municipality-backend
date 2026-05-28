import os
import logging

import httpx
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()

GOOGLE_PLACES_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "AIzaSyDL0a90zxzfj6bLT41q_G2LedbAM9V2mhE")


@router.get("/autocomplete")
async def places_autocomplete(input: str):
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/autocomplete/json",
                params={
                    "input": input,
                    "key": GOOGLE_PLACES_KEY,
                    "language": "el",
                    "components": "country:gr",
                    "location": "35.3387,25.1442",
                    "radius": "50000",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"[places] autocomplete error: {e}")
            raise HTTPException(status_code=502, detail="Google Places request failed")


@router.get("/details")
async def places_details(place_id: str):
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/details/json",
                params={
                    "place_id": place_id,
                    "key": GOOGLE_PLACES_KEY,
                    "fields": "geometry,formatted_address",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"[places] details error: {e}")
            raise HTTPException(status_code=502, detail="Google Places request failed")
