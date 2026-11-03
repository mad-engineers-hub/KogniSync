import math
from app.services.maps.provider import MapsProvider
from app.services.maps.schemas import (
    RouteCoordinate,
    RouteEnrichRequestSegment,
    SegmentRouteGeometry,
)
from app.services.maps.polyline import encode_polyline


def haversine_distance_meters(
    lat1: float, lng1: float, lat2: float, lng2: float
) -> float:
    """Computes great-circle distance between two points in meters."""
    r = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def generate_curved_corridor(
    p1: RouteCoordinate,
    p2: RouteCoordinate,
    num_steps: int = 12,
    curvature_ratio: float = 0.08,
) -> list[RouteCoordinate]:
    """Generates an aesthetic curved waypoint corridor between two coordinates."""
    points: list[RouteCoordinate] = [p1]
    dx = p2.longitude - p1.longitude
    dy = p2.latitude - p1.latitude

    # Normal vector for lateral curvature
    norm_len = math.hypot(dx, dy)
    if norm_len < 1e-6:
        return [p1, p2]

    perp_x = -dy / norm_len
    perp_y = dx / norm_len

    for i in range(1, num_steps):
        t = i / float(num_steps)
        # Parabolic arc factor (0 at ends, 1 at midpoint)
        arc = 4.0 * t * (1.0 - t)
        offset = norm_len * curvature_ratio * arc

        lat = p1.latitude + t * dy + offset * perp_y
        lng = p1.longitude + t * dx + offset * perp_x
        points.append(RouteCoordinate(latitude=round(lat, 5), longitude=round(lng, 5)))

    points.append(p2)
    return points


def generate_road_waypoints(
    p1: RouteCoordinate,
    p2: RouteCoordinate,
    num_steps: int = 8,
) -> list[RouteCoordinate]:
    """Generates road-like intermediate waypoints with realistic micro-variations."""
    points: list[RouteCoordinate] = [p1]
    dx = p2.longitude - p1.longitude
    dy = p2.latitude - p1.latitude

    norm_len = math.hypot(dx, dy)
    if norm_len < 1e-6:
        return [p1, p2]

    perp_x = -dy / norm_len
    perp_y = dx / norm_len

    for i in range(1, num_steps):
        t = i / float(num_steps)
        # Small pseudo-random road swerves using deterministic sinusoidal wave
        swerve = math.sin(t * math.pi * 3.0) * (norm_len * 0.015)
        lat = p1.latitude + t * dy + swerve * perp_y
        lng = p1.longitude + t * dx + swerve * perp_x
        points.append(RouteCoordinate(latitude=round(lat, 5), longitude=round(lng, 5)))

    points.append(p2)
    return points


class FallbackMapsProvider(MapsProvider):
    """Deterministic geographic routing engine used when Google Routes is disabled or unavailable."""

    @property
    def name(self) -> str:
        return "deterministic_fallback"

    async def compute_segment_route(
        self, segment: RouteEnrichRequestSegment
    ) -> SegmentRouteGeometry:
        p1 = RouteCoordinate(latitude=segment.origin_lat, longitude=segment.origin_lng)
        p2 = RouteCoordinate(
            latitude=segment.destination_lat, longitude=segment.destination_lng
        )

        direct_meters = haversine_distance_meters(
            p1.latitude, p1.longitude, p2.latitude, p2.longitude
        )

        mode_lower = segment.mode.lower()

        # Generate realistic route coordinates based on transport mode
        if mode_lower == "flight":
            # High-altitude curved geodesic arc
            coords = generate_curved_corridor(p1, p2, num_steps=16, curvature_ratio=0.12)
            distance_meters = (
                int(segment.distance_km * 1000)
                if segment.distance_km
                else int(direct_meters * 1.05)
            )
        elif mode_lower in ("train", "rail"):
            # Rail corridor
            coords = generate_curved_corridor(p1, p2, num_steps=12, curvature_ratio=0.04)
            distance_meters = (
                int(segment.distance_km * 1000)
                if segment.distance_km
                else int(direct_meters * 1.15)
            )
        elif mode_lower in ("cab", "rapido", "auto", "bus", "car", "taxi"):
            # Road network with slight path curvature
            coords = generate_road_waypoints(p1, p2, num_steps=10)
            distance_meters = (
                int(segment.distance_km * 1000)
                if segment.distance_km
                else int(direct_meters * 1.25)
            )
        else:
            # Walk / local feeder
            coords = generate_road_waypoints(p1, p2, num_steps=5)
            distance_meters = (
                int(segment.distance_km * 1000)
                if segment.distance_km
                else int(direct_meters * 1.20)
            )

        # Duration preservation: prefer authoritative segment duration
        if segment.duration_minutes is not None and segment.duration_minutes > 0:
            duration_seconds = int(segment.duration_minutes * 60)
        else:
            # Mode-based average speed estimation (km/h)
            speeds = {
                "flight": 650.0,
                "train": 80.0,
                "bus": 40.0,
                "cab": 45.0,
                "auto": 35.0,
                "rapido": 35.0,
                "walk": 4.5,
            }
            avg_speed_kmh = speeds.get(mode_lower, 45.0)
            dist_km = distance_meters / 1000.0
            duration_seconds = max(60, int((dist_km / avg_speed_kmh) * 3600))

        encoded = encode_polyline(coords)

        return SegmentRouteGeometry(
            segment_id=segment.segment_id,
            mode=segment.mode,
            origin_title=segment.origin_name,
            origin_city=segment.origin_city,
            destination_title=segment.destination_name,
            destination_city=segment.destination_city,
            origin_coords=p1,
            destination_coords=p2,
            coordinates=coords,
            distance_meters=distance_meters,
            duration_seconds=duration_seconds,
            encoded_polyline=encoded,
            source=self.name,
            warnings=[],
        )
