"""
backend/tests/test_maps_geometry.py

Comprehensive tests for KogniSync Milestone M3.5:
Intelligent Map Visualization, Real Route Geometry & Navigation-Grade Journey Experience.
Verifies:
1. Polyline encoding/decoding with precision 5 (Google) and precision 6 (Valhalla).
2. GeoJSON LineString formatting with [longitude, latitude] coordinate ordering.
3. ValhallaMapsProvider road and pedestrian route geometry extraction.
4. Non-road mode segregation (train, flight, metro strictly use estimated corridors).
5. MapsService composite enrichment, provider health, and resilient error degradation.
"""
import pytest
import httpx
from app.services.maps.polyline import (
    encode_polyline,
    decode_polyline,
    polyline_to_geojson_coordinates,
    coordinates_to_geojson_linestring,
)
from app.services.maps.schemas import (
    RouteCoordinate,
    RouteEnrichRequest,
    RouteEnrichRequestSegment,
    SegmentRouteGeometry,
)
from app.services.maps.fallback import FallbackMapsProvider
from app.services.maps.valhalla import ValhallaMapsProvider
from app.services.maps.service import MapsService


# ============================================================================
# 1. POLYLINE ENCODING & PRECISION CONFORMANCE
# ============================================================================

def test_1_polyline_precision_5_and_6():
    """Verify polyline encoding/decoding at precision 5 (Google) and precision 6 (Valhalla)."""
    coords = [
        RouteCoordinate(latitude=12.971599, longitude=77.594563),
        RouteCoordinate(latitude=13.082680, longitude=80.270718),
    ]

    # Precision 5 (Google format, 1e5)
    poly5 = encode_polyline(coords, precision=5)
    assert isinstance(poly5, str) and len(poly5) > 0
    decoded5 = decode_polyline(poly5, precision=5)
    assert len(decoded5) == 2
    assert abs(decoded5[0].latitude - 12.9716) < 1e-4
    assert abs(decoded5[0].longitude - 77.5946) < 1e-4

    # Precision 6 (Valhalla format, 1e6)
    poly6 = encode_polyline(coords, precision=6)
    assert isinstance(poly6, str) and len(poly6) > 0
    decoded6 = decode_polyline(poly6, precision=6)
    assert len(decoded6) == 2
    assert abs(decoded6[0].latitude - 12.971599) < 1e-5
    assert abs(decoded6[0].longitude - 77.594563) < 1e-5


def test_2_geojson_linestring_coordinate_ordering():
    """Verify GeoJSON LineString coordinates strictly follow [longitude, latitude] order."""
    coords = [
        RouteCoordinate(latitude=12.9716, longitude=77.5946),
        RouteCoordinate(latitude=13.0827, longitude=80.2707),
    ]
    geojson = coordinates_to_geojson_linestring(coords)

    assert geojson["type"] == "LineString"
    assert len(geojson["coordinates"]) == 2

    # Coordinate 0: [lng, lat]
    assert geojson["coordinates"][0][0] == 77.5946  # Longitude first
    assert geojson["coordinates"][0][1] == 12.9716  # Latitude second

    # Coordinate 1: [lng, lat]
    assert geojson["coordinates"][1][0] == 80.2707
    assert geojson["coordinates"][1][1] == 13.0827


# ============================================================================
# 2. VALHALLA MAPS PROVIDER & ROAD GEOMETRY EXTRACTION
# ============================================================================

@pytest.mark.anyio
async def test_3_valhalla_maps_provider_road_geometry():
    """Verify ValhallaMapsProvider extracts polyline6 shape and converts to live GeoJSON."""
    test_coords = [
        (12.978, 77.572),
        (12.980, 77.590),
        (12.978, 77.640),
    ]
    valhalla_shape = encode_polyline(test_coords, precision=6)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/route"
        payload = request.read().decode("utf-8")
        assert '"costing":"auto"' in payload or '"costing": "auto"' in payload
        return httpx.Response(
            200,
            json={
                "trip": {
                    "summary": {"time": 1200.0, "length": 15.4},
                    "legs": [
                        {
                            "shape": valhalla_shape,
                            "summary": {"time": 1200.0, "length": 15.4},
                            "maneuvers": [
                                {"instruction": "Drive east on MG Road.", "length": 5.2, "time": 300},
                                {"instruction": "Turn right onto 100 Feet Road.", "length": 10.2, "time": 900},
                            ],
                        }
                    ],
                }
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = ValhallaMapsProvider(
        base_url="http://localhost:8002",
        enabled=True,
        http_client=mock_client,
    )

    seg = RouteEnrichRequestSegment(
        segment_id="seg-cab-01",
        mode="cab",
        origin_name="Majestic Station",
        origin_city="Bangalore",
        origin_lat=12.978,
        origin_lng=77.572,
        destination_name="Indiranagar Hub",
        destination_city="Bangalore",
        destination_lat=12.978,
        destination_lng=77.640,
        distance_km=15.4,
        duration_minutes=20,
    )

    geom = await provider.compute_segment_route(seg)
    assert isinstance(geom, SegmentRouteGeometry)
    assert geom.source == "valhalla_live"
    assert geom.is_live_geometry is True
    assert geom.distance_meters == 15400
    assert geom.duration_seconds == 1200
    assert geom.encoded_polyline == valhalla_shape
    assert geom.geojson_geometry is not None
    assert geom.geojson_geometry["type"] == "LineString"
    assert len(geom.geojson_geometry["coordinates"]) == 3
    # Check first point [lng, lat]
    assert abs(geom.geojson_geometry["coordinates"][0][0] - 77.572) < 1e-4
    assert abs(geom.geojson_geometry["coordinates"][0][1] - 12.978) < 1e-4
    assert len(geom.maneuvers) == 2


# ============================================================================
# 3. NON-ROAD MODE SEGREGATION (FLIGHT & TRAIN)
# ============================================================================

@pytest.mark.anyio
async def test_4_non_road_modes_corridor_segregation():
    """Verify non-road modes (train, flight) strictly use estimated corridors and are not labeled live."""
    provider = ValhallaMapsProvider(base_url="http://localhost:8002", enabled=True)

    # 1. Train segment
    train_seg = RouteEnrichRequestSegment(
        segment_id="seg-train-02",
        mode="train",
        origin_name="Chennai Central",
        origin_city="Chennai",
        origin_lat=13.0827,
        origin_lng=80.2707,
        destination_name="Bangalore City",
        destination_city="Bangalore",
        destination_lat=12.978,
        destination_lng=77.572,
        distance_km=360.0,
        duration_minutes=270,
    )
    train_geom = await provider.compute_segment_route(train_seg)
    assert train_geom.is_live_geometry is False
    assert "corridor" in train_geom.source
    assert "Estimated train corridor" in (train_geom.provenance_notes or "")
    assert train_geom.geojson_geometry is not None

    # 2. Flight segment
    flight_seg = RouteEnrichRequestSegment(
        segment_id="seg-flight-02",
        mode="flight",
        origin_name="Chennai Airport",
        origin_city="Chennai",
        origin_lat=12.9941,
        origin_lng=80.1709,
        destination_name="Mangalore Airport",
        destination_city="Mangalore",
        destination_lat=12.9613,
        destination_lng=74.8901,
        distance_km=580.0,
        duration_minutes=75,
    )
    flight_geom = await provider.compute_segment_route(flight_seg)
    assert flight_geom.is_live_geometry is False
    assert "flight" in flight_geom.source
    assert flight_geom.geojson_geometry is not None


# ============================================================================
# 4. RESILIENT FALLBACK ON VALHALLA OUTAGE
# ============================================================================

@pytest.mark.anyio
async def test_5_valhalla_outage_graceful_fallback():
    """Verify Valhalla connection error gracefully degrades to deterministic spatial engine."""
    def error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused by localhost:8002")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(error_handler))
    provider = ValhallaMapsProvider(
        base_url="http://localhost:8002",
        enabled=True,
        http_client=mock_client,
    )

    seg = RouteEnrichRequestSegment(
        segment_id="seg-cab-fail",
        mode="cab",
        origin_name="Origin Point",
        origin_city="Bangalore",
        origin_lat=12.978,
        origin_lng=77.572,
        destination_name="Destination Point",
        destination_city="Bangalore",
        destination_lat=12.935,
        destination_lng=77.624,
        distance_km=12.0,
        duration_minutes=25,
    )

    geom = await provider.compute_segment_route(seg)
    assert geom.is_live_geometry is False
    assert geom.source == "deterministic_fallback"
    assert len(geom.warnings) > 0
    assert "unavailable" in geom.warnings[0].lower()
    assert geom.geojson_geometry is not None


# ============================================================================
# 5. MAPS SERVICE COMPOSITE ENRICHMENT
# ============================================================================

@pytest.mark.anyio
async def test_6_maps_service_composite_enrichment():
    """Verify MapsService enriches multimodal journeys and computes aggregate metrics."""
    fallback_provider = FallbackMapsProvider()
    service = MapsService(provider=fallback_provider)

    req = RouteEnrichRequest(
        journey_id="jny-test-01",
        segments=[
            RouteEnrichRequestSegment(
                segment_id="seg-01",
                mode="walk",
                origin_name="Home",
                origin_city="Chennai",
                origin_lat=13.080,
                origin_lng=80.270,
                destination_name="Bus Stop",
                destination_city="Chennai",
                destination_lat=13.085,
                destination_lng=80.275,
                distance_km=0.8,
                duration_minutes=10,
            ),
            RouteEnrichRequestSegment(
                segment_id="seg-02",
                mode="train",
                origin_name="Chennai Central",
                origin_city="Chennai",
                origin_lat=13.082,
                origin_lng=80.275,
                destination_name="Bangalore City",
                destination_city="Bangalore",
                destination_lat=12.978,
                destination_lng=77.572,
                distance_km=360.0,
                duration_minutes=270,
            ),
        ],
    )

    enriched = await service.enrich_journey_route(req)
    assert enriched.journey_id == "jny-test-01"
    assert len(enriched.segments) == 2
    assert enriched.total_distance_meters > 300000
    assert enriched.total_duration_seconds > 10000
    assert enriched.provider_status == "ok"
    assert enriched.has_live_geometry is False
