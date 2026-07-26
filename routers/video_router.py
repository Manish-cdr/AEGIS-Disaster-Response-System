from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

from services.video_analyzer import VideoAnalyzer
from services.location_service import LocationService

router = APIRouter()
analyzer = VideoAnalyzer()
location_svc = LocationService()


class AnalysisRequest(BaseModel):
    file_id: str
    disaster_type: str = "general"
    sample_rate: int = 30
    user_lat: Optional[float] = None
    user_lng: Optional[float] = None
    user_address: Optional[str] = None


class AnalysisResponse(BaseModel):
    success: bool
    file_id: str
    analysis: dict
    location: Optional[dict] = None


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_video(request: AnalysisRequest):
    upload_dir = Path("uploads")
    file_path = None
    for ext in [".mp4", ".avi", ".mov", ".mkv", ".webm"]:
        candidate = upload_dir / f"{request.file_id}{ext}"
        if candidate.exists():
            file_path = candidate
            break

    if file_path is None:
        raise HTTPException(status_code=404, detail=f"File not found for ID: {request.file_id}")

    output_path = str(upload_dir / f"{request.file_id}_annotated.mp4")

    result = analyzer.analyze_video(
        video_path=str(file_path),
        disaster_type=request.disaster_type,
        sample_rate=request.sample_rate,
        output_path=output_path
    )

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    location_data = None

    # 1. Video GPS metadata
    metadata = analyzer.extract_metadata(str(file_path))
    if metadata.get("has_gps") and metadata.get("gps_location"):
        coords = location_svc.parse_iso6709(metadata["gps_location"])
        if coords:
            lat, lng = coords
            rev = location_svc.reverse_geocode(lat, lng)
            location_data = {
                "source": "video_metadata",
                "lat": lat, "lng": lng,
                "address": rev.get("formatted_address", ""),
                "maps_url": location_svc.get_maps_embed_url(lat, lng),
                "static_map_url": location_svc.get_static_map_url(lat, lng),
            }

    # 2. User coordinates
    if location_data is None and request.user_lat and request.user_lng:
        rev = location_svc.reverse_geocode(request.user_lat, request.user_lng)
        location_data = {
            "source": "user_coordinates",
            "lat": request.user_lat, "lng": request.user_lng,
            "address": rev.get("formatted_address", ""),
            "maps_url": location_svc.get_maps_embed_url(request.user_lat, request.user_lng),
            "static_map_url": location_svc.get_static_map_url(request.user_lat, request.user_lng),
        }

    # 3. User address → Geoapify geocode
    if location_data is None and request.user_address:
        geo = location_svc.geocode_address(request.user_address)
        if geo.get("success"):
            location_data = {
                "source": "user_address",
                "lat": geo["lat"], "lng": geo["lng"],
                "address": geo.get("formatted_address", request.user_address),
                "maps_url": location_svc.get_maps_embed_url(geo["lat"], geo["lng"]),
                "static_map_url": location_svc.get_static_map_url(geo["lat"], geo["lng"]),
                "geocode_note": geo.get("note", ""),
            }

    return AnalysisResponse(
        success=True, file_id=request.file_id,
        analysis=result, location=location_data
    )


@router.get("/metadata/{file_id}")
async def get_video_metadata(file_id: str):
    upload_dir = Path("uploads")
    file_path = None
    for ext in [".mp4", ".avi", ".mov", ".mkv", ".webm"]:
        candidate = upload_dir / f"{file_id}{ext}"
        if candidate.exists():
            file_path = candidate
            break
    if file_path is None:
        raise HTTPException(status_code=404, detail="File not found")
    return analyzer.extract_metadata(str(file_path))