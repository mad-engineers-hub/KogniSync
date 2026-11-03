"""
XR service package for KogniSync.
"""

from app.services.xr.schemas import (
    XRScene,
    XRSceneAsset,
    XRSceneHotspot,
    ARWayfindingCase,
    ARWayfindingStep,
    XRDeviceProfile,
    XRExperienceMatchRequest,
    XRExperienceMatchResponse,
)
from app.services.xr.service import XRService, xr_service

__all__ = [
    "XRScene",
    "XRSceneAsset",
    "XRSceneHotspot",
    "ARWayfindingCase",
    "ARWayfindingStep",
    "XRDeviceProfile",
    "XRExperienceMatchRequest",
    "XRExperienceMatchResponse",
    "XRService",
    "xr_service",
]
