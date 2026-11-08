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


# ============================================================================
# 6. CONFIGURATION AUDIT & ENVIRONMENT READINESS (M3.5 AUDIT)
# ============================================================================

def test_7_valhalla_configuration_environments():
    """Verify Valhalla settings behave safely across development and production environments."""
    from app.core.config import Settings

    # 1. Development default: Valhalla enabled on localhost:8002
    dev_settings = Settings(ENVIRONMENT="development")
    assert dev_settings.VALHALLA_ENABLED is True
    assert dev_settings.VALHALLA_BASE_URL == "http://localhost:8002"

    # 2. Production default: Never silently assumes localhost is reachable; auto-disables
    prod_default = Settings(ENVIRONMENT="production")
    assert prod_default.VALHALLA_ENABLED is False
    assert prod_default.VALHALLA_BASE_URL == "http://localhost:8002"

    # 3. Production with external Valhalla URL: Automatically remains enabled
    prod_external = Settings(
        ENVIRONMENT="production",
        VALHALLA_BASE_URL="http://valhalla.cluster.internal:8002",
    )
    assert prod_external.VALHALLA_ENABLED is True
    assert prod_external.VALHALLA_BASE_URL == "http://valhalla.cluster.internal:8002"

    # 4. Production with explicit localhost opt-in (e.g. sidecar container setup)
    prod_sidecar = Settings(
        ENVIRONMENT="production",
        VALHALLA_ALLOW_LOCALHOST=True,
        VALHALLA_BASE_URL="http://localhost:8002",
    )
    assert prod_sidecar.VALHALLA_ENABLED is True

    # 5. Production with explicit disable
    prod_disabled = Settings(
        ENVIRONMENT="production",
        VALHALLA_ENABLED=False,
        VALHALLA_BASE_URL="http://valhalla.cluster.internal:8002",
    )
    assert prod_disabled.VALHALLA_ENABLED is False


@pytest.mark.anyio
async def test_8_valhalla_provider_disabled_and_unconfigured():
    """Verify provider-disabled and unconfigured behaviors route cleanly via fallback."""
    seg = RouteEnrichRequestSegment(
        segment_id="seg-cab-disabled",
        mode="cab",
        origin_name="A",
        origin_city="Bangalore",
        origin_lat=12.978,
        origin_lng=77.572,
        destination_name="B",
        destination_city="Bangalore",
        destination_lat=12.935,
        destination_lng=77.624,
        distance_km=10.0,
        duration_minutes=20,
    )

    # 1. Explicitly disabled provider
    provider_disabled = ValhallaMapsProvider(
        base_url="http://localhost:8002",
        enabled=False,
    )
    assert provider_disabled.is_available() is False
    geom_disabled = await provider_disabled.compute_segment_route(seg)
    assert geom_disabled.is_live_geometry is False
    assert geom_disabled.source == "deterministic_fallback"
    assert len(geom_disabled.coordinates) >= 2

    # 2. Empty base URL provider
    provider_empty_url = ValhallaMapsProvider(
        base_url="",
        enabled=True,
    )
    assert provider_empty_url.is_available() is False
    geom_empty = await provider_empty_url.compute_segment_route(seg)
    assert geom_empty.is_live_geometry is False
    assert geom_empty.source == "deterministic_fallback"


@pytest.mark.anyio
async def test_9_valhalla_provider_timeout_and_error_handling():
    """Verify provider-timeout and HTTP error codes trigger graceful fallback without unhandled exceptions."""
    seg = RouteEnrichRequestSegment(
        segment_id="seg-cab-err",
        mode="cab",
        origin_name="A",
        origin_city="Bangalore",
        origin_lat=12.978,
        origin_lng=77.572,
        destination_name="B",
        destination_city="Bangalore",
        destination_lat=12.935,
        destination_lng=77.624,
        distance_km=10.0,
        duration_minutes=20,
    )

    # 1. Timeout handling
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Socket read timed out after 3.0s")

    client_timeout = httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler))
    provider_timeout = ValhallaMapsProvider(
        base_url="http://localhost:8002",
        enabled=True,
        http_client=client_timeout,
    )
    geom_timeout = await provider_timeout.compute_segment_route(seg)
    assert geom_timeout.is_live_geometry is False
    assert geom_timeout.source == "deterministic_fallback"
    assert any("unavailable" in w.lower() for w in geom_timeout.warnings)

    # 2. HTTP 503 Service Unavailable
    def unavailable_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Temporarily Unavailable")

    client_503 = httpx.AsyncClient(transport=httpx.MockTransport(unavailable_handler))
    provider_503 = ValhallaMapsProvider(
        base_url="http://localhost:8002",
        enabled=True,
        http_client=client_503,
    )
    geom_503 = await provider_503.compute_segment_route(seg)
    assert geom_503.is_live_geometry is False
    assert geom_503.source == "deterministic_fallback"
    assert any("unavailable" in w.lower() for w in geom_503.warnings)

    # 3. HTTP 429 Rate Limit
    def ratelimit_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    client_429 = httpx.AsyncClient(transport=httpx.MockTransport(ratelimit_handler))
    provider_429 = ValhallaMapsProvider(
        base_url="http://localhost:8002",
        enabled=True,
        http_client=client_429,
    )
    geom_429 = await provider_429.compute_segment_route(seg)
    assert geom_429.is_live_geometry is False
    assert geom_429.source == "deterministic_fallback"


@pytest.mark.anyio
async def test_10_no_failed_request_preserves_stale_geometry():
    """Verify that a failure after a success never leaks or preserves stale geometry or live flags."""
    test_coords = [(12.978, 77.572), (12.935, 77.624)]
    valhalla_shape = encode_polyline(test_coords, precision=6)
    call_count = 0

    def alternating_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call succeeds
            return httpx.Response(
                200,
                json={
                    "trip": {
                        "summary": {"time": 600.0, "length": 8.0},
                        "legs": [
                            {
                                "shape": valhalla_shape,
                                "summary": {"time": 600.0, "length": 8.0},
                                "maneuvers": [],
                            }
                        ],
                    }
                },
            )
        else:
            # Subsequent call fails catastrophically
            raise httpx.ConnectError("Connection refused by localhost:8002")

    client_alt = httpx.AsyncClient(transport=httpx.MockTransport(alternating_handler))
    provider = ValhallaMapsProvider(
        base_url="http://localhost:8002",
        enabled=True,
        http_client=client_alt,
    )

    seg_success = RouteEnrichRequestSegment(
        segment_id="seg-live-success",
        mode="cab",
        origin_name="A",
        origin_city="Bangalore",
        origin_lat=12.978,
        origin_lng=77.572,
        destination_name="B",
        destination_city="Bangalore",
        destination_lat=12.935,
        destination_lng=77.624,
        distance_km=8.0,
        duration_minutes=10,
    )

    seg_failure = RouteEnrichRequestSegment(
        segment_id="seg-subsequent-failure",
        mode="cab",
        origin_name="C",
        origin_city="Chennai",
        origin_lat=13.082,
        origin_lng=80.270,
        destination_name="D",
        destination_city="Chennai",
        destination_lat=12.990,
        destination_lng=80.170,
        distance_km=18.0,
        duration_minutes=35,
    )

    # 1. First call: success
    res1 = await provider.compute_segment_route(seg_success)
    assert res1.is_live_geometry is True
    assert res1.source == "valhalla_live"
    assert res1.encoded_polyline == valhalla_shape

    # 2. Second call: failure -> must NOT retain res1 geometry or live status
    res2 = await provider.compute_segment_route(seg_failure)
    assert res2.is_live_geometry is False
    assert res2.source == "deterministic_fallback"
    assert res2.encoded_polyline != valhalla_shape
    # Coordinates must reflect segment C->D, not segment A->B
    assert abs(res2.coordinates[0].latitude - 13.082) < 1e-3
    assert abs(res2.coordinates[-1].latitude - 12.990) < 1e-3


