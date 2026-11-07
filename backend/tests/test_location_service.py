"""
backend/tests/test_location_service.py

Comprehensive tests for KogniSync Location & GPS Starting-Location Autofill (Milestone M3.4):
1. Reverse geocoding valid coordinates returns structured response and preserves coordinates.
2. Regional hub proximity fallback functions deterministically when network/external provider is offline.
3. Coordinate bounds validation rejects out-of-range values.
4. API endpoint GET /api/v1/location/reverse-geocode satisfies schema and camelCase contract.
5. Multi-modal journey search accepts and incorporates origin_coordinates for first-mile routing.
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.services.location.service import LocationService, haversine_distance_km
from app.services.location.schemas import ReverseGeocodeResponse

client = TestClient(app)


def test_haversine_distance_calculation():
    """Verify haversine formula correctly computes distance between Bangalore and Chennai (~290 km direct)."""
    dist = haversine_distance_km(12.9716, 77.5946, 13.0827, 80.2707)
    assert 280.0 <= dist <= 310.0


def test_reverse_geocode_regional_fallback():
    """Verify regional hub fallback resolves known Indian coordinates to their city and preserves precise coordinates."""
    service = LocationService()
    # Coordinates in Koramangala, Bangalore: 12.9352, 77.6245
    result = service._reverse_geocode_regional_fallback(12.9352, 77.6245)

    assert isinstance(result, ReverseGeocodeResponse)
    assert result.city == "Bangalore"
    assert result.coordinates.lat == 12.9352
    assert result.coordinates.lng == 77.6245
    assert result.provider == "kognisync_regional_hub"
    assert result.is_estimate is True
    assert "Bangalore" in result.formatted_address


@pytest.mark.anyio
async def test_reverse_geocode_bounds_validation():
    """Verify invalid coordinates outside standard latitude/longitude boundaries raise ValueError."""
    service = LocationService()

    with pytest.raises(ValueError, match="out of bounds"):
        await service.reverse_geocode(lat=95.0, lng=77.5946)

    with pytest.raises(ValueError, match="out of bounds"):
        await service.reverse_geocode(lat=12.9716, lng=195.0)


def test_api_reverse_geocode_endpoint_success():
    """Verify GET /api/v1/location/reverse-geocode returns 200 with camelCase serialized response."""
    response = client.get("/api/v1/location/reverse-geocode?lat=13.0827&lng=80.2707")
    assert response.status_code == 200
    data = response.json()

    assert "formattedAddress" in data
    assert "city" in data
    assert data["city"] == "Chennai"
    assert "coordinates" in data
    assert data["coordinates"]["lat"] == 13.0827
    assert data["coordinates"]["lng"] == 80.2707
    assert "provider" in data


def test_api_reverse_geocode_invalid_query():
    """Verify endpoint rejects missing or out-of-bounds parameters with 422."""
    # Missing parameters
    res_missing = client.get("/api/v1/location/reverse-geocode")
    assert res_missing.status_code == 422

    # Latitude out of bounds
    res_invalid_lat = client.get("/api/v1/location/reverse-geocode?lat=120.0&lng=77.0")
    assert res_invalid_lat.status_code == 422

    # Longitude out of bounds
    res_invalid_lng = client.get("/api/v1/location/reverse-geocode?lat=12.0&lng=200.0")
    assert res_invalid_lng.status_code == 422


def test_journey_search_with_origin_coordinates_preservation():
    """Verify POST /api/v1/journeys/search preserves custom origin_coordinates for first-mile routing."""
    custom_lat = 12.9279
    custom_lng = 77.6271

    payload = {
        "origin": "Bangalore",
        "destination": "Chennai",
        "departure_date": "2026-11-02",
        "preferred_arrival_before": "20:00",
        "budget_max": 6000.0,
        "passengers_count": 1,
        "weights": {"cost": 0.2, "duration": 0.5, "comfort": 0.2, "carbon": 0.1},
        "originCoordinates": {
            "lat": custom_lat,
            "lng": custom_lng,
        },
    }
    response = client.post("/api/v1/journeys/search", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "journeys" in data
    assert len(data["journeys"]) > 0

    # Inspect first journey's first segment origin coordinates
    first_journey = data["journeys"][0]
    first_segment = first_journey["segments"][0]

    # The starting node must match the user's custom GPS coordinates
    origin_coords = first_segment["origin"]["coordinates"]
    assert origin_coords["lat"] == custom_lat
    assert origin_coords["lng"] == custom_lng
