"""
backend/tests/test_pydantic_api_contracts_compatibility.py

Focused regression test suite verifying Phase 3 Pydantic v2 API contracts:
1. Python constructor keyword arguments (snake_case)
2. Deserialization of incoming camelCase API payloads
3. Deserialization of incoming snake_case API payloads
4. Serialization to outgoing camelCase JSON (by_alias=True)
5. Defaults, optional fields, and validation behavior
6. Frontend-backend 1:1 schema alignment
"""
import pytest
from datetime import datetime, timezone, timedelta
from app.services.journey.schemas import (
    AIExplanationSchema,
    AttributeProvenanceSchema,
    BookingFeasibilitySchema,
    CoordinatesSchema,
    JourneyProvenanceSchema,
    JourneySchema,
    JourneySearchRequest,
    JourneySearchResponse,
    JourneySegmentSchema,
    LocationSchema,
    SegmentAvailabilitySchema,
    SegmentProvenanceSchema,
)
from app.services.journey.provider import (
    NormalizedTransportSegmentResponse,
    ProviderCapabilities,
    TransportSegmentSearchRequest,
)


def test_1_snake_case_python_constructor_calls():
    """Confirms all Pydantic schemas can be constructed via native snake_case Python keywords."""
    attr = AttributeProvenanceSchema(
        source_type="provider_live",
        provider_name="Valhalla OSM Routing Engine",
        is_estimate=False,
        notes="Live road routing",
        last_updated_at="2026-11-07T12:00:00Z",
    )
    assert attr.source_type == "provider_live"
    assert attr.provider_name == "Valhalla OSM Routing Engine"
    assert attr.is_estimate is False

    seg_prov = SegmentProvenanceSchema(
        source_type="provider_live",
        provider_name="Valhalla OSM Routing Engine",
        is_estimate=False,
        has_live_provider=True,
        attributes={"duration": attr},
    )
    assert seg_prov.has_live_provider is True

    jny_prov = JourneyProvenanceSchema(
        overall_source_type="mixed",
        is_fully_confirmed=False,
        has_live_attributes=True,
        has_simulated_attributes=True,
        summary="Mixed provenance test",
    )
    assert jny_prov.overall_source_type == "mixed"
    assert jny_prov.is_fully_confirmed is False

    avail = SegmentAvailabilitySchema(
        status="available",
        remaining_units=42,
        is_real_inventory=False,
    )
    assert avail.is_real_inventory is False

    loc1 = LocationSchema(
        id="loc-1",
        name="Origin",
        city="CityA",
        type="landmark",
        coordinates=CoordinatesSchema(lat=12.9, lng=80.1),
    )
    loc2 = LocationSchema(
        id="loc-2",
        name="Dest",
        city="CityB",
        type="landmark",
        coordinates=CoordinatesSchema(lat=13.0, lng=80.2),
    )

    seg = JourneySegmentSchema(
        segment_id="seg-test-01",
        sequence=1,
        mode="cab",
        provider="KogniCab",
        origin=loc1,
        destination=loc2,
        departure_time="2026-11-07T08:00:00",
        arrival_time="2026-11-07T08:30:00",
        duration_minutes=30,
        price=350.0,
        distance_km=15.0,
        carbon_kg=2.5,
        comfort_score=8.5,
        transfer_buffer_minutes=15,
        availability=avail,
        provenance=seg_prov,
    )
    assert seg.segment_id == "seg-test-01"
    assert seg.duration_minutes == 30

    ai = AIExplanationSchema(
        summary="Test summary",
        trade_offs=["Tradeoff 1"],
        rank_reason="Ranked #1",
        score=88.5,
        cost_vs_fastest_saving=120.0,
        duration_diff_minutes=15,
        data_credibility_notice="Notice",
        is_fare_estimated=True,
        is_duration_estimated=False,
        is_availability_verified=False,
    )
    assert ai.score == 88.5
    assert ai.is_fare_estimated is True

    bf = BookingFeasibilitySchema(
        hold_supported=True,
        concurrency_safe=True,
        hold_ttl_seconds=600,
    )
    assert bf.hold_ttl_seconds == 600

    j = JourneySchema(
        id="jny-test-01",
        title="Test Journey",
        origin=loc1,
        destination=loc2,
        departure_time="2026-11-07T08:00:00",
        arrival_time="2026-11-07T12:00:00",
        total_duration_minutes=240,
        travel_duration_minutes=210,
        waiting_duration_minutes=30,
        in_vehicle_duration_minutes=210,
        walking_duration_minutes=0,
        is_connection_feasible=True,
        connection_feasibility_notes=["Connection verified"],
        total_price=1200.0,
        currency="INR",
        total_transfers=1,
        modes=["cab", "train"],
        segments=[seg],
        carbon_kg=12.0,
        comfort_score=8.7,
        recommendation_category="best_value",
        is_pareto_optimal=True,
        ai_explanation=ai,
        booking_feasibility=bf,
        provenance=jny_prov,
    )
    assert j.total_duration_minutes == 240
    assert j.is_connection_feasible is True

    req = JourneySearchRequest(
        origin="Chennai",
        destination="Udupi",
        departure_date="2026-11-07",
        preferred_arrival_before="20:00",
        budget_max=5000.0,
    )
    assert req.departure_date == "2026-11-07"
    assert req.preferred_arrival_before == "20:00"

    resp = JourneySearchResponse(
        journeys=[j],
        recommended_journey_id="jny-test-01",
        total_candidates=1,
        eligible_candidates=1,
        pareto_frontier_count=1,
        source="backend_orchestrator",
        provider_status={"valhalla": "active_live"},
    )
    assert resp.recommended_journey_id == "jny-test-01"

    # Provider interfaces
    p_req = TransportSegmentSearchRequest(
        origin_title="Pickup",
        origin_city="Chennai",
        origin_lat=12.9,
        origin_lng=80.1,
        destination_title="Dropoff",
        destination_city="Chennai",
        destination_lat=13.0,
        destination_lng=80.2,
        mode="cab",
    )
    assert p_req.mode == "cab"

    p_resp = NormalizedTransportSegmentResponse(
        provider_id="valhalla",
        provider_name="Valhalla OSM Routing Engine",
        mode="cab",
        duration_minutes=25,
        distance_km=18.0,
        departure_time="2026-11-07T08:00:00",
        arrival_time="2026-11-07T08:25:00",
        attribute_provenance={"duration": attr},
    )
    assert p_resp.duration_minutes == 25

    caps = ProviderCapabilities(
        provider_id="valhalla",
        name="Valhalla OSM Routing Engine",
        supported_modes=["cab", "auto", "rapido", "bus", "walk"],
        is_available=True,
        is_live_authenticated=True,
        timeout_seconds=3.0,
    )
    assert caps.provider_id == "valhalla"


def test_2_incoming_camelcase_payload_deserialization():
    """Verifies that API payloads formatted in camelCase (from frontend) deserialize correctly."""
    payload = {
        "origin": "Chennai",
        "destination": "Udupi",
        "departureDate": "2026-11-08",
        "preferredArrivalBefore": "19:30",
        "budgetMax": 4500.0,
        "passengersCount": 2,
    }
    req = JourneySearchRequest.model_validate(payload)
    assert req.origin == "Chennai"
    assert req.destination == "Udupi"
    assert req.departure_date == "2026-11-08"
    assert req.preferred_arrival_before == "19:30"
    assert req.budget_max == 4500.0
    assert req.passengers_count == 2

    # Provider request camelCase
    p_payload = {
        "originTitle": "Station A",
        "originCity": "City A",
        "originLat": 12.92,
        "originLng": 80.12,
        "destinationTitle": "Station B",
        "destinationCity": "City B",
        "destinationLat": 13.04,
        "destinationLng": 80.24,
        "mode": "auto",
    }
    p_req = TransportSegmentSearchRequest.model_validate(p_payload)
    assert p_req.origin_lat == 12.92
    assert p_req.destination_lat == 13.04
    assert p_req.origin_title == "Station A"


def test_3_incoming_snake_case_payload_deserialization():
    """Verifies that API payloads formatted in snake_case deserialize correctly."""
    payload = {
        "origin": "Chennai",
        "destination": "Udupi",
        "departure_date": "2026-11-08",
        "preferred_arrival_before": "19:30",
        "budget_max": 4500.0,
        "passengers_count": 2,
    }
    req = JourneySearchRequest.model_validate(payload)
    assert req.departure_date == "2026-11-08"
    assert req.preferred_arrival_before == "19:30"
    assert req.budget_max == 4500.0


def test_4_outgoing_response_serialization_emits_camelcase():
    """Verifies that response serialization emits the exact camelCase keys expected by the frontend."""
    loc = LocationSchema(
        id="loc-1",
        name="Origin",
        city="CityA",
        type="landmark",
        coordinates=CoordinatesSchema(lat=12.9, lng=80.1),
    )
    seg = JourneySegmentSchema(
        segment_id="seg-1",
        sequence=1,
        mode="cab",
        provider="KogniCab",
        origin=loc,
        destination=loc,
        departure_time="2026-11-07T08:00:00",
        arrival_time="2026-11-07T08:30:00",
        duration_minutes=30,
        price=200.0,
        distance_km=10.0,
        carbon_kg=1.5,
        comfort_score=8.0,
        transfer_buffer_minutes=15,
        availability=SegmentAvailabilitySchema(status="available", remaining_units=10, is_real_inventory=False),
        provenance=SegmentProvenanceSchema(
            source_type="provider_live",
            provider_name="Valhalla",
            is_estimate=False,
            has_live_provider=True,
            attributes={
                "duration": AttributeProvenanceSchema(
                    source_type="provider_live",
                    provider_name="Valhalla",
                    is_estimate=False,
                )
            },
        ),
    )
    journey = JourneySchema(
        id="jny-1",
        title="Sample Journey",
        origin=loc,
        destination=loc,
        departure_time="2026-11-07T08:00:00",
        arrival_time="2026-11-07T08:30:00",
        total_duration_minutes=30,
        travel_duration_minutes=30,
        waiting_duration_minutes=0,
        in_vehicle_duration_minutes=30,
        walking_duration_minutes=0,
        is_connection_feasible=True,
        connection_feasibility_notes=[],
        total_price=200.0,
        total_transfers=0,
        modes=["cab"],
        segments=[seg],
        carbon_kg=1.5,
        comfort_score=8.0,
        recommendation_category="fastest",
        ai_explanation=AIExplanationSchema(
            summary="Fast route",
            trade_offs=[],
            rank_reason="Fastest",
            score=95.0,
            is_fare_estimated=True,
            is_duration_estimated=False,
            is_availability_verified=False,
        ),
        booking_feasibility=BookingFeasibilitySchema(
            hold_supported=True,
            concurrency_safe=True,
            hold_ttl_seconds=600,
        ),
        provenance=JourneyProvenanceSchema(
            overall_source_type="provider_live",
            is_fully_confirmed=False,
            has_live_attributes=True,
            has_simulated_attributes=False,
            summary="All live",
        ),
    )
    resp = JourneySearchResponse(
        journeys=[journey],
        recommended_journey_id="jny-1",
        total_candidates=1,
        eligible_candidates=1,
        pareto_frontier_count=1,
        source="backend_orchestrator",
        provider_status={"valhalla": "active_live"},
    )

    dumped = resp.model_dump(by_alias=True)

    # Top-level keys must be camelCase
    assert "recommendedJourneyId" in dumped
    assert "totalCandidates" in dumped
    assert "eligibleCandidates" in dumped
    assert "paretoFrontierCount" in dumped
    assert "providerStatus" in dumped

    j_dumped = dumped["journeys"][0]
    assert "totalDurationMinutes" in j_dumped
    assert "travelDurationMinutes" in j_dumped
    assert "waitingDurationMinutes" in j_dumped
    assert "inVehicleDurationMinutes" in j_dumped
    assert "walkingDurationMinutes" in j_dumped
    assert "isConnectionFeasible" in j_dumped
    assert "connectionFeasibilityNotes" in j_dumped
    assert "totalPrice" in j_dumped
    assert "totalTransfers" in j_dumped
    assert "recommendationCategory" in j_dumped
    assert "aiExplanation" in j_dumped
    assert "bookingFeasibility" in j_dumped

    # aiExplanation keys
    ai_dumped = j_dumped["aiExplanation"]
    assert "rankReason" in ai_dumped
    assert "tradeOffs" in ai_dumped
    assert "isFareEstimated" in ai_dumped
    assert "isDurationEstimated" in ai_dumped
    assert "isAvailabilityVerified" in ai_dumped

    # bookingFeasibility keys
    bf_dumped = j_dumped["bookingFeasibility"]
    assert "holdSupported" in bf_dumped
    assert "concurrencySafe" in bf_dumped
    assert "holdTtlSeconds" in bf_dumped

    # provenance keys
    prov_dumped = j_dumped["provenance"]
    assert "overallSourceType" in prov_dumped
    assert "isFullyConfirmed" in prov_dumped
    assert "hasLiveAttributes" in prov_dumped
    assert "hasSimulatedAttributes" in prov_dumped

    # segment keys
    seg_dumped = j_dumped["segments"][0]
    assert "segmentId" in seg_dumped
    assert "departureTime" in seg_dumped
    assert "arrivalTime" in seg_dumped
    assert "durationMinutes" in seg_dumped
    assert "distanceKm" in seg_dumped
    assert "carbonKg" in seg_dumped
    assert "comfortScore" in seg_dumped
    assert "transferBufferMinutes" in seg_dumped
    assert "isRealInventory" in seg_dumped["availability"]

    seg_prov_dumped = seg_dumped["provenance"]
    assert "sourceType" in seg_prov_dumped
    assert "providerName" in seg_prov_dumped
    assert "hasLiveProvider" in seg_prov_dumped
    attr_dumped = seg_prov_dumped["attributes"]["duration"]
    assert "sourceType" in attr_dumped
    assert "providerName" in attr_dumped
    assert "isEstimate" in attr_dumped


def test_5_defaults_and_validation_behavior():
    """Verifies that defaults and validation behavior (e.g. date normalization) remain active."""
    # Defaults
    seg = JourneySegmentSchema(
        segment_id="s1",
        mode="auto",
        provider="p1",
        origin=LocationSchema(
            id="l1",
            name="A",
            city="C",
            type="landmark",
            coordinates=CoordinatesSchema(lat=1.0, lng=2.0),
        ),
        destination=LocationSchema(
            id="l2",
            name="B",
            city="C",
            type="landmark",
            coordinates=CoordinatesSchema(lat=1.1, lng=2.1),
        ),
        departure_time="2026-11-07T10:00:00",
        arrival_time="2026-11-07T10:15:00",
        duration_minutes=15,
        price=80.0,
        distance_km=5.0,
        carbon_kg=0.5,
        comfort_score=7.0,
    )
    assert seg.currency == "INR"
    assert seg.transfer_buffer_minutes == 15

    ai = AIExplanationSchema(
        summary="S",
        rank_reason="R",
        score=75.0,
    )
    assert ai.trade_offs == []
    assert ai.cost_vs_fastest_saving is None
    assert ai.duration_diff_minutes is None
    assert ai.is_fare_estimated is True
    assert ai.is_duration_estimated is True
    assert ai.is_availability_verified is False

    # Date normalization
    req_tomorrow = JourneySearchRequest(
        origin="A",
        destination="B",
        departure_date="tomorrow",
    )
    expected_tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    assert req_tomorrow.departure_date == expected_tomorrow

    req_today = JourneySearchRequest(
        origin="A",
        destination="B",
        departure_date="TODAY",
    )
    expected_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert req_today.departure_date == expected_today

    with pytest.raises(ValueError, match="Departure date must be in YYYY-MM-DD format"):
        JourneySearchRequest(
            origin="A",
            destination="B",
            departure_date="not-a-valid-date",
        )
