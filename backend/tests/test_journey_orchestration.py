"""
backend/tests/test_journey_orchestration.py

Comprehensive tests for KogniSync Backend Journey Orchestration Foundation (M2.0):
1. Valid journey search request.
2. Invalid request bounds validation.
3. Multimodal composition, sequential leg timing, and positive transfer buffers.
4. Door-to-door locality resolution (e.g. Udayapalya -> Chennai).
5. Hard constraint budget cap enforcement.
6. Zero relaxation when no journey meets constraints (impossible budget).
7. Hard constraint arrival deadline enforcement.
8. Deterministic reproducibility across repeated queries.
9. Pareto optimality and multi-objective scoring integration.
10. API contract camelCase and snake_case request/response alignment.
11. Journey orchestrator health endpoint.
"""
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ============================================================================
# 1. VALID JOURNEY SEARCH REQUEST
# ============================================================================

def test_1_valid_journey_search_request():
    """Verify POST /api/v1/journeys/search returns complete multimodal journeys."""
    payload = {
        "origin": "Chennai",
        "destination": "Udupi",
        "departure_date": "2026-11-02",
        "preferred_arrival_before": "20:00",
        "budget_max": 5000.0,
        "passengers_count": 1,
        "weights": {
            "cost": 0.15,
            "duration": 0.55,
            "comfort": 0.20,
            "carbon": 0.10,
        },
        "natural_language_query": "I need to reach Udupi from Chennai tomorrow before 8 PM. My budget is ₹5000 and I prefer speed.",
    }
    response = client.post("/api/v1/journeys/search", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "journeys" in data
    assert isinstance(data["journeys"], list)
    assert len(data["journeys"]) > 0
    assert data["totalCandidates"] == 5
    assert data["eligibleCandidates"] == len(data["journeys"])
    assert data["source"] == "backend_orchestrator"
    assert "providerStatus" in data
    assert data["providerStatus"]["transport"] == "catalog_modelled"
    assert data["providerStatus"]["optimizer"] == "authoritative_pareto"


# ============================================================================
# 2. INVALID REQUEST BOUNDS VALIDATION
# ============================================================================

def test_2_invalid_request_validation():
    """Verify input validation fails closed with HTTP 400 or 422 for invalid inputs."""
    base = {
        "origin": "Bangalore",
        "destination": "Chennai",
        "departure_date": "2026-11-05",
    }

    # Empty origin
    res1 = client.post("/api/v1/journeys/search", json={**base, "origin": "   "})
    assert res1.status_code in (400, 422)

    # Empty destination
    res2 = client.post("/api/v1/journeys/search", json={**base, "destination": ""})
    assert res2.status_code in (400, 422)

    # Negative budget
    res3 = client.post("/api/v1/journeys/search", json={**base, "budget_max": -100.0})
    assert res3.status_code in (400, 422)

    # Passengers count < 1
    res4 = client.post("/api/v1/journeys/search", json={**base, "passengers_count": 0})
    assert res4.status_code in (400, 422)

    # Invalid date format
    res5 = client.post("/api/v1/journeys/search", json={**base, "departure_date": "invalid-date"})
    assert res5.status_code in (400, 422)


# ============================================================================
# 3. MULTIMODAL COMPOSITION & CONNECTIVITY INVARIANTS
# ============================================================================

def test_3_multimodal_composition_and_connectivity():
    """Verify journeys have >= 3 segments with positive transfer buffers and mathematical invariants."""
    payload = {
        "origin": "Bangalore",
        "destination": "Goa",
        "departure_date": "2026-11-07",
        "preferred_arrival_before": "20:00",
        "budget_max": 6000.0,
    }
    response = client.post("/api/v1/journeys/search", json=payload)
    assert response.status_code == 200
    journeys = response.json()["journeys"]
    assert len(journeys) > 0

    for j in journeys:
        segments = j["segments"]
        assert len(segments) >= 3, f"Expected >= 3 segments, found {len(segments)}"

        # Verify sequential leg timing and positive transfer buffers
        for idx in range(len(segments)):
            seg = segments[idx]
            dep = datetime.fromisoformat(seg["departureTime"])
            arr = datetime.fromisoformat(seg["arrivalTime"])
            assert dep < arr, f"Segment {seg['segmentId']} departure must precede arrival"

            if idx > 0:
                prev_seg = segments[idx - 1]
                prev_arr = datetime.fromisoformat(prev_seg["arrivalTime"])
                transfer_buffer = (dep - prev_arr).total_seconds() / 60.0
                assert transfer_buffer >= 10.0, f"Transfer buffer {transfer_buffer}m must be >= 10m"

        # Verify mathematical aggregations
        sum_price = sum(s["price"] for s in segments)
        assert j["totalPrice"] == sum_price, "Total price must equal sum of segment prices"

        sum_travel_dur = sum(s["durationMinutes"] for s in segments)
        assert j["travelDurationMinutes"] == sum_travel_dur, "Travel duration must match leg sum"

        total_dur_calculated = round(
            (datetime.fromisoformat(segments[-1]["arrivalTime"]) - datetime.fromisoformat(segments[0]["departureTime"])).total_seconds() / 60.0
        )
        assert j["totalDurationMinutes"] == total_dur_calculated, "Total duration must match overall elapsed minutes"


# ============================================================================
# 4. DOOR-TO-DOOR LOCALITY RESOLUTION
# ============================================================================

def test_4_door_to_door_locality_resolution():
    """Verify localities (e.g. Udayapalya) resolve to local user addresses within parent metropolitan city."""
    payload = {
        "origin": "Udayapalya",
        "destination": "Chennai",
        "departure_date": "2026-10-30",
        "preferred_arrival_before": "20:00",
        "budget_max": 5000.0,
    }
    response = client.post("/api/v1/journeys/search", json=payload)
    assert response.status_code == 200
    journeys = response.json()["journeys"]
    assert len(journeys) > 0

    for j in journeys:
        # User node anchors to Udayapalya
        assert "Udayapalya" in j["origin"]["name"]
        assert j["origin"]["type"] == "address"
        assert "Bangalore" in j["origin"]["city"]

        # First segment originates from Udayapalya
        first_seg = j["segments"][0]
        assert "Udayapalya" in first_seg["origin"]["name"]

        # Destination connects to Chennai
        assert "Chennai" in j["destination"]["city"]
        last_seg = j["segments"][-1]
        assert "Chennai" in last_seg["destination"]["city"]


# ============================================================================
# 5. HARD CONSTRAINT BUDGET CAP ENFORCEMENT
# ============================================================================

def test_5_hard_constraint_budget_cap_enforcement():
    """Verify that all returned journeys strictly satisfy the requested budget cap."""
    budget_cap = 2000.0
    payload = {
        "origin": "Bangalore",
        "destination": "Chennai",
        "departure_date": "2026-11-05",
        "budget_max": budget_cap,
    }
    response = client.post("/api/v1/journeys/search", json=payload)
    assert response.status_code == 200
    journeys = response.json()["journeys"]

    assert len(journeys) > 0
    # Every single returned journey must be <= ₹2000
    for j in journeys:
        assert j["totalPrice"] <= budget_cap, f"Journey {j['id']} price ₹{j['totalPrice']} exceeded budget ₹{budget_cap}"

    # Verify expensive flight option (which costs > ₹2500) was excluded
    flight_options = [j for j in journeys if any(s["mode"] == "flight" for s in j["segments"])]
    assert len(flight_options) == 0, "Flight option exceeding budget should be pruned"


# ============================================================================
# 6. NO FEASIBLE JOURNEY ZERO RELAXATION
# ============================================================================

def test_6_no_feasible_journey_zero_relaxation():
    """Verify that impossible constraints return 0 candidates without silent relaxation."""
    payload = {
        "origin": "Bangalore",
        "destination": "Chennai",
        "departure_date": "2026-11-05",
        "budget_max": 20.0,  # Impossible budget cap
    }
    response = client.post("/api/v1/journeys/search", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Zero relaxation: empty journeys list with explicit count reporting
    assert data["journeys"] == []
    assert data["eligibleCandidates"] == 0
    assert data["totalCandidates"] == 5
    assert data["recommendedJourneyId"] is None


# ============================================================================
# 7. HARD CONSTRAINT ARRIVAL DEADLINE ENFORCEMENT
# ============================================================================

def test_7_hard_constraint_arrival_deadline_enforcement():
    """Verify that all composed journeys arrive safely prior to the requested deadline."""
    payload = {
        "origin": "Chennai",
        "destination": "Udupi",
        "departure_date": "2026-11-02",
        "preferred_arrival_before": "14:00",  # Arrive before 2:00 PM
    }
    response = client.post("/api/v1/journeys/search", json=payload)
    assert response.status_code == 200
    journeys = response.json()["journeys"]
    assert len(journeys) > 0

    for j in journeys:
        arr_time = datetime.fromisoformat(j["arrivalTime"])
        # Must arrive before 14:00 (target hour <= 13 or (target hour == 14 and minute == 0))
        assert arr_time.hour < 14 or (arr_time.hour == 14 and arr_time.minute == 0), (
            f"Journey {j['id']} arrival {arr_time.strftime('%H:%M')} must be <= 14:00"
        )


# ============================================================================
# 8. DETERMINISTIC REPRODUCIBILITY
# ============================================================================

def test_8_deterministic_reproducibility():
    """Verify identical requests generate identical outputs, scoring, and Pareto ranking."""
    payload = {
        "origin": "Bangalore",
        "destination": "Goa",
        "departure_date": "2026-11-07",
        "preferred_arrival_before": "20:00",
        "weights": {"cost": 0.40, "duration": 0.30, "comfort": 0.20, "carbon": 0.10},
    }
    res1 = client.post("/api/v1/journeys/search", json=payload)
    res2 = client.post("/api/v1/journeys/search", json=payload)

    assert res1.status_code == 200
    assert res2.status_code == 200

    data1 = res1.json()
    data2 = res2.json()

    assert data1["recommendedJourneyId"] == data2["recommendedJourneyId"]
    assert data1["totalCandidates"] == data2["totalCandidates"]
    assert len(data1["journeys"]) == len(data2["journeys"])

    for j1, j2 in zip(data1["journeys"], data2["journeys"]):
        assert j1["id"] == j2["id"]
        assert j1["totalPrice"] == j2["totalPrice"]
        assert j1["totalDurationMinutes"] == j2["totalDurationMinutes"]
        assert j1["isParetoOptimal"] == j2["isParetoOptimal"]
        assert j1["aiExplanation"]["score"] == j2["aiExplanation"]["score"]


# ============================================================================
# 9. PARETO OPTIMALITY & OPTIMIZER INTEGRATION
# ============================================================================

def test_9_pareto_optimality_and_optimizer_integration():
    """Verify Pareto frontier flags, multi-objective score breakdown, and explanations."""
    payload = {
        "origin": "Chennai",
        "destination": "Udupi",
        "departure_date": "2026-11-02",
        "preferred_arrival_before": "20:00",
        "weights": {"cost": 0.10, "duration": 0.60, "comfort": 0.20, "carbon": 0.10},
    }
    response = client.post("/api/v1/journeys/search", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Speed-weighted priority should rank Fastest option #1
    top_journey = data["journeys"][0]
    assert top_journey["recommendationCategory"] == "fastest"
    assert "optimization" in top_journey
    assert top_journey["optimization"] is not None

    opt = top_journey["optimization"]
    breakdown = opt.get("scoreBreakdown") or opt.get("score_breakdown")
    assert breakdown is not None
    assert "metrics" in opt
    assert "explanation" in opt
    total_score = breakdown.get("totalScore") or breakdown.get("total_score")
    assert total_score > 0
    assert len(opt["explanation"]["reasons"]) > 0


# ============================================================================
# 10. API CONTRACT CAMELCASE & SNAKE_CASE ACCEPTANCE
# ============================================================================

def test_10_api_contract_camelcase_and_snakecase():
    """Verify frontend-style camelCase payload is accepted and response includes camelCase fields."""
    camel_payload = {
        "origin": "Bangalore",
        "destination": "Chennai",
        "departureDate": "2026-11-05",
        "preferredArrivalBefore": "18:00",
        "budgetMax": 4000.0,
        "passengersCount": 2,
        "naturalLanguageQuery": "Bangalore to Chennai for 2 pax under 4000",
    }
    response = client.post("/api/v1/journeys/search", json=camel_payload)
    assert response.status_code == 200
    data = response.json()

    # CamelCase keys present in JSON response
    assert "totalCandidates" in data
    assert "eligibleCandidates" in data
    assert "recommendedJourneyId" in data
    assert "providerStatus" in data

    j = data["journeys"][0]
    assert "totalPrice" in j
    assert "totalDurationMinutes" in j
    assert "totalTransfers" in j
    assert "isParetoOptimal" in j
    assert "aiExplanation" in j
    assert "bookingFeasibility" in j


# ============================================================================
# 11. JOURNEY ORCHESTRATOR HEALTH ENDPOINT
# ============================================================================

def test_11_journey_orchestrator_health():
    """Verify GET /api/v1/journeys/health returns healthy status and supported modes."""
    response = client.get("/api/v1/journeys/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "flight" in data["supported_modes"]
    assert "train" in data["supported_modes"]
    assert "bus" in data["supported_modes"]
    assert "cab" in data["supported_modes"]
    assert "rapido" in data["supported_modes"]
    assert "metro" in data["supported_modes"]
    assert "walk" in data["supported_modes"]
