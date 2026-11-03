import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.services.maps.schemas import (
    RouteCoordinate,
    RouteEnrichRequest,
    RouteEnrichRequestSegment,
)
from app.services.maps.fallback import FallbackMapsProvider, haversine_distance_meters
from app.services.maps.google_routes import GoogleRoutesProvider
from app.services.maps.polyline import decode_polyline, encode_polyline
from app.services.maps.service import MapsService

client = TestClient(app)


def test_maps_health_endpoint():
    """Verify health endpoint reports provider status without exposing credentials."""
    response = client.get("/api/v1/routes/health")
    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data
    assert "active_provider" in data
    assert "api_key_configured" in data
    assert "service" in data
    assert isinstance(data["api_key_configured"], bool)
    assert "AQ." not in str(data)  # Key hygiene: never leak raw key strings


def test_polyline_round_trip():
    """Verify standard Google encoded polyline encoding and decoding."""
    coords = [
        RouteCoordinate(latitude=13.0827, longitude=80.2707),
        RouteCoordinate(latitude=13.0450, longitude=80.2400),
        RouteCoordinate(latitude=12.9900, longitude=80.1700),
    ]
    encoded = encode_polyline(coords)
    assert isinstance(encoded, str)
    assert len(encoded) > 0

    decoded = decode_polyline(encoded)
    assert len(decoded) == len(coords)
    for orig, dec in zip(coords, decoded):
        assert abs(orig.latitude - dec.latitude) < 1e-4
        assert abs(orig.longitude - dec.longitude) < 1e-4


@pytest.mark.anyio
async def test_fallback_provider_road_segment():
    """Verify deterministic fallback provider computes road waypoints and distances."""
    provider = FallbackMapsProvider()
    seg = RouteEnrichRequestSegment(
        segment_id="seg-first-mile-cab",
        mode="cab",
        origin_name="Chennai City Center",
        origin_city="Chennai",
        origin_lat=13.0827,
        origin_lng=80.2707,
        destination_name="Chennai International Airport",
        destination_city="Chennai",
        destination_lat=12.9900,
        destination_lng=80.1700,
        duration_minutes=40,
        distance_km=18.5,
    )

    geom = await provider.compute_segment_route(seg)
    assert geom.segment_id == "seg-first-mile-cab"
    assert geom.mode == "cab"
    assert geom.source == "deterministic_fallback"
    assert geom.distance_meters == 18500
    assert geom.duration_seconds == 40 * 60
    assert len(geom.coordinates) >= 2
    assert geom.coordinates[0].latitude == pytest.approx(13.0827, abs=1e-4)
    assert geom.coordinates[-1].latitude == pytest.approx(12.9900, abs=1e-4)
    assert geom.encoded_polyline is not None


@pytest.mark.anyio
async def test_fallback_provider_flight_segment():
    """Verify flight segments use geodesic arc path while preserving schedule."""
    provider = FallbackMapsProvider()
    seg = RouteEnrichRequestSegment(
        segment_id="seg-flight-maa-ixe",
        mode="flight",
        origin_name="Chennai Airport (MAA)",
        origin_city="Chennai",
        origin_lat=12.9900,
        origin_lng=80.1700,
        destination_name="Mangalore Airport (IXE)",
        destination_city="Mangalore",
        destination_lat=12.9613,
        destination_lng=74.8900,
        duration_minutes=85,
        distance_km=580.0,
    )

    geom = await provider.compute_segment_route(seg)
    assert geom.mode == "flight"
    assert geom.duration_seconds == 85 * 60
    assert geom.distance_meters == 580000
    # Flight arc should produce at least 15 points
    assert len(geom.coordinates) >= 15


@pytest.mark.anyio
async def test_fallback_provider_rail_segment():
    """Verify rail segments use rail path and preserve train schedule."""
    provider = FallbackMapsProvider()
    seg = RouteEnrichRequestSegment(
        segment_id="seg-train-bangalore-chennai",
        mode="train",
        origin_name="KSR Bengaluru",
        origin_city="Bangalore",
        origin_lat=12.9780,
        origin_lng=77.5690,
        destination_name="Chennai Central",
        destination_city="Chennai",
        destination_lat=13.0827,
        destination_lng=80.2707,
        duration_minutes=270,
        distance_km=360.0,
    )

    geom = await provider.compute_segment_route(seg)
    assert geom.mode == "train"
    assert geom.duration_seconds == 270 * 60
    assert geom.distance_meters == 360000
    assert len(geom.coordinates) >= 10


@pytest.mark.anyio
async def test_google_provider_without_key_falls_back():
    """Verify GoogleRoutesProvider safely falls back when no API key is provided."""
    provider = GoogleRoutesProvider(api_key=None)
    seg = RouteEnrichRequestSegment(
        segment_id="seg-test-cab",
        mode="cab",
        origin_name="Bangalore City",
        origin_city="Bangalore",
        origin_lat=12.9716,
        origin_lng=77.5946,
        destination_name="Bangalore Airport",
        destination_city="Bangalore",
        destination_lat=13.1986,
        destination_lng=77.7066,
        duration_minutes=50,
        distance_km=35.0,
    )

    geom = await provider.compute_segment_route(seg)
    assert geom.segment_id == "seg-test-cab"
    assert geom.source == "deterministic_fallback"
    assert len(geom.coordinates) > 0


@pytest.mark.anyio
async def test_google_provider_mocked_success():
    """Verify GoogleRoutesProvider parses Google Routes v2 response correctly."""
    provider = GoogleRoutesProvider(api_key="mock_key_for_testing")
    seg = RouteEnrichRequestSegment(
        segment_id="seg-cab-route",
        mode="cab",
        origin_name="Point A",
        origin_city="City A",
        origin_lat=13.0827,
        origin_lng=80.2707,
        destination_name="Point B",
        destination_city="City A",
        destination_lat=12.9900,
        destination_lng=80.1700,
        duration_minutes=35,
        distance_km=18.0,
    )

    fake_coords = [
        RouteCoordinate(latitude=13.0827, longitude=80.2707),
        RouteCoordinate(latitude=13.0400, longitude=80.2200),
        RouteCoordinate(latitude=12.9900, longitude=80.1700),
    ]
    fake_encoded = encode_polyline(fake_coords)

    from unittest.mock import MagicMock
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "routes": [
            {
                "distanceMeters": 18240,
                "duration": "2100s",
                "polyline": {"encodedPolyline": fake_encoded},
            }
        ]
    }

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        geom = await provider.compute_segment_route(seg)
        assert geom.source == "google_routes"
        assert geom.distance_meters == 18240
        assert geom.duration_seconds == 2100
        assert len(geom.coordinates) == 3


@pytest.mark.anyio
async def test_google_provider_resilient_error_handling():
    """Verify provider falls back cleanly when Google Routes raises network error or 500."""
    provider = GoogleRoutesProvider(api_key="mock_key_for_testing")
    seg = RouteEnrichRequestSegment(
        segment_id="seg-err-cab",
        mode="cab",
        origin_name="Point A",
        origin_city="City A",
        origin_lat=13.0827,
        origin_lng=80.2707,
        destination_name="Point B",
        destination_city="City A",
        destination_lat=12.9900,
        destination_lng=80.1700,
        duration_minutes=35,
        distance_km=18.0,
    )

    with patch(
        "httpx.AsyncClient.post", side_effect=Exception("Network connection timeout")
    ):
        geom = await provider.compute_segment_route(seg)
        assert geom.segment_id == "seg-err-cab"
        assert geom.source == "deterministic_fallback"
        assert len(geom.warnings) > 0
        assert "Google Routes unavailable" in geom.warnings[0]


def test_enrich_journey_route_api_endpoint():
    """Verify POST /api/v1/routes/enrich returns fully enriched door-to-door itinerary."""
    payload = {
        "journey_id": "jny-chennai-udupi-door-to-door",
        "segments": [
            {
                "segment_id": "seg-1",
                "mode": "cab",
                "origin_name": "Chennai City",
                "origin_city": "Chennai",
                "origin_lat": 13.0827,
                "origin_lng": 80.2707,
                "destination_name": "Chennai Airport (MAA)",
                "destination_city": "Chennai",
                "destination_lat": 12.9900,
                "destination_lng": 80.1700,
                "duration_minutes": 40,
                "distance_km": 18.0,
            },
            {
                "segment_id": "seg-2",
                "mode": "flight",
                "origin_name": "Chennai Airport (MAA)",
                "origin_city": "Chennai",
                "origin_lat": 12.9900,
                "origin_lng": 80.1700,
                "destination_name": "Mangalore Airport (IXE)",
                "destination_city": "Mangalore",
                "destination_lat": 12.9613,
                "destination_lng": 74.8900,
                "duration_minutes": 88,
                "distance_km": 580.0,
            },
            {
                "segment_id": "seg-3",
                "mode": "cab",
                "origin_name": "Mangalore Airport (IXE)",
                "origin_city": "Mangalore",
                "origin_lat": 12.9613,
                "origin_lng": 74.8900,
                "destination_name": "Udupi Krishna Temple",
                "destination_city": "Udupi",
                "destination_lat": 13.3409,
                "destination_lng": 74.7421,
                "duration_minutes": 65,
                "distance_km": 55.0,
            },
        ],
    }

    response = client.post("/api/v1/routes/enrich", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["journey_id"] == "jny-chennai-udupi-door-to-door"
    assert len(data["segments"]) == 3
    assert data["total_distance_meters"] > 600000  # ~653 km
    assert data["total_duration_seconds"] > 10000
    assert data["provider_status"] == "ok"

    for seg in data["segments"]:
        assert len(seg["coordinates"]) > 0
        assert seg["distance_meters"] > 0
        assert seg["duration_seconds"] > 0
        assert seg["origin_coords"]["latitude"] is not None
        assert seg["destination_coords"]["longitude"] is not None


def test_enrich_journey_empty_segments_validation():
    """Verify endpoint rejects empty segment list with 400."""
    response = client.post(
        "/api/v1/routes/enrich",
        json={"journey_id": "jny-empty", "segments": []},
    )
    assert response.status_code == 400
