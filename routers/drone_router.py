from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from services.drone_service import DroneService

router = APIRouter()
drone_svc = DroneService()


class DispatchRequest(BaseModel):
    target_lat: float
    target_lng: float
    disaster_type: str = "general"
    preferred_drone_id: Optional[str] = None
    mission_id: Optional[str] = None


class RecallRequest(BaseModel):
    drone_id: str


@router.post("/dispatch")
async def dispatch_drone(request: DispatchRequest):
    """Dispatch a drone to the target location."""
    result = drone_svc.dispatch(
        target_lat=request.target_lat,
        target_lng=request.target_lng,
        disaster_type=request.disaster_type,
        preferred_drone_id=request.preferred_drone_id,
        mission_id=request.mission_id
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Dispatch failed"))
    return result


@router.get("/fleet")
async def get_fleet_status():
    """Get status of all drones in the fleet."""
    return {"fleet": drone_svc.get_fleet_status()}


@router.get("/status/{drone_id}")
async def get_drone_status(drone_id: str):
    """Get detailed status of a specific drone."""
    status = drone_svc.get_drone_status(drone_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Drone not found")
    return status


@router.post("/recall")
async def recall_drone(request: RecallRequest):
    """Recall a drone back to base."""
    result = drone_svc.recall_drone(request.drone_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Recall failed"))
    return result