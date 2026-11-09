"""
backend/tests/test_disruption_intelligence.py

Comprehensive test suite for Real-Time Journey Disruption Intelligence (Milestone M3.7).
Tests event normalization, route-to-disruption spatial matching, impact assessment,
connection risk calculations, Pareto recovery recommendations, and inventory immutability.
"""
import pytest
from datetime import datetime, timezone, timedelta
from app.services.disruption.schemas import (
    DisruptionEvent,
    DisruptedSegmentImpact,
    JourneyDisruptionAssessment,
    RecoveryRecommendation,
    DisruptionRecoveryResponse,
    DisruptionProviderCapability,
)
from app.services.disruption.providers.base import DisruptionProvider
from app.services.disruption.providers.simulation import SimulatedDisruptionProvider
from app.services.disruption.providers.live_traffic import LiveTrafficIncidentProvider
from app.services.disruption.providers.manager import DisruptionProviderRegistry
from app.services.disruption.matcher import (
    RouteDisruptionMatcher,
    haversine_km,
    point_to_segment_distance_km,
)
from app.services.disruption.assessment import JourneyImpactAssessor
from app.services.disruption.recovery import JourneyRecoveryEngine
from app.services.disruption.service import DisruptionIntelligenceService
from app.services.journey.schemas import (
    AIExplanationSchema,
    CoordinatesSchema,
    JourneySchema,
    JourneySegmentSchema,
    LocationSchema,
    OptimizationWeightsInput,
    SegmentAvailabilitySchema,
    SegmentProvenanceSchema,
)
from app.services.maps.polyline import encode_polyline


# --- Test Fixtures ---

@pytest.fixture
def sample_location_blr():
    return LocationSchema(
        id="loc-blr-ksr",
        name="KSR Bengaluru City Junction",
        city="Bengaluru",
        type="railway_station",
        coordinates=CoordinatesSchema(lat=12.9781, lng=77.5695),
    )


@pytest.fixture
def sample_location_silk_board():
    return LocationSchema(
        id="loc-blr-silkboard",
        name="Central Silk Board",
        city="Bengaluru",
        type="landmark",
        coordinates=CoordinatesSchema(lat=12.9176, lng=77.6238),
    )


@pytest.fixture
def sample_location_sakleshpur():
    return LocationSchema(
        id="loc-sakleshpur",
        name="Sakleshpur Ghat Section (NH-75)",
        city="Hassan",
        type="landmark",
        coordinates=CoordinatesSchema(lat=12.8797, lng=75.6425),
    )


@pytest.fixture
def sample_location_mangaluru():
    return LocationSchema(
        id="loc-mangaluru",
        name="Mangaluru Central",
        city="Mangaluru",
        type="railway_station",
        coordinates=CoordinatesSchema(lat=12.8698, lng=74.8430),
    )


@pytest.fixture
def sample_location_udupi():
    return LocationSchema(
        id="loc-udupi",
        name="Udupi Bus Stand",
        city="Udupi",
        type="bus_terminal",
        coordinates=CoordinatesSchema(lat=13.3409, lng=74.7421),
    )


@pytest.fixture
def sample_multimodal_journey(
    sample_location_silk_board,
    sample_location_blr,
    sample_location_mangaluru,
    sample_location_udupi,
):
    """
    Multimodal Journey:
    Leg 1: Silk Board -> KSR Bengaluru (Cab, 40 min)
    Leg 2: KSR Bengaluru -> Mangaluru (Train/Cab, 300 min)
    Leg 3: Mangaluru -> Udupi (Bus, 60 min)
    """
    # Create simple polyline for Leg 1
    poly_leg1 = encode_polyline(
        [
            (12.9176, 77.6238),
            (12.9350, 77.6100),
            (12.9600, 77.5850),
            (12.9781, 77.5695),
        ],
        precision=6,
    )
    # Create polyline for Leg 2 (via Hassan/Sakleshpur on NH-75)
    poly_leg2 = encode_polyline(
        [
            (12.9781, 77.5695),
            (13.0000, 76.1000),  # Hassan
            (12.8797, 75.6425),  # Sakleshpur Shiradi Ghat
            (12.8698, 74.8430),  # Mangaluru
        ],
        precision=6,
    )

    t0 = datetime.now(timezone.utc)
    t1 = t0 + timedelta(minutes=45)
    t2 = t1 + timedelta(minutes=20)  # 20 min transfer buffer at KSR
    t3 = t2 + timedelta(minutes=300)
    t4 = t3 + timedelta(minutes=30)  # 30 min transfer buffer at Mangaluru
    t5 = t4 + timedelta(minutes=60)

    seg1 = JourneySegmentSchema(
        segment_id="seg-1-cab",
        sequence=1,
        mode="cab",
        provider="Ola Cabs",
        vehicle_name="Prime Sedan",
        origin=sample_location_silk_board,
        destination=sample_location_blr,
        departure_time=t0.isoformat(),
        arrival_time=t1.isoformat(),
        duration_minutes=45,
        price=350.0,
        distance_km=15.0,
        carbon_kg=3.2,
        comfort_score=7.5,
        transfer_buffer_minutes=20,
        encoded_polyline=poly_leg1,
        is_live_geometry=True,
    )

    seg2 = JourneySegmentSchema(
        segment_id="seg-2-road",
        sequence=2,
        mode="bus",
        provider="KSRTC FlyBus",
        vehicle_name="Airavat Club Class",
        origin=sample_location_blr,
        destination=sample_location_mangaluru,
        departure_time=t2.isoformat(),
        arrival_time=t3.isoformat(),
        duration_minutes=300,
        price=850.0,
        distance_km=350.0,
        carbon_kg=14.5,
        comfort_score=8.0,
        transfer_buffer_minutes=30,
        encoded_polyline=poly_leg2,
        is_live_geometry=True,
    )

    seg3 = JourneySegmentSchema(
        segment_id="seg-3-bus",
        sequence=3,
        mode="bus",
        provider="Canara Pinto Travels",
        vehicle_name="Local Express",
        origin=sample_location_mangaluru,
        destination=sample_location_udupi,
        departure_time=t4.isoformat(),
        arrival_time=t5.isoformat(),
        duration_minutes=60,
        price=120.0,
        distance_km=55.0,
        carbon_kg=2.5,
        comfort_score=6.5,
        transfer_buffer_minutes=15,
        encoded_polyline=None,
        is_live_geometry=False,
    )

    return JourneySchema(
        id="jny-demo-silkboard-to-udupi",
        title="Bengaluru to Udupi Multimodal Express",
        origin=sample_location_silk_board,
        destination=sample_location_udupi,
        departure_time=t0.isoformat(),
        arrival_time=t5.isoformat(),
        total_duration_minutes=455,
        total_price=1320.0,
        total_transfers=2,
        modes=["cab", "bus"],
        segments=[seg1, seg2, seg3],
        carbon_kg=20.2,
        comfort_score=7.4,
        recommendation_category="best_value",
        is_pareto_optimal=True,
        ai_explanation=AIExplanationSchema(
            summary="Fastest road and highway connection to coastal Karnataka.",
            trade_offs=["Balanced price and transfer comfort."],
            rank_reason="Optimal Pareto alternative",
            score=88.0,
        ),
    )


# --- 1. Event Normalization & Schema Tests ---

def test_disruption_event_defaults_and_validation():
    now_iso = datetime.now(timezone.utc).isoformat()
    event = DisruptionEvent(
        id="ev-1",
        title="Test Incident",
        description="Test description",
        valid_from=now_iso,
        observed_at=now_iso,
        last_verified_at=now_iso,
    )
    assert event.id == "ev-1"
    assert event.severity == "moderate"
    assert event.status == "active"
    assert event.provenance == "simulated"
    assert event.confidence == 1.0
    assert event.estimated_delay_minutes == 0


def test_disruption_event_camel_case_aliases():
    """Verify serialization aliases for camelCase frontend alignment."""
    now_iso = datetime.now(timezone.utc).isoformat()
    event = DisruptionEvent(
        id="ev-alias",
        source="simulation_engine",
        source_id="DEMO-1",
        event_type="road_closure",
        severity="critical",
        title="Closure",
        description="Desc",
        valid_from=now_iso,
        observed_at=now_iso,
        last_verified_at=now_iso,
        estimated_delay_minutes=60,
    )
    dumped = event.model_dump(by_alias=True)
    assert dumped["eventType"] == "road_closure"
    assert dumped["sourceId"] == "DEMO-1"
    assert dumped["estimatedDelayMinutes"] == 60
    assert dumped["validFrom"] == now_iso


def test_provider_capability_discovery():
    sim_provider = SimulatedDisruptionProvider()
    cap = sim_provider.get_capabilities()
    assert cap.name == "simulation_engine"
    assert cap.is_available is True
    assert cap.provenance_source == "simulated"
    assert "cab" in cap.supported_modes
    assert "train" in cap.supported_modes

    live_provider = LiveTrafficIncidentProvider(api_key=None)
    live_cap = live_provider.get_capabilities()
    assert live_cap.is_available is False
    assert "BLOCKED — credentials unavailable" in live_cap.status_notice


# --- 2. Route Matching Tests ---

def test_haversine_and_segment_distance():
    # Bangalore to Chennai is ~290 km
    d = haversine_km(12.9781, 77.5695, 13.0827, 80.2707)
    assert 280.0 < d < 305.0

    # Point directly on line segment (distance ~ 0 km)
    p_dist = point_to_segment_distance_km(
        12.9250, 77.6160,
        12.9176, 77.6238,
        12.9350, 77.6100,
    )
    assert p_dist < 0.2


def test_route_matching_exact_geometry(sample_multimodal_journey):
    matcher = RouteDisruptionMatcher(road_tolerance_km=2.0)
    sim_provider = SimulatedDisruptionProvider()

    # Shiradi Ghat landslide event
    shiradi_event = sim_provider.get_demo_shiradi_ghat_event()

    matched = matcher.match_events_to_segments(
        events=[shiradi_event],
        segments=sample_multimodal_journey.segments,
    )

    # Leg 2 passes through Sakleshpur Shiradi Ghat, so it must match
    assert len(matched["seg-2-road"]) == 1
    match_result = matched["seg-2-road"][0]
    assert match_result.match_type == "exact_geometry"
    assert match_result.min_distance_km <= 2.0
    assert match_result.event.id == "sim-disrupt-nh75-shiradi-ghat"

    # Leg 1 and Leg 3 are not in Shiradi Ghat, must not match
    assert len(matched["seg-1-cab"]) == 0
    assert len(matched["seg-3-bus"]) == 0


def test_route_matching_incompatible_transport_mode(sample_multimodal_journey):
    matcher = RouteDisruptionMatcher()
    sim_provider = SimulatedDisruptionProvider()

    # Create rail disruption at Silk Board (where only cab runs)
    now_iso = datetime.now(timezone.utc).isoformat()
    rail_event = DisruptionEvent(
        id="ev-rail-silkboard",
        source="test",
        event_type="transport_delay",
        severity="high",
        title="Rail Track Delay",
        description="Rail only",
        affected_modes=["train", "metro"],  # Leg 1 is cab, so incompatible
        point=CoordinatesSchema(lat=12.9176, lng=77.6238),
        radius_meters=3000.0,
        valid_from=now_iso,
        observed_at=now_iso,
        last_verified_at=now_iso,
    )

    matched = matcher.match_events_to_segments(
        events=[rail_event],
        segments=sample_multimodal_journey.segments,
    )
    # Leg 1 mode is 'cab', so rail event must NOT match
    assert len(matched["seg-1-cab"]) == 0


def test_route_matching_expired_event(sample_multimodal_journey):
    matcher = RouteDisruptionMatcher()
    past_iso = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    expired_event = DisruptionEvent(
        id="ev-expired",
        source="test",
        event_type="road_closure",
        severity="critical",
        title="Old Road Closure",
        description="Already cleared",
        status="resolved",  # Resolved status
        affected_modes=["cab"],
        point=CoordinatesSchema(lat=12.9176, lng=77.6238),
        valid_from=past_iso,
        valid_until=past_iso,
        observed_at=past_iso,
        last_verified_at=past_iso,
    )

    matched = matcher.match_events_to_segments(
        events=[expired_event],
        segments=sample_multimodal_journey.segments,
    )
    assert len(matched["seg-1-cab"]) == 0


# --- 3. Impact Assessment Tests ---

def test_impact_assessment_no_disruptions(sample_multimodal_journey):
    assessor = JourneyImpactAssessor()
    assessment = assessor.assess_journey(
        journey=sample_multimodal_journey,
        events=[],
    )
    assert assessment.is_disrupted is False
    assert assessment.overall_impact_level == "none"
    assert assessment.total_estimated_delay_minutes == 0
    assert assessment.affected_segment_count == 0
    assert assessment.critical_connection_risk_count == 0
    assert "No disruptions" in assessment.summary


def test_impact_assessment_critical_disruption(sample_multimodal_journey):
    assessor = JourneyImpactAssessor()
    sim_provider = SimulatedDisruptionProvider()
    shiradi_event = sim_provider.get_demo_shiradi_ghat_event()

    assessment = assessor.assess_journey(
        journey=sample_multimodal_journey,
        events=[shiradi_event],
    )

    assert assessment.is_disrupted is True
    assert assessment.overall_impact_level == "critical"
    assert assessment.total_estimated_delay_minutes == 180
    assert assessment.affected_segment_count == 1
    assert assessment.provenance == "simulated"
    assert assessment.notice is not None and "SIMULATED DISRUPTION" in assessment.notice

    # Check that Leg 2 has critical impact
    leg2_impact = next(imp for imp in assessment.segment_impacts if imp.segment_id == "seg-2-road")
    assert leg2_impact.impact_level == "critical"
    assert leg2_impact.estimated_delay_minutes == 180
    # Because Leg 2 is delayed by 180 min and transfer buffer at Mangaluru is only 30 min,
    # connection to Leg 3 is critical
    assert leg2_impact.subsequent_transfer_risk == "critical"
    assert leg2_impact.transfer_buffer_reduction_minutes > 0


def test_impact_assessment_moderate_urban_delay(sample_multimodal_journey):
    assessor = JourneyImpactAssessor()
    sim_provider = SimulatedDisruptionProvider()
    silk_board_event = sim_provider.get_demo_silk_board_event()

    assessment = assessor.assess_journey(
        journey=sample_multimodal_journey,
        events=[silk_board_event],
    )

    assert assessment.is_disrupted is True
    assert assessment.total_estimated_delay_minutes == 45

    leg1_impact = next(imp for imp in assessment.segment_impacts if imp.segment_id == "seg-1-cab")
    assert leg1_impact.estimated_delay_minutes == 45
    # Original transfer buffer at KSR was 20 min, delay is 45 min -> buffer eroded, transfer critical!
    assert leg1_impact.subsequent_transfer_risk == "critical"


# --- 4. Recovery Engine Tests ---

def test_recovery_engine_generates_viable_alternatives(sample_multimodal_journey):
    assessor = JourneyImpactAssessor()
    recovery_engine = JourneyRecoveryEngine()
    sim_provider = SimulatedDisruptionProvider()

    # Disrupted by Shiradi Ghat landslide
    shiradi_event = sim_provider.get_demo_shiradi_ghat_event()
    assessment = assessor.assess_journey(sample_multimodal_journey, [shiradi_event])

    response = recovery_engine.recover_journey(
        journey=sample_multimodal_journey,
        assessment=assessment,
    )

    assert response.feasible_alternatives_found is True
    assert len(response.recommendations) >= 1
    assert response.primary_recommendation is not None
    assert response.primary_recommendation.is_feasible is True
    assert response.primary_recommendation.manual_rebooking_required is True

    # Check alternative strategies generated
    strategies = [r.strategy for r in response.recommendations]
    assert "alternative_transport_mode" in strategies or "reroute_same_mode" in strategies

    # Verify that original journey was NOT mutated
    assert sample_multimodal_journey.id == "jny-demo-silkboard-to-udupi"
    assert sample_multimodal_journey.segments[1].mode == "bus"


def test_recovery_engine_respects_hard_budget_constraint(sample_multimodal_journey):
    assessor = JourneyImpactAssessor()
    recovery_engine = JourneyRecoveryEngine()
    sim_provider = SimulatedDisruptionProvider()

    shiradi_event = sim_provider.get_demo_shiradi_ghat_event()
    assessment = assessor.assess_journey(sample_multimodal_journey, [shiradi_event])

    # Extremely low budget: ₹500 (while original was ₹1320)
    response = recovery_engine.recover_journey(
        journey=sample_multimodal_journey,
        assessment=assessment,
        budget_max=500.0,
    )

    # Hard budget filter must NOT be silently relaxed
    assert response.feasible_alternatives_found is False
    assert response.primary_recommendation is not None
    assert response.primary_recommendation.strategy == "no_feasible_alternative"
    assert response.primary_recommendation.is_feasible is False
    assert any("budget" in note.lower() for note in response.primary_recommendation.feasibility_notes)


def test_recovery_engine_respects_arrival_deadline(sample_multimodal_journey):
    assessor = JourneyImpactAssessor()
    recovery_engine = JourneyRecoveryEngine()
    sim_provider = SimulatedDisruptionProvider()

    silk_board_event = sim_provider.get_demo_silk_board_event()
    assessment = assessor.assess_journey(sample_multimodal_journey, [silk_board_event])

    # Impossible arrival deadline: '01:00'
    response = recovery_engine.recover_journey(
        journey=sample_multimodal_journey,
        assessment=assessment,
        preferred_arrival_before="01:00",
    )

    assert response.feasible_alternatives_found is False
    assert response.primary_recommendation is not None
    assert response.primary_recommendation.strategy == "no_feasible_alternative"


# --- 5. Service & Registry End-to-End Tests ---

@pytest.mark.anyio
async def test_disruption_service_assess_and_recover_flow(sample_multimodal_journey):
    service = DisruptionIntelligenceService()

    # Assess journey
    assessment = await service.assess_journey_disruptions(
        journey=sample_multimodal_journey,
        include_simulated=True,
        scenario="shiradi_ghat",
    )
    assert assessment.is_disrupted is True
    assert assessment.highest_severity == "critical"

    # Recover journey
    recovery = await service.recover_journey(
        journey=sample_multimodal_journey,
        include_simulated=True,
        scenario="shiradi_ghat",
    )
    assert recovery.feasible_alternatives_found is True
    assert len(recovery.recommendations) > 0
    assert recovery.primary_recommendation is not None
    assert recovery.primary_recommendation.transfer_risk_mitigated is True


# --- 6. FastAPI Route Integration Tests ---

def test_api_disruptions_providers_and_get():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # Health
    res_health = client.get("/api/v1/disruptions/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"

    # Providers
    res_prov = client.get("/api/v1/disruptions/providers")
    assert res_prov.status_code == 200
    providers = res_prov.json()
    assert len(providers) >= 2
    prov_names = [p["name"] for p in providers]
    assert "simulation_engine" in prov_names
    assert "live_traffic_feed" in prov_names

    # Get disruptions
    res_disrupt = client.get("/api/v1/disruptions?include_simulated=true")
    assert res_disrupt.status_code == 200
    disruptions = res_disrupt.json()
    assert len(disruptions) >= 1
    assert any("NH-75" in d["title"] for d in disruptions)


def test_api_disruptions_assess_and_recover(sample_multimodal_journey):
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    journey_dict = sample_multimodal_journey.model_dump(by_alias=True)

    # POST /api/v1/disruptions/assess
    assess_payload = {
        "journey": journey_dict,
        "includeSimulated": True,
        "scenario": "shiradi_ghat",
    }
    res_assess = client.post("/api/v1/disruptions/assess", json=assess_payload)
    assert res_assess.status_code == 200
    data_assess = res_assess.json()
    assert data_assess["isDisrupted"] is True
    assert data_assess["highestSeverity"] == "critical"
    assert data_assess["totalEstimatedDelayMinutes"] == 180

    # POST /api/v1/disruptions/recover
    recover_payload = {
        "journey": journey_dict,
        "budgetMax": 2500.0,
        "includeSimulated": True,
        "scenario": "shiradi_ghat",
    }
    res_recover = client.post("/api/v1/disruptions/recover", json=recover_payload)
    assert res_recover.status_code == 200
    data_recover = res_recover.json()
    assert data_recover["feasibleAlternativesFound"] is True
    assert len(data_recover["recommendations"]) > 0
    assert data_recover["primaryRecommendation"]["manualRebookingRequired"] is True

    # POST /api/v1/journeys/{id}/assess-disruptions alias
    res_jny_assess = client.post(
        f"/api/v1/journeys/{sample_multimodal_journey.id}/assess-disruptions",
        json=assess_payload,
    )
    assert res_jny_assess.status_code == 200
    assert res_jny_assess.json()["isDisrupted"] is True

