"""
backend/app/services/disruption/matcher.py

Deterministic Route-to-Disruption Matching Engine (Milestones M3.7, M3.9, & M3.9.1).
Calculates spatial proximity, temporal validity, mode compatibility, and exact transit
identifier matches (route and stop codes) between disruption events and journey route segments.
Enforces exact and discrete token matching on route/stop IDs to prevent accidental substring collisions.
"""
from __future__ import annotations

import math
import re
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


def normalize_transit_identifier(val: str | None) -> str:
    """
    Normalizes a route or stop identifier deterministically:
    - Strips leading and trailing whitespace.
    - Converts to lowercase.
    - Normalizes internal multiple whitespaces to single spaces.
    - Preserves meaningful identifier characters including hyphens (-) and underscores (_).
    - Returns empty string for None or whitespace-only input.
    """
    if not val:
        return ""
    cleaned = val.strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def tokenize_transit_text(text: str | None) -> list[str]:
    """
    Splits descriptive transit text into discrete normalized tokens.
    Uses delimiters such as whitespace, parentheses, brackets, commas, semicolons, and forward slashes.
    CRITICAL: Preserves hyphens and underscores within tokens so that identifiers like
    '500-D', 'V-335E', 'BMTC_KBS', and 'hub-chennai-central' remain intact.
    """
    if not text:
        return []
    raw_tokens = re.split(r'[\s\(\)\[\]\{\},;:/\'"]+', text)
    tokens: list[str] = []
    for t in raw_tokens:
        norm = normalize_transit_identifier(t)
        if norm:
            tokens.append(norm)
    return tokens


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
    3. Exact canonical & tokenized Route and Stop ID matching (no broad substring matching).
    4. Route geometry proximity (exact polyline if available, hub coordinates fallback).
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
        # Prevents substring collisions: route '1' will NOT match 'Bus 15' or 'Route 50'
        # Arbitrary operator/provider descriptions are excluded from route matches
        if event.route_ids:
            seg_vehicle_norm = normalize_transit_identifier(segment.vehicle_number)
            seg_name_tokens = tokenize_transit_text(segment.vehicle_name)
            seg_name_norm = normalize_transit_identifier(segment.vehicle_name)

            for r_id in event.route_ids:
                r_norm = normalize_transit_identifier(r_id)
                if not r_norm:
                    continue

                # Exact canonical equality against segment vehicle_number
                if seg_vehicle_norm and r_norm == seg_vehicle_norm:
                    logger.debug(f"Matcher: exact route_id match '{r_id}' on vehicle_number")
                    return MatchedSegmentDisruption(
                        event=event,
                        match_type="route_id_exact",
                        min_distance_km=0.0,
                        confidence=0.98,
                        explanation=f"Exact route match on route '{r_id}': {event.title}",
                        correlation_metadata={
                            "matched_route_id": r_id,
                            "match_method": "route_id_exact",
                            "match_precision": "exact",
                            "confidence": 0.98,
                            "provenance": event.provenance,
                        },
                    )

                # Exact equality against full normalized vehicle_name
                if seg_name_norm and r_norm == seg_name_norm:
                    logger.debug(f"Matcher: exact route_id match '{r_id}' on full vehicle_name")
                    return MatchedSegmentDisruption(
                        event=event,
                        match_type="route_id_exact",
                        min_distance_km=0.0,
                        confidence=0.98,
                        explanation=f"Exact route match on route '{r_id}': {event.title}",
                        correlation_metadata={
                            "matched_route_id": r_id,
                            "match_method": "route_id_exact",
                            "match_precision": "exact",
                            "confidence": 0.98,
                            "provenance": event.provenance,
                        },
                    )

                # Discrete token equality against vehicle_name tokens (e.g. '500-D' in 'Vajra Bus (Route 500-D)')
                if r_norm in seg_name_tokens:
                    logger.debug(f"Matcher: tokenized route_id match '{r_id}' in vehicle_name tokens")
                    return MatchedSegmentDisruption(
                        event=event,
                        match_type="route_id_exact",
                        min_distance_km=0.0,
                        confidence=0.96,
                        explanation=f"Exact route match on route '{r_id}': {event.title}",
                        correlation_metadata={
                            "matched_route_id": r_id,
                            "match_method": "route_id_token",
                            "match_precision": "token",
                            "confidence": 0.96,
                            "provenance": event.provenance,
                        },
                    )

        # 2B. Direct Stop ID / Transit Station Matching
        # Prevents substring collisions: stop '12' will NOT match 'Platform 120'
        if event.stop_ids:
            orig_code = normalize_transit_identifier(getattr(segment.origin, "code", None))
            orig_id = normalize_transit_identifier(getattr(segment.origin, "id", None))
            orig_hub = normalize_transit_identifier(getattr(segment.origin, "hub_id", None))
            orig_name_norm = normalize_transit_identifier(segment.origin.name)
            orig_tokens = tokenize_transit_text(segment.origin.name)

            dest_code = normalize_transit_identifier(getattr(segment.destination, "code", None))
            dest_id = normalize_transit_identifier(getattr(segment.destination, "id", None))
            dest_hub = normalize_transit_identifier(getattr(segment.destination, "hub_id", None))
            dest_name_norm = normalize_transit_identifier(segment.destination.name)
            dest_tokens = tokenize_transit_text(segment.destination.name)

            for s_id in event.stop_ids:
                s_norm = normalize_transit_identifier(s_id)
                if not s_norm:
                    continue

                # 1. Exact canonical stop equality on origin station identifiers
                if s_norm in (orig_code, orig_id, orig_hub) or s_norm == orig_name_norm:
                    logger.debug(f"Matcher: exact stop_id match '{s_id}' on origin station")
                    return MatchedSegmentDisruption(
                        event=event,
                        match_type="stop_id_exact",
                        min_distance_km=0.0,
                        confidence=0.95,
                        explanation=f"Direct transit stop match at {segment.origin.name} ({s_id}): {event.title}",
                        correlation_metadata={
                            "matched_stop_id": s_id,
                            "match_method": "stop_id_exact",
                            "match_precision": "exact",
                            "confidence": 0.95,
                            "provenance": event.provenance,
                        },
                    )

                # 2. Exact canonical stop equality on destination station identifiers
                if s_norm in (dest_code, dest_id, dest_hub) or s_norm == dest_name_norm:
                    logger.debug(f"Matcher: exact stop_id match '{s_id}' on destination station")
                    return MatchedSegmentDisruption(
                        event=event,
                        match_type="stop_id_exact",
                        min_distance_km=0.0,
                        confidence=0.95,
                        explanation=f"Direct transit stop match at {segment.destination.name} ({s_id}): {event.title}",
                        correlation_metadata={
                            "matched_stop_id": s_id,
                            "match_method": "stop_id_exact",
                            "match_precision": "exact",
                            "confidence": 0.95,
                            "provenance": event.provenance,
                        },
                    )

                # 3. Discrete token equality against station name tokens
                if s_norm in orig_tokens:
                    logger.debug(f"Matcher: tokenized stop_id match '{s_id}' in origin station tokens")
                    return MatchedSegmentDisruption(
                        event=event,
                        match_type="stop_id_exact",
                        min_distance_km=0.0,
                        confidence=0.92,
                        explanation=f"Direct transit stop match at {segment.origin.name} ({s_id}): {event.title}",
                        correlation_metadata={
                            "matched_stop_id": s_id,
                            "match_method": "stop_id_token",
                            "match_precision": "token",
                            "confidence": 0.92,
                            "provenance": event.provenance,
                        },
                    )

                if s_norm in dest_tokens:
                    logger.debug(f"Matcher: tokenized stop_id match '{s_id}' in destination station tokens")
                    return MatchedSegmentDisruption(
                        event=event,
                        match_type="stop_id_exact",
                        min_distance_km=0.0,
                        confidence=0.92,
                        explanation=f"Direct transit stop match at {segment.destination.name} ({s_id}): {event.title}",
                        correlation_metadata={
                            "matched_stop_id": s_id,
                            "match_method": "stop_id_token",
                            "match_precision": "token",
                            "confidence": 0.92,
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
                            if min_dist <= 0.1:
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
