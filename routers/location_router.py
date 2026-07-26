from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from services.location_service import LocationService

router = APIRouter()
location_svc = LocationService()


class GeocodeRequest(BaseModel):
    address: str


class ReverseGeocodeRequest(BaseModel):
    lat: float
    lng: float


@router.post("/geocode")
async def geocode(request: GeocodeRequest):
    """Convert address to coordinates."""
    result = location_svc.geocode_address(request.address)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail="Geocoding failed")
    return result


@router.post("/reverse-geocode")
async def reverse_geocode(request: ReverseGeocodeRequest):
    """Convert coordinates to address."""
    return location_svc.reverse_geocode(request.lat, request.lng)


@router.get("/sample-locations")
async def get_sample_locations():
    """Get sample disaster-prone locations for demo."""
    return {"locations": location_svc.SAMPLE_LOCATIONS}