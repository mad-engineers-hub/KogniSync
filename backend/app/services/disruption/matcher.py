"""
backend/app/services/disruption/matcher.py

Deterministic Route-to-Disruption Matching Engine (Milestone M3.7).
Calculates spatial proximity, temporal validity, and transport mode compatibility
between disruption events and journey route segments without external heavy GIS dependencies.
"""
import math
from datetime import datetime, timezone
from typing import Any, Sequence
from app.core.logging import logger
from app.services.disruption.schemas import DisruptionEvent
from app.services.journey.schemas import JourneySegmentSchema
from app.services.maps.polyline import decode_polyline

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Computes great-circle distance between two coordinates in kilometers."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_KM * c


def point_to_segment_distance_km(
    p_lat: float, p_lng: float,
    a_lat: float, a_lng: float,
    b_lat: float, b_lng: float,
) -> float:
    """
    Computes minimum distance from point P to line segment AB using equirectangular projection approximation.
    Sufficiently accurate for local road distance checks (< 50 km).
    """
    # Convert lat/lng deltas to local cartesian coordinates (km)
    mid_lat_rad = math.radians((a_lat + b_lat) / 2.0)
    cos_lat = math.cos(mid_lat_rad)

    ax = a_lng * 111.320 * cos_lat
    ay = a_lat * 110.574
    bx = b_lng * 111.320 * cos_lat
    by = b_lat * 110.574
    px = p_lng * 111.320 * cos_lat
    py = p_lat * 110.574

    dx = bx - ax
    dy = by - ay
    line_len_sq = dx * dx + dy * dy

    if line_len_sq == 0:
        return math.hypot(px - ax, py - ay)

    # Project P onto line segment AB, clamping to [0, 1]
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / line_len_sq))
    proj_x = ax + t * dx
    proj_y = ay + t * dy

    return math.hypot(px - proj_x, py - proj_y)


class MatchedSegmentDisruption:
    def __init__(
        self,
        event: DisruptionEvent,
        match_type: str,
        min_distance_km: float,
        explanation: str,
        confidence: float | None = None,
        correlation_metadata: dict[str, Any] | None = None,
    ):
        self.event = event
        self.match_type = match_type
        self.min_distance_km = min_distance_km
        self.explanation = explanation
        self.confidence = confidence if confidence is not None else getattr(event, "confidence", 1.0)
        self.correlation_metadata = correlation_metadata


class RouteDisruptionMatcher:
    """
    Matches disruption events against journey segments based on:
    1. Mode compatibility.
    2. Temporal overlap / active status.
    3. Route geometry proximity (exact polyline if available, hub coordinates fallback).
    """

    def __init__(
        self,
        road_tolerance_km: float = 2.0,
        hub_tolerance_km: float = 6.0,
    ):
        self.road_tolerance_km = road_tolerance_km
        self.hub_tolerance_km = hub_tolerance_km

    def is_temporally_valid(
        self, event: DisruptionEvent, segment: JourneySegmentSchema
    ) -> bool:
        """Checks if event overlaps the journey segment's execution window."""
        if event.status == "resolved":
            return False

        # If validity bounds are missing, assume active
        if not event.valid_until and not event.valid_from:
            return True

        now = datetime.now(timezone.utc)

        # 1. Check expiration against current wall-clock time
        if event.valid_until:
            try:
                valid_until_dt = datetime.fromisoformat(event.valid_until.replace("Z", "+00:00"))
                if valid_until_dt < now:
                    return False
                # If segment departure is known and occurs after event expiration, no conflict
                if segment.departure_time:
                    seg_dep_dt = datetime.fromisoformat(segment.departure_time.replace("Z", "+00:00"))
                    if valid_until_dt < seg_dep_dt:
                        return False
            except Exception:
                pass

        # 2. Check future scheduled events against segment arrival
        if event.valid_from:
            try:
                valid_from_dt = datetime.fromisoformat(event.valid_from.replace("Z", "+00:00"))
                if segment.arrival_time:
                    seg_arr_dt = datetime.fromisoformat(segment.arrival_time.replace("Z", "+00:00"))
                    if valid_from_dt > seg_arr_dt:
                        # Event has not started yet during this leg
                        return False
            except Exception:
                pass

        return True

    def match_event_to_segment(
        self, event: DisruptionEvent, segment: JourneySegmentSchema
    ) -> MatchedSegmentDisruption | None:
        """Determines if a disruption event affects a specific journey segment."""
        # 1. Transport Mode Compatibility Guard
        if segment.mode not in event.affected_modes:
            return None

        # 2. Temporal Validity Guard
        if not self.is_temporally_valid(event, segment):
            return None

        # 2A. Direct Route ID Matching (GTFS-RT route descriptor or alert informed entity)
        if event.route_ids:
            seg_vehicle = (segment.vehicle_number or "").lower().strip()
            seg_name = (segment.vehicle_name or "").lower().strip()
            seg_provider = (segment.provider or "").lower().strip()
            for r_id in event.route_ids:
                r_clean = r_id.lower().strip()
                if (
                    r_clean in seg_vehicle
                    or r_clean in seg_name
                    or r_clean in seg_provider
                    or seg_vehicle == r_clean
                ):
                    return MatchedSegmentDisruption(
                        event=event,
                        match_type="route_id_exact",
                        min_distance_km=0.0,
                        confidence=0.98,
                        explanation=f"Exact route match on route '{r_id}': {event.title}",
                        correlation_metadata={
                            "matched_route_id": r_id,
                            "match_method": "route_id_exact",
                            "confidence": 0.98,
                            "provenance": event.provenance,
                        },
                    )

        # 2B. Direct Stop ID / Transit Station Matching
        if event.stop_ids:
            orig_hub = (getattr(segment.origin, "hub_id", None) or getattr(segment.origin, "id", None) or getattr(segment.origin, "code", None) or "").lower().strip()
            dest_hub = (getattr(segment.destination, "hub_id", None) or getattr(segment.destination, "id", None) or getattr(segment.destination, "code", None) or "").lower().strip()
            orig_name = (segment.origin.name or "").lower().strip()
            dest_name = (segment.destination.name or "").lower().strip()
            for s_id in event.stop_ids:
                s_clean = s_id.lower().strip()
                if s_clean in (orig_hub, dest_hub) or s_clean in orig_name or s_clean in dest_name:
                    matched_station = (
                        segment.origin.name
                        if (s_clean in orig_hub or s_clean in orig_name)
                        else segment.destination.name
                    )
                    return MatchedSegmentDisruption(
                        event=event,
                        match_type="stop_id_exact",
                        min_distance_km=0.0,
                        confidence=0.95,
                        explanation=f"Direct transit stop match at {matched_station} ({s_id}): {event.title}",
                        correlation_metadata={
                            "matched_stop_id": s_id,
                            "match_method": "stop_id_exact",
                            "confidence": 0.95,
                            "provenance": event.provenance,
                        },
                    )

        # 3. Spatial Matching
        event_point = event.point
        if not event_point and event.affected_locations:
            # Fall back to first affected location coordinate if available
            first_loc = event.affected_locations[0]
            if first_loc.coordinates:
                event_point = first_loc.coordinates

        if not event_point:
            # Check city-level or name match if no coordinates exist
            for loc in event.affected_locations:
                if (
                    loc.city.lower() in (segment.origin.city.lower(), segment.destination.city.lower())
                    or loc.name.lower() in (segment.origin.name.lower(), segment.destination.name.lower())
                ):
                    return MatchedSegmentDisruption(
                        event=event,
                        match_type="hub_approximate",
                        min_distance_km=0.0,
                        explanation=f"Approximate city match at {loc.city}: {event.title}",
                    )
            return None

        e_lat, e_lng = event_point.lat, event_point.lng
        effective_tolerance = max(self.road_tolerance_km, (event.radius_meters or 1000.0) / 1000.0)

        # 3A. Exact Geometry Matching (via encoded polyline)
        if segment.encoded_polyline:
            try:
                # Precision 6 for Valhalla, 5 for Google
                precision = 6 if segment.is_live_geometry else 5
                coords = decode_polyline(segment.encoded_polyline, precision=precision)
                if not coords and precision == 6:
                    coords = decode_polyline(segment.encoded_polyline, precision=5)

                if coords and len(coords) >= 2:
                    min_dist = float("inf")
                    # Sample every step or segment
                    step = 1 if len(coords) < 200 else 2
                    for i in range(0, len(coords) - 1, step):
                        c1 = coords[i]
                        c2 = coords[i + 1]
                        dist = point_to_segment_distance_km(
                            e_lat, e_lng,
                            c1.latitude, c1.longitude,
                            c2.latitude, c2.longitude,
                        )
                        if dist < min_dist:
                            min_dist = dist
                            if min_dist <= 0.1:  # extremely close, break early
                                break

                    if min_dist <= effective_tolerance:
                        return MatchedSegmentDisruption(
                            event=event,
                            match_type="exact_geometry",
                            min_distance_km=round(min_dist, 2),
                            explanation=(
                                f"Disruption intersects segment route within {min_dist:.1f} km "
                                f"({event.title})"
                            ),
                        )
            except Exception as geo_err:
                logger.debug(f"Polyline matching error: {geo_err}; falling back to hub coordinates.")

        # 3B. Hub / Corridor Proximity Matching (Endpoints)
        dist_orig = haversine_km(
            e_lat, e_lng,
            segment.origin.coordinates.lat, segment.origin.coordinates.lng,
        )
        dist_dest = haversine_km(
            e_lat, e_lng,
            segment.destination.coordinates.lat, segment.destination.coordinates.lng,
        )
        min_hub_dist = min(dist_orig, dist_dest)

        if min_hub_dist <= self.hub_tolerance_km:
            hub_name = segment.origin.name if dist_orig < dist_dest else segment.destination.name
            return MatchedSegmentDisruption(
                event=event,
                match_type="hub_approximate",
                min_distance_km=round(min_hub_dist, 2),
                explanation=(
                    f"Disruption within {min_hub_dist:.1f} km of {hub_name} ({event.title})"
                ),
            )

        # 3C. Direct corridor check between origin and destination
        corridor_dist = point_to_segment_distance_km(
            e_lat, e_lng,
            segment.origin.coordinates.lat, segment.origin.coordinates.lng,
            segment.destination.coordinates.lat, segment.destination.coordinates.lng,
        )
        if corridor_dist <= effective_tolerance:
            if segment.mode == "bus" and event.source != "gtfs_realtime":
                return MatchedSegmentDisruption(
                    event=event,
                    match_type="multimodal_corridor_correlation",
                    min_distance_km=round(corridor_dist, 2),
                    confidence=0.90,
                    explanation=(
                        f"Multimodal Corridor Correlation: Road disruption on transit route corridor within {corridor_dist:.1f} km "
                        f"({event.title})"
                    ),
                    correlation_metadata={
                        "corridor_road_event": event.id,
                        "transit_mode": segment.mode,
                        "transit_route": segment.vehicle_name,
                        "match_method": "multimodal_corridor_correlation",
                        "confidence": 0.90,
                        "provenance": event.provenance,
                    },
                )
            return MatchedSegmentDisruption(
                event=event,
                match_type="spatial_corridor",
                min_distance_km=round(corridor_dist, 2),
                explanation=(
                    f"Disruption lies along straight-line corridor between {segment.origin.name} "
                    f"and {segment.destination.name} within {corridor_dist:.1f} km"
                ),
            )

        return None

    def match_events_to_segments(
        self,
        events: Sequence[DisruptionEvent],
        segments: Sequence[JourneySegmentSchema],
    ) -> dict[str, list[MatchedSegmentDisruption]]:
        """
        Matches a collection of disruption events across all segments of a journey.
        Returns a dict mapping segment_id to list of unique matched disruptions.
        """
        results: dict[str, list[MatchedSegmentDisruption]] = {}

        for segment in segments:
            matched_for_segment: list[MatchedSegmentDisruption] = []
            seen_event_ids: set[str] = set()

            for event in events:
                if event.id in seen_event_ids:
                    continue
                match = self.match_event_to_segment(event, segment)
                if match:
                    seen_event_ids.add(event.id)
                    matched_for_segment.append(match)

            results[segment.segment_id] = matched_for_segment

        return results


route_disruption_matcher = RouteDisruptionMatcher()

