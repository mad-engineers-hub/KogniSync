"""
backend/tests/test_disruption_intelligence.py

Comprehensive test suite for Real-Time Journey Disruption Intelligence (Milestone M3.7).
Tests event normalization, route-to-disruption spatial matching, impact assessment,
connection risk calculations, Pareto recovery recommendations, and inventory immutability.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
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

    with patch("app.core.config.settings.TOMTOM_API_KEY", None):
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

    with patch("app.core.config.settings.TOMTOM_TRAFFIC_ENABLED", False):
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


# --- 6. M3.7.1 Targeted Feasibility, Freshness & Tolerance Tests ---

def test_route_matching_tolerance_boundary():
    """Verifies matching behavior: directly on route, within tolerance, outside tolerance, unrelated."""
    matcher = RouteDisruptionMatcher(road_tolerance_km=2.0, hub_tolerance_km=5.0)

    # Road segment between (12.9000, 77.6000) and (12.9000, 77.7000)
    origin_loc = LocationSchema(
        id="loc-test-a",
        name="Point A",
        city="TestCity",
        type="landmark",
        coordinates=CoordinatesSchema(lat=12.9000, lng=77.6000),
    )
    dest_loc = LocationSchema(
        id="loc-test-b",
        name="Point B",
        city="TestCity",
        type="landmark",
        coordinates=CoordinatesSchema(lat=12.9000, lng=77.7000),
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    seg = JourneySegmentSchema(
        segment_id="seg-test-corridor",
        sequence=1,
        mode="cab",
        provider="TestCab",
        origin=origin_loc,
        destination=dest_loc,
        departure_time=now_iso,
        arrival_time=now_iso,
        duration_minutes=30,
        price=200.0,
        currency="INR",
        distance_km=11.0,
        carbon_kg=2.0,
        comfort_score=7.0,
        encoded_polyline=encode_polyline([(12.9000, 77.6000), (12.9000, 77.7000)], precision=5),
    )

    # 1. Point at offset ~1.8 km (approx 0.016 degrees latitude offset: 0.016 * 110.574 = 1.77 km)
    event_within = DisruptionEvent(
        id="ev-within",
        title="Event Within Tolerance",
        description="Within tolerance",
        affected_modes=["cab"],
        point=CoordinatesSchema(lat=12.9160, lng=77.6500),
        radius_meters=1000.0,
        valid_from=now_iso,
        observed_at=now_iso,
        last_verified_at=now_iso,
    )
    match_within = matcher.match_event_to_segment(event_within, seg)
    assert match_within is not None
    assert match_within.min_distance_km <= 2.0

    # 2. Point at offset ~2.4 km (approx 0.022 degrees lat offset: 0.022 * 110.574 = 2.43 km > 2.0 km)
    event_outside = DisruptionEvent(
        id="ev-outside",
        title="Event Outside Tolerance",
        description="Outside tolerance",
        affected_modes=["cab"],
        point=CoordinatesSchema(lat=12.9220, lng=77.6500),
        radius_meters=1000.0,
        valid_from=now_iso,
        observed_at=now_iso,
        last_verified_at=now_iso,
    )
    match_outside = matcher.match_event_to_segment(event_outside, seg)
    assert match_outside is None

    # 3. Unrelated road 15 km away
    event_unrelated = DisruptionEvent(
        id="ev-unrelated",
        title="Unrelated Incident",
        description="Far away",
        affected_modes=["cab"],
        point=CoordinatesSchema(lat=13.0400, lng=77.6500),
        radius_meters=1000.0,
        valid_from=now_iso,
        observed_at=now_iso,
        last_verified_at=now_iso,
    )
    match_unrelated = matcher.match_event_to_segment(event_unrelated, seg)
    assert match_unrelated is None


def test_route_matching_missing_geometry_and_invalid_coordinates():
    matcher = RouteDisruptionMatcher(road_tolerance_km=2.0)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Segment without encoded polyline
    origin = LocationSchema(
        id="loc-o", name="Origin", city="CityA", type="landmark",
        coordinates=CoordinatesSchema(lat=12.9000, lng=77.6000),
    )
    dest = LocationSchema(
        id="loc-d", name="Dest", city="CityB", type="landmark",
        coordinates=CoordinatesSchema(lat=12.9500, lng=77.6500),
    )
    seg_no_geom = JourneySegmentSchema(
        segment_id="seg-no-geom",
        sequence=1,
        mode="cab",
        provider="TestCab",
        origin=origin,
        destination=dest,
        departure_time=now_iso,
        arrival_time=now_iso,
        duration_minutes=30,
        price=150.0,
        currency="INR",
        distance_km=8.0,
        carbon_kg=1.5,
        comfort_score=7.0,
        encoded_polyline=None,  # Missing geometry
    )

    # Event without point or locations
    empty_event = DisruptionEvent(
        id="ev-empty",
        title="Empty Event",
        description="No point",
        affected_modes=["cab"],
        point=None,
        affected_locations=[],
        valid_from=now_iso,
        observed_at=now_iso,
        last_verified_at=now_iso,
    )
    assert matcher.match_event_to_segment(empty_event, seg_no_geom) is None


def test_event_lifecycle_resolved_and_expired_exclusion():
    matcher = RouteDisruptionMatcher()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    origin = LocationSchema(
        id="loc-o", name="Origin", city="CityA", type="landmark",
        coordinates=CoordinatesSchema(lat=12.9000, lng=77.6000),
    )
    dest = LocationSchema(
        id="loc-d", name="Dest", city="CityB", type="landmark",
        coordinates=CoordinatesSchema(lat=12.9100, lng=77.6100),
    )
    seg = JourneySegmentSchema(
        segment_id="seg-1",
        sequence=1,
        mode="cab",
        provider="TestCab",
        origin=origin,
        destination=dest,
        departure_time=(now + timedelta(hours=2)).isoformat(),
        arrival_time=(now + timedelta(hours=3)).isoformat(),
        duration_minutes=60,
        price=100.0,
        currency="INR",
        distance_km=5.0,
        carbon_kg=1.0,
        comfort_score=7.0,
    )

    # 1. Resolved event must be excluded
    resolved_event = DisruptionEvent(
        id="ev-res",
        title="Resolved Roadblock",
        description="Cleared",
        status="resolved",
        affected_modes=["cab"],
        point=CoordinatesSchema(lat=12.9050, lng=77.6050),
        valid_from=(now - timedelta(hours=2)).isoformat(),
        valid_until=(now + timedelta(hours=5)).isoformat(),
        observed_at=now_iso,
        last_verified_at=now_iso,
    )
    assert matcher.is_temporally_valid(resolved_event, seg) is False

    # 2. Expired event (valid_until in past) must be excluded
    expired_event = DisruptionEvent(
        id="ev-exp",
        title="Expired Congestion",
        description="Expired 10m ago",
        status="active",
        affected_modes=["cab"],
        point=CoordinatesSchema(lat=12.9050, lng=77.6050),
        valid_from=(now - timedelta(hours=2)).isoformat(),
        valid_until=(now - timedelta(minutes=10)).isoformat(),
        observed_at=now_iso,
        last_verified_at=now_iso,
    )
    assert matcher.is_temporally_valid(expired_event, seg) is False

    # 3. Disruption ending before segment departs must be excluded
    ended_before_seg = DisruptionEvent(
        id="ev-ended-before",
        title="Ends Before Leg",
        description="Ends in 1 hour; leg departs in 2 hours",
        status="active",
        affected_modes=["cab"],
        point=CoordinatesSchema(lat=12.9050, lng=77.6050),
        valid_from=now_iso,
        valid_until=(now + timedelta(hours=1)).isoformat(),
        observed_at=now_iso,
        last_verified_at=now_iso,
    )
    assert matcher.is_temporally_valid(ended_before_seg, seg) is False


def test_earlier_departure_disabled_when_underway(sample_multimodal_journey):
    """Guarantees earlier departure is NEVER recommended for a traveller already underway."""
    recovery_engine = JourneyRecoveryEngine()
    sim_provider = SimulatedDisruptionProvider()
    silk_event = sim_provider.get_demo_silk_board_event()

    # Artificially set first segment departure to 45 minutes in the past
    past_dep = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
    sample_multimodal_journey.segments[0].departure_time = past_dep

    impact = DisruptedSegmentImpact(
        segment_id="seg-1-cab",
        sequence=1,
        mode="cab",
        impact_level="high",
        estimated_delay_minutes=45,
        original_departure_time=past_dep,
        original_arrival_time=datetime.now(timezone.utc).isoformat(),
        estimated_arrival_time=datetime.now(timezone.utc).isoformat(),
        matching_events=[silk_event],
    )

    earlier_alt = recovery_engine._generate_earlier_departure_recovery(
        journey=sample_multimodal_journey,
        impact=impact,
    )
    # Must be None: traveller is already underway, earlier departure is physically impossible
    assert earlier_alt is None


def test_detour_alternative_provenance_is_deterministic_estimate(sample_multimodal_journey):
    """Guarantees detour candidates carry deterministic_estimate and never claim live road geometry."""
    recovery_engine = JourneyRecoveryEngine()
    sim_provider = SimulatedDisruptionProvider()
    shiradi_event = sim_provider.get_demo_shiradi_ghat_event()

    impact = DisruptedSegmentImpact(
        segment_id="seg-2-road",
        sequence=2,
        mode="bus",
        impact_level="critical",
        estimated_delay_minutes=180,
        original_departure_time=sample_multimodal_journey.segments[1].departure_time,
        original_arrival_time=sample_multimodal_journey.segments[1].arrival_time,
        estimated_arrival_time=sample_multimodal_journey.segments[1].arrival_time,
        matching_events=[shiradi_event],
    )

    detour_res = recovery_engine._generate_reroute_same_mode_recovery(
        journey=sample_multimodal_journey,
        impact=impact,
    )
    assert detour_res is not None
    recovered_journey, strategy, title, tradeoffs = detour_res
    assert strategy == "reroute_same_mode"
    assert "Charmadi" in title

    detour_seg = next(s for s in recovered_journey.segments if s.segment_id == "seg-2-road-rec-detour")
    assert detour_seg.is_live_geometry is False
    assert detour_seg.provenance is not None
    assert detour_seg.provenance.source_type == "deterministic_estimate"
    assert detour_seg.provenance.has_live_provider is False


def test_railway_alternative_is_estimated_and_unverified(sample_multimodal_journey):
    """Guarantees rail mode shifts are labeled as estimated alternatives with unverified inventory."""
    recovery_engine = JourneyRecoveryEngine()
    sim_provider = SimulatedDisruptionProvider()
    shiradi_event = sim_provider.get_demo_shiradi_ghat_event()

    impact = DisruptedSegmentImpact(
        segment_id="seg-2-road",
        sequence=2,
        mode="bus",
        impact_level="critical",
        estimated_delay_minutes=180,
        original_departure_time=sample_multimodal_journey.segments[1].departure_time,
        original_arrival_time=sample_multimodal_journey.segments[1].arrival_time,
        estimated_arrival_time=sample_multimodal_journey.segments[1].arrival_time,
        matching_events=[shiradi_event],
    )

    rail_res = recovery_engine._generate_alternative_mode_recovery(
        journey=sample_multimodal_journey,
        impact=impact,
    )
    assert rail_res is not None
    recovered_journey, strategy, title, tradeoffs = rail_res
    assert strategy == "alternative_transport_mode"
    assert "Estimated Alternative" in title
    assert any("IRCTC" in to for to in tradeoffs)
    assert any("unverified" in to for to in tradeoffs)

    # Check that AI explanation marks availability as unverified
    assert recovered_journey.ai_explanation.is_availability_verified is False
    assert recovered_journey.ai_explanation.is_fare_estimated is True


def test_downstream_transfer_buffer_states(sample_multimodal_journey):
    """Verifies safe, at_risk, critical connection risk and missing timestamps handling."""
    assessor = JourneyImpactAssessor()
    now = datetime.now(timezone.utc)

    seg_a = sample_multimodal_journey.segments[0]
    seg_b = sample_multimodal_journey.segments[1]

    # 1. Safe transfer (buffer = 30 min, required = 15)
    dep_b = now + timedelta(minutes=45)
    arr_a = now + timedelta(minutes=15)
    risk_safe, red_safe = assessor._evaluate_downstream_transfer(
        current_est_arr_dt=arr_a,
        next_segment=seg_b.model_copy(update={"departure_time": dep_b.isoformat()}),
        segment_buffer_min=15,
    )
    assert risk_safe == "safe"
    assert red_safe == 0

    # 2. At risk transfer (buffer = 10 min < required 15 min)
    dep_b_tight = now + timedelta(minutes=25)
    risk_tight, red_tight = assessor._evaluate_downstream_transfer(
        current_est_arr_dt=arr_a,
        next_segment=seg_b.model_copy(update={"departure_time": dep_b_tight.isoformat()}),
        segment_buffer_min=15,
    )
    assert risk_tight == "at_risk"
    assert red_tight == 5

    # 3. Negative buffer -> critical
    dep_b_neg = now + timedelta(minutes=5)  # Departs before incoming arrives at +15
    risk_neg, red_neg = assessor._evaluate_downstream_transfer(
        current_est_arr_dt=arr_a,
        next_segment=seg_b.model_copy(update={"departure_time": dep_b_neg.isoformat()}),
        segment_buffer_min=15,
    )
    assert risk_neg == "critical"
    assert red_neg > 15

    # 4. Missing timestamps -> unknown
    risk_unk, _ = assessor._evaluate_downstream_transfer(
        current_est_arr_dt=arr_a,
        next_segment=seg_b.model_copy(update={"departure_time": ""}),
        segment_buffer_min=15,
    )
    assert risk_unk == "unknown"


