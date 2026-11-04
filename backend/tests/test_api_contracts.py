"""
backend/tests/test_api_contracts.py
Focused API Contract Harmonization and Integration Alignment Tests for KogniSync.

Validates:
1. Maps API canonical (/api/v1/maps/*) and legacy alias (/api/v1/routes/*) endpoints.
2. AI API canonical (/api/v1/ai/*) and legacy alias (/api/ai/*) endpoints.
3. Request schema flexibility: accepts both snake_case and camelCase parameters.
4. Response schema stability: required fields, types, and nullability.
5. Error response contracts: 400 Bad Request and 422 Validation Error envelopes.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ============================================================================
# 1. MAPS & ROUTING CONTRACT TESTS
# ============================================================================

def test_maps_health_canonical_and_alias():
    """Verify both canonical /api/v1/maps/health and alias /api/v1/routes/health respond identically."""
    res_canonical = client.get("/api/v1/maps/health")
    assert res_canonical.status_code == 200
    data_c = res_canonical.json()

    res_alias = client.get("/api/v1/routes/health")
    assert res_alias.status_code == 200
    data_a = res_alias.json()

    assert data_c == data_a
    assert "enabled" in data_c
    assert "active_provider" in data_c
    assert "api_key_configured" in data_c
    assert "service" in data_c
    assert isinstance(data_c["enabled"], bool)


def test_maps_enrich_canonical_endpoint():
    """Verify canonical POST /api/v1/maps/enrich computes route geometry."""
    payload = {
        "journey_id": "jny-test-contract-1",
        "segments": [
            {
                "segment_id": "seg-1",
                "mode": "cab",
                "origin_name": "Chennai Central",
                "origin_city": "Chennai",
                "origin_lat": 13.0827,
                "origin_lng": 80.2707,
                "destination_name": "Chennai Airport",
                "destination_city": "Chennai",
                "destination_lat": 12.9900,
                "destination_lng": 80.1700,
                "duration_minutes": 40,
                "distance_km": 18.0,
            }
        ],
    }

    response = client.post("/api/v1/maps/enrich", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["journey_id"] == "jny-test-contract-1"
    assert len(data["segments"]) == 1
    assert data["total_distance_meters"] > 0
    assert data["total_duration_seconds"] > 0
    assert data["provider_status"] == "ok"
    assert "coordinates" in data["segments"][0]
    assert len(data["segments"][0]["coordinates"]) >= 2


def test_maps_enrich_camelcase_input_acceptance():
    """Verify POST /api/v1/maps/enrich accepts camelCase JSON fields from TypeScript callers."""
    payload = {
        "journeyId": "jny-test-camel",
        "segments": [
            {
                "segmentId": "seg-c1",
                "mode": "train",
                "originName": "Bangalore City Hub",
                "originCity": "Bangalore",
                "originLat": 12.9781,
                "originLng": 77.5694,
                "destinationName": "Chennai Central",
                "destinationCity": "Chennai",
                "destinationLat": 13.0827,
                "destinationLng": 80.2755,
                "durationMinutes": 330,
                "distanceKm": 350.0,
            }
        ],
    }

    response = client.post("/api/v1/maps/enrich", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["journey_id"] == "jny-test-camel"
    assert len(data["segments"]) == 1
    assert data["segments"][0]["segment_id"] == "seg-c1"


def test_maps_enrich_empty_segments_rejection():
    """Verify endpoint rejects empty segment list with 400 Bad Request."""
    response = client.post("/api/v1/maps/enrich", json={"journey_id": "jny-empty", "segments": []})
    assert response.status_code == 400
    assert "at least one segment" in response.json()["detail"].lower()


# ============================================================================
# 2. AI INTENT EXTRACTION CONTRACT TESTS
# ============================================================================

def test_ai_canonical_and_alias_endpoints():
    """Verify canonical /api/v1/ai/parse-travel-intent and legacy /api/ai/parse-travel-intent respond with 200."""
    payload = {
        "text": "Chennai to Udupi tomorrow before 8 PM under ₹5000",
    }

    res_canonical = client.post("/api/v1/ai/parse-travel-intent", json=payload)
    assert res_canonical.status_code == 200
    data_c = res_canonical.json()

    res_alias = client.post("/api/ai/parse-travel-intent", json=payload)
    assert res_alias.status_code == 200
    data_a = res_alias.json()

    assert "intent" in data_c
    assert "intent" in data_a
    assert data_c["intent"]["origin"] == data_a["intent"]["origin"]
    assert data_c["intent"]["destination"] == data_a["intent"]["destination"]


def test_ai_camelcase_context_acceptance():
    """Verify AI intent endpoint accepts camelCase currentContext fields."""
    payload = {
        "text": "Make it for 2 passengers with higher comfort",
        "currentContext": {
            "origin": "Bangalore",
            "destination": "Goa",
            "date": "2026-11-04",
            "arrivalDeadline": "18:00",
            "timePriority": 0.3,
            "preferredModes": ["flight", "cab"],
        },
    }

    response = client.post("/api/v1/ai/parse-travel-intent", json=payload)
    assert response.status_code == 200
    intent = response.json()["intent"]
    assert intent["origin"] == "Bangalore"
    assert intent["destination"] == "Goa"


def test_ai_empty_text_rejection():
    """Verify endpoint rejects empty text payload with 400 Bad Request."""
    response = client.post("/api/v1/ai/parse-travel-intent", json={"text": "   "})
    assert response.status_code == 400
    assert "input text is required" in response.json()["detail"].lower()


# ============================================================================
# 3. OPTIMIZER CONTRACT TESTS (DUAL CASING)
# ============================================================================

def test_optimizer_camelcase_input_acceptance():
    """Verify optimizer accepts camelCase candidate fields from TypeScript."""
    payload = {
        "weights": {"cost": 0.5, "duration": 0.5},
        "budgetMax": 4000,
        "preferredArrivalBefore": "20:00",
        "candidates": [
            {
                "id": "c-camel-1",
                "title": "Express Air Link",
                "totalPrice": 3500,
                "totalDurationMinutes": 180,
                "totalTransfers": 1,
                "carbonKg": 22.0,
                "comfortScore": 8.5,
                "modes": ["cab", "flight", "cab"],
            },
            {
                "id": "c-camel-2",
                "title": "Superfast Rail",
                "totalPrice": 1200,
                "totalDurationMinutes": 420,
                "totalTransfers": 1,
                "carbonKg": 8.5,
                "comfortScore": 7.0,
                "modes": ["cab", "train", "cab"],
            },
        ],
    }

    response = client.post("/api/v1/optimizer/optimize", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total_candidates"] == 2
    assert data["eligible_candidates"] == 2
    assert len(data["journeys"]) == 2
    assert "recommended_journey_id" in data

