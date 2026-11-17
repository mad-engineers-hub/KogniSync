"""
backend/tests/test_dynamic_journey_map_sync.py

Comprehensive regression tests for M4.0.3: Dynamic Origin/Destination Synchronization Across Journey Map.
Verifies:
1. Forward geocoding of non-registered regional cities (Tumkur, Hubli, etc.) via regional gazetteer.
2. API endpoint GET /api/v1/location/geocode returns structured coordinates.
3. resolve_hub_context resolves dynamically to actual city coordinates instead of defaulting to Bengaluru.
4. Multimodal journey orchestration for Tumkur -> Chennai produces segments starting at Tumkur.
5. Spatial distance estimation dynamically uses real city coordinates.
6. Maps route enrichment accepts and reflects the dynamic origin coordinates.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.location.service import location_service
from app.services.journey.hubs import resolve_hub_context, estimate_corridor_distance_km
from app.services.journey.service import journey_orchestrator
from app.services.journey.schemas import JourneySearchRequest, CoordinatesSchema, OptimizationWeightsInput
from app.services.maps.schemas import RouteEnrichRequest, RouteEnrichRequestSegment

client = TestClient(app)


def test_forward_geocode_regional_gazetteer_tumkur():
    """Verify Tumkur resolves accurately via regional gazetteer without hardcoding in registry."""
    coords = location_service.forward_geocode_sync("Tumkur")
    assert coords is not None
    assert round(coords.lat, 2) == 13.34
    assert round(coords.lng, 2) == 77.10


def test_forward_geocode_api_endpoint():
    """Verify GET /api/v1/location/geocode returns 200 with camelCase coordinate payload."""
    response = client.get("/api/v1/location/geocode?q=Tumkur")
    assert response.status_code == 200
    data = response.json()
    assert "coordinates" in data
    assert "lat" in data["coordinates"]
    assert "lng" in data["coordinates"]
    assert abs(data["coordinates"]["lat"] - 13.34) < 0.05
    assert abs(data["coordinates"]["lng"] - 77.10) < 0.05


def test_resolve_hub_context_tumkur_dynamic():
    """Verify resolve_hub_context for Tumkur produces coordinates at Tumkur, NOT Bengaluru (~12.96, 77.57)."""
    hub = resolve_hub_context("Tumkur", is_origin=True)
    assert hub.parent_city == "Tumkur"
    assert not hub.is_locality

    # Verify origin user node coordinates are in Tumkur, not Bangalore
    user_lat = hub.user_node.coordinates.lat
    user_lng = hub.user_node.coordinates.lng
    assert abs(user_lat - 13.34) < 0.05
    assert abs(user_lng - 77.10) < 0.05

    # Bangalore is at 12.97, distance must be significant (> 35 km)
    assert abs(user_lat - 12.9716) > 0.3


def test_resolve_hub_context_custom_coordinates():
    """Verify custom GPS coordinates are strictly preserved and not overwritten."""
    custom = CoordinatesSchema(lat=13.3500, lng=77.1100)
    hub = resolve_hub_context("Tumkur", is_origin=True, custom_coordinates=custom)
    assert hub.user_node.coordinates.lat == 13.3500
    assert hub.user_node.coordinates.lng == 77.1100


def test_dynamic_corridor_distance_calculation():
    """Verify corridor distance calculation uses real coordinates for arbitrary cities."""
    dist_tumkur_chennai = estimate_corridor_distance_km("Tumkur", "Chennai")
    # Tumkur to Chennai direct is ~330km, with 1.25 circuity is ~410km
    assert 380 <= dist_tumkur_chennai <= 460


@pytest.mark.anyio
async def test_journey_orchestration_tumkur_origin_propagation():
    """Verify search_journeys for Tumkur -> Chennai produces journeys starting at Tumkur."""
    req = JourneySearchRequest(
        origin="Tumkur",
        destination="Chennai",
        departure_date="2026-11-16",
        passengers_count=1,
        weights=OptimizationWeightsInput(),
    )
    res = await journey_orchestrator.search_journeys(req)
    assert len(res.journeys) > 0

    first = res.journeys[0]
    # Journey origin must be Tumkur
    assert "Tumkur" in first.origin.name or "Tumkur" in first.origin.city
    assert abs(first.origin.coordinates.lat - 13.34) < 0.05
    assert abs(first.origin.coordinates.lng - 77.10) < 0.05

    # First segment origin must be at Tumkur
    seg0 = first.segments[0]
    assert abs(seg0.origin.coordinates.lat - 13.34) < 0.05
    assert abs(seg0.origin.coordinates.lng - 77.10) < 0.05


def test_maps_enrich_reflects_dynamic_origin():
    """Verify POST /api/v1/maps/enrich computes geometry starting from Tumkur coordinates."""
    payload = {
        "journey_id": "jny-tumkur-test",
        "segments": [
            {
                "segment_id": "seg-01",
                "mode": "cab",
                "origin_name": "Tumkur City Hub",
                "origin_city": "Tumkur",
                "origin_lat": 13.3401,
                "origin_lng": 77.1006,
                "destination_name": "Tumkur Railway Station",
                "destination_city": "Tumkur",
                "destination_lat": 13.3451,
                "destination_lng": 77.1056,
                "duration_minutes": 10,
                "distance_km": 3.5,
            }
        ],
    }
    response = client.post("/api/v1/maps/enrich", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["segments"]) == 1
    seg = data["segments"][0]
    # Coordinates in geometry must start at Tumkur
    coords = seg["coordinates"]
    assert len(coords) >= 2
    assert abs(coords[0]["latitude"] - 13.3401) < 0.001
    assert abs(coords[0]["longitude"] - 77.1006) < 0.001


def test_resolve_hub_context_stale_collision_detection():
    """Verify that stale coordinates belonging to another city (e.g. Bangalore coords with Tumkur query)
    are discarded in favor of geocoded Tumkur coordinates."""
    from app.services.journey.hubs import detect_cross_city_collision
    stale_blr = CoordinatesSchema(lat=12.9716, lng=77.5946)
    is_stale, conflict_city, dist = detect_cross_city_collision(stale_blr, "tumkur", "Tumkur")
    assert is_stale is True
    assert conflict_city == "Bangalore"

    hub = resolve_hub_context("Tumkur", is_origin=True, custom_coordinates=stale_blr)
    assert abs(hub.user_node.coordinates.lat - 13.34) < 0.05
    assert abs(hub.user_node.coordinates.lng - 77.10) < 0.05
    assert abs(hub.user_node.coordinates.lat - 12.9716) > 0.3


def test_resolve_hub_context_preserves_intentional_distant_gps():
    """Verify that intentional GPS coordinates > 45km from centroid (e.g. Palolem in Goa, Sira in Tumkur)
    are strictly preserved when no cross-city collision exists."""
    # Sira, Tumkur (~45 km from Tumkur centroid)
    sira_coords = CoordinatesSchema(lat=13.7447, lng=76.9077)
    hub_sira = resolve_hub_context("Tumkur", is_origin=True, custom_coordinates=sira_coords)
    assert hub_sira.user_node.coordinates.lat == 13.7447
    assert hub_sira.user_node.coordinates.lng == 76.9077

    # Palolem, Goa (~55 km from Goa centroid)
    palolem_coords = CoordinatesSchema(lat=15.0100, lng=74.0232)
    hub_palolem = resolve_hub_context("Goa", is_origin=False, custom_coordinates=palolem_coords)
    assert hub_palolem.user_node.coordinates.lat == 15.0100
    assert hub_palolem.user_node.coordinates.lng == 74.0232


def test_resolve_hub_context_unresolved_location_raises_value_error():
    """Verify that unknown locations with failed geocoding explicitly raise ValueError instead of defaulting."""
    with pytest.raises(ValueError, match="Unable to resolve coordinates for location"):
        resolve_hub_context("NonExistentCityXYZ999", is_origin=True)

