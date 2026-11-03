"""
XR Service Layer for KogniSync.
Provides request-aware matching of XR scenes and AR wayfinding
to user journeys and canonical entities.
"""

from typing import List, Optional
import re
from app.services.xr.schemas import (
    XRScene,
    ARWayfindingCase,
    XRDeviceProfile,
    XRExperienceMatchRequest,
    XRExperienceMatchResponse,
)
from app.services.xr.data import CANONICAL_XR_SCENES

CITY_ALIASES = {
    "bangalore": ["bengaluru", "blr", "ksr", "majestic", "udayapalya"],
    "bengaluru": ["bangalore", "blr", "ksr", "majestic", "udayapalya"],
    "chennai": ["maa", "madras", "central", "egmore"],
    "udupi": ["manipal", "mangalore", "ixe", "udupi"],
    "mangalore": ["mangaluru", "ixe", "udupi"],
    "goa": ["madgaon", "margao", "panaji", "vasco", "dabolim", "mao"],
}


def _normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _matches_query(query: str, scene: XRScene) -> bool:
    q_norm = _normalize_text(query)
    if not q_norm:
        return False

    targets = [
        _normalize_text(scene.title),
        _normalize_text(scene.city_name),
        _normalize_text(scene.location_name),
    ]
    for tag in scene.tags:
        targets.append(_normalize_text(tag))

    # Check direct match
    if any(q_norm in t or t in q_norm for t in targets):
        return True

    # Check alias matches
    for key, aliases in CITY_ALIASES.items():
        if key in q_norm or any(a in q_norm for a in aliases):
            alias_set = set([key] + aliases)
            if any(any(a in t for a in alias_set) for t in targets):
                return True

    return False


class XRService:
    def __init__(self, scenes=None):
        self._scenes = scenes or CANONICAL_XR_SCENES

    def get_scene_by_id(self, scene_id: str) -> Optional[XRScene]:
        """Fetch a specific scene by its canonical xrs_ ID."""
        return self._scenes.get(scene_id)

    def list_scenes(
        self,
        entity_type: Optional[str] = None,
        city_name: Optional[str] = None
    ) -> List[XRScene]:
        """List all available XR scenes with optional filtering."""
        results = list(self._scenes.values())
        if entity_type:
            results = [s for s in results if s.entity_type == entity_type]
        if city_name:
            results = [s for s in results if _matches_query(city_name, s)]
        return results

    def match_journey_xr(self, req: XRExperienceMatchRequest) -> XRExperienceMatchResponse:
        """
        Request-aware matcher: finds all relevant transfer hub and destination
        XR scenes matching the user's specific journey.
        """
        matched_scenes: List[XRScene] = []
        seen_ids = set()

        def add_scene(s: XRScene):
            if s.scene_id not in seen_ids:
                seen_ids.add(s.scene_id)
                matched_scenes.append(s)

        # 1. Match by explicit hotel ID
        if req.hotel_id:
            for s in self._scenes.values():
                if s.entity_id == req.hotel_id or s.scene_id == f"xrs_{req.hotel_id}":
                    add_scene(s)

        # 2. Match by transfer hubs
        if req.transfer_hubs:
            for hub in req.transfer_hubs:
                for s in self._scenes.values():
                    if _matches_query(hub, s):
                        add_scene(s)

        # 3. Match by destination
        if req.destination:
            for s in self._scenes.values():
                if _matches_query(req.destination, s):
                    add_scene(s)

        # 4. Match by origin (first-mile interchanges)
        if req.origin:
            for s in self._scenes.values():
                if s.entity_type == "transfer" and _matches_query(req.origin, s):
                    add_scene(s)

        primary_scene = matched_scenes[0] if matched_scenes else None

        return XRExperienceMatchResponse(
            total_matches=len(matched_scenes),
            primary_scene=primary_scene,
            scenes=matched_scenes,
        )

    def get_wayfinding(
        self,
        scene_id: str,
        wayfinding_id: Optional[str] = None
    ) -> List[ARWayfindingCase]:
        """Get wayfinding navigation routes for a scene."""
        scene = self.get_scene_by_id(scene_id)
        if not scene:
            return []
        if wayfinding_id:
            return [w for w in scene.wayfinding_cases if w.wayfinding_id == wayfinding_id]
        return scene.wayfinding_cases

    def get_device_profiles(self, user_agent: Optional[str] = None) -> List[XRDeviceProfile]:
        """
        Returns organizer-defined device profiles (phone_ar, tablet_ar, headset_vr, desktop)
        with honest capability mapping.
        """
        profiles = [
            XRDeviceProfile(
                profile_id="xrd_webxr_immersive",
                device_class="headset_vr",
                platform="webxr",
                supported=False,
                notes="Requires WebXR immersive-vr/ar session support in browser.",
            ),
            XRDeviceProfile(
                profile_id="xrd_arcore_phone",
                device_class="phone_ar",
                platform="arcore",
                supported=False,
                notes="Supported on compatible Android handhelds via WebXR AR session.",
            ),
            XRDeviceProfile(
                profile_id="xrd_arkit_phone",
                device_class="phone_ar",
                platform="arkit",
                supported=False,
                notes="Supported on iOS devices via QuickLook USDZ integration.",
            ),
            XRDeviceProfile(
                profile_id="xrd_desktop_fallback",
                device_class="desktop",
                platform="desktop_fallback",
                supported=True,
                notes="Universal high-performance 360 canvas & gyro/mouse rotation.",
            ),
        ]
        return profiles


xr_service = XRService()
