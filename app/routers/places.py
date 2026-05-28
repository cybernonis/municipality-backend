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
            resp = await client.post(
                "https://places.googleapis.com/v1/places:autocomplete",
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": GOOGLE_PLACES_KEY,
                },
                json={
                    "input": input,
                    "languageCode": "el",
                    "regionCode": "GR",
                    "locationBias": {
                        "circle": {
                            "center": {"latitude": 35.3387, "longitude": 25.1442},
                            "radius": 50000.0,
                        }
                    },
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            predictions = []
            for s in data.get("suggestions", []):
                p = s.get("placePrediction", {})
                predictions.append({
                    "description": p.get("text", {}).get("text", ""),
                    "place_id": p.get("placeId", ""),
                })
            return {"predictions": predictions, "status": "OK"}
        except httpx.HTTPError as e:
            logger.error(f"[places] autocomplete error: {e}")
            raise HTTPException(status_code=502, detail="Google Places request failed")


@router.get("/details")
async def place_details(place_id: str):
    try:
        url = f"https://places.googleapis.com/v1/places/{place_id}"
        headers = {
            "X-Goog-Api-Key": GOOGLE_PLACES_KEY,
            "X-Goog-FieldMask": "location,formattedAddress",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=10.0)
        data = resp.json()
        location = data.get("location", {})
        return {
            "result": {
                "geometry": {
                    "location": {
                        "lat": location.get("latitude"),
                        "lng": location.get("longitude"),
                    }
                },
                "formatted_address": data.get("formattedAddress", ""),
            },
            "status": "OK",
        }
    except Exception as e:
        logger.error(f"[places] details error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
