import os
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query

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


@router.get("/search")
async def search_places(
    q: str = Query(..., min_length=2),
    country: str = Query("gr"),
    language: str = Query("el"),
    lat: float = Query(35.3387),
    lng: float = Query(25.1442),
    radius: int = Query(30000),
):
    """Search places με Google Places Autocomplete API (legacy)."""
    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": q,
        "key": GOOGLE_PLACES_KEY,
        "components": f"country:{country}",
        "language": language,
        "location": f"{lat},{lng}",
        "radius": radius,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            data = resp.json()

        status = data.get("status")
        if status == "OK":
            return {
                "status": "OK",
                "predictions": [
                    {
                        "description": p.get("description", ""),
                        "place_id": p.get("place_id", ""),
                        "main_text": p.get("structured_formatting", {}).get("main_text", ""),
                        "secondary_text": p.get("structured_formatting", {}).get("secondary_text", ""),
                    }
                    for p in data.get("predictions", [])
                ],
            }
        elif status == "ZERO_RESULTS":
            return {"status": "ZERO_RESULTS", "predictions": []}
        else:
            error_msg = data.get("error_message", status or "Unknown")
            logger.error(f"[places] search error: {error_msg}")
            raise HTTPException(status_code=400, detail=f"Places API error: {error_msg}")

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Places API timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[places] search exception: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/details/{place_id}")
async def place_details_by_id(
    place_id: str,
    language: str = Query("el"),
):
    """Get lat/lng για συγκεκριμένο place_id (legacy API, path param)."""
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "key": GOOGLE_PLACES_KEY,
        "fields": "geometry,formatted_address",
        "language": language,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            data = resp.json()

        status = data.get("status")
        if status == "OK":
            result = data.get("result", {})
            location = result.get("geometry", {}).get("location", {})
            return {
                "status": "OK",
                "lat": location.get("lat"),
                "lng": location.get("lng"),
                "address": result.get("formatted_address", ""),
            }
        else:
            error_msg = data.get("error_message", status or "Unknown")
            raise HTTPException(status_code=400, detail=f"Places API error: {error_msg}")

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Places API timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[places] details_by_id exception: {e}")
        raise HTTPException(status_code=500, detail=str(e))
