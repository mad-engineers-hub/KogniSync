"""
FastAPI router for KogniSync Organizer XR Capability.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from app.services.xr.schemas import (
    XRScene,
    ARWayfindingCase,
    XRDeviceProfile,
    XRExperienceMatchRequest,
    XRExperienceMatchResponse,
)
from app.services.xr.service import xr_service

router = APIRouter(prefix="/api/v1/xr", tags=["XR Experiences"])


@router.get("/scenes", response_model=List[XRScene])
async def list_xr_scenes(
    entity_type: Optional[str] = Query(None, description="Filter by entity_type: transfer, hotel, poi, etc."),
    city: Optional[str] = Query(None, description="Filter by city name"),
):
    """List all available canonical XR scenes."""
    return xr_service.list_scenes(entity_type=entity_type, city_name=city)


@router.get("/scenes/{scene_id}", response_model=XRScene)
async def get_xr_scene(scene_id: str):
    """Retrieve a specific XR scene by its xrs_ ID."""
    scene = xr_service.get_scene_by_id(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail=f"XR scene '{scene_id}' not found.")
    return scene


@router.post("/match", response_model=XRExperienceMatchResponse)
async def match_journey_xr(request: XRExperienceMatchRequest):
    """
    Request-aware matching endpoint: returns relevant transfer and destination
    XR scenes for the given multimodal journey parameters.
    """
    return xr_service.match_journey_xr(request)


@router.get("/wayfinding/{scene_id}", response_model=List[ARWayfindingCase])
async def get_scene_wayfinding(
    scene_id: str,
    wayfinding_id: Optional[str] = Query(None, description="Optional specific wayfinding ID"),
):
    """Retrieve AR wayfinding routes for a transfer hub or scene."""
    wayfinding_cases = xr_service.get_wayfinding(scene_id=scene_id, wayfinding_id=wayfinding_id)
    return wayfinding_cases


@router.get("/device-profiles", response_model=List[XRDeviceProfile])
async def get_xr_device_profiles():
    """Retrieve supported device profiles and platform requirements."""
    return xr_service.get_device_profiles()
