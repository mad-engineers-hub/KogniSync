"""
Pydantic schemas and models for KogniSync Organizer XR Capability.
Strictly conforms to organizer enums in BookingInventory/data/enums.json.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


# Organizer-defined canonical XR enums (enums.json / validate_conformance.py)
XRSceneType = Literal["panorama_360", "model_3d", "photogrammetry", "video_360"]
XRAssetFormat = Literal["jpg_equirect", "gltf", "glb", "usdz", "ktx2", "mp4"]
XRPlatform = Literal["webxr", "arcore", "arkit", "desktop_fallback"]
DeviceClass = Literal["phone_ar", "tablet_ar", "headset_vr", "desktop"]
XREntityType = Literal["transfer", "hotel", "poi", "flight", "xr_scene"]


class XRSceneHotspot(BaseModel):
    """Interactive hotspot positioned inside a 360/3D scene."""
    hotspot_id: str = Field(..., description="Unique ID prefixed with xrh_")
    scene_id: str = Field(..., description="Parent scene ID prefixed with xrs_")
    title: str = Field(..., description="Visible label")
    description: Optional[str] = None
    category: Literal[
        "transfer", "platform", "bus_bay", "cab_pickup", "hotel_amenity", "exit", "info"
    ] = "info"
    # Spherical coordinates for 360 (degrees): yaw 0..360, pitch -90..+90
    yaw: float = Field(default=0.0, ge=0.0, le=360.0)
    pitch: float = Field(default=0.0, ge=-90.0, le=90.0)
    action: Literal["navigate", "info", "wayfinding", "booking"] = "info"
    target_id: Optional[str] = None


class XRSceneAsset(BaseModel):
    """Media asset supporting the XR scene (equirectangular image, GLTF, etc.)."""
    asset_id: str = Field(..., description="Unique ID prefixed with xra_")
    format: XRAssetFormat
    uri: str
    mime_type: str = "image/jpeg"
    file_size_bytes: int = 0
    description: Optional[str] = None


class XRDeviceProfile(BaseModel):
    """Device capability profile conforming to organizer device_class & xr_platform."""
    profile_id: str = Field(..., description="Unique ID prefixed with xrd_")
    device_class: DeviceClass
    platform: XRPlatform
    supported: bool = True
    notes: Optional[str] = None


class ARWayfindingStep(BaseModel):
    """Step-by-step pedestrian navigation instruction for an intermodal interchange."""
    step_number: int
    instruction: str
    distance_meters: int
    turn_direction: Literal[
        "straight", "left", "right", "slight_left", "slight_right",
        "stairs_up", "stairs_down", "elevator", "arrival"
    ] = "straight"
    target_landmark: str


class ARWayfindingCase(BaseModel):
    """Wayfinding route between platforms, arrival gates, and transit connections."""
    wayfinding_id: str = Field(..., description="Unique ID prefixed with arw_")
    scene_id: str
    origin_title: str
    destination_title: str
    estimated_walking_minutes: int
    steps: List[ARWayfindingStep] = []


class XRScene(BaseModel):
    """Canonical XR Scene representation."""
    scene_id: str = Field(..., description="Unique ID prefixed with xrs_")
    title: str
    subtitle: str
    entity_type: XREntityType = "xr_scene"
    entity_id: Optional[str] = None
    city_id: Optional[str] = None
    city_name: str
    location_name: str
    scene_type: XRSceneType = "panorama_360"
    description: str
    assets: List[XRSceneAsset] = []
    hotspots: List[XRSceneHotspot] = []
    wayfinding_cases: List[ARWayfindingCase] = []
    supported_platforms: List[XRPlatform] = ["desktop_fallback", "webxr", "arcore", "arkit"]
    tags: List[str] = []


class XRExperienceMatchRequest(BaseModel):
    """Request to match relevant XR experiences to a planned multimodal journey."""
    origin: Optional[str] = None
    destination: Optional[str] = None
    transfer_hubs: Optional[List[str]] = None
    hotel_id: Optional[str] = None


class XRExperienceMatchResponse(BaseModel):
    """Response containing request-aware XR scenes for a specific journey."""
    total_matches: int
    primary_scene: Optional[XRScene] = None
    scenes: List[XRScene] = []
