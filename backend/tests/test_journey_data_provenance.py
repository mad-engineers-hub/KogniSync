"""
backend/tests/test_journey_data_provenance.py

Comprehensive test suite for KogniSync Journey Intelligence & Data Credibility (M2.1):
1. Deterministic attributes labeled correctly (fare, duration, schedules).
2. Provider-backed attributes retain live source metadata without conflation.
3. Mixed provenance leg representation (live duration + estimated fare).
4. Unknown provenance not falsely labeled as live.
5. Generated schedules clearly labeled as estimates.
6. Synthetic availability never represented as real inventory locks.
7. Provider timeout and error handling with graceful fallback and no exception leakage.
8. Empty provider response handling with clean fallback.
9. Hard constraints strictly preserved regardless of provenance.
10. Optimizer rankings and Pareto semantics remain intact.
11. API response compatibility (camelCase/snake_case and legacy client safety).
12. AI explanations explicitly communicate data credibility and unverified availability.
"""
import asyncio
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.journey.schemas import (
    AttributeProvenanceSchema,
    JourneySearchRequest,
)
from app.services.optimizer.schemas import OptimizationWeightsInput
from app.services.journey.service import (
    JourneyOrchestrationService,
    build_default_segment_provenance,
    build_journey_provenance,
)

client = TestClient(app)


def _sample_request(**kwargs) -> JourneySearchRequest:
    default_kwargs = {
        "origin": "Chennai",
        "destination": "Udupi",
        "departure_date": "2026-11-02",
        "preferred_arrival_before": "20:00",
        "budget_max": 6000.0,
        "passengers_count": 1,
        "weights": OptimizationWeightsInput(
            cost=0.25,
            duration=0.45,
            comfort=0.20,
            carbon=0.10,
        ),
        "natural_language_query": "Chennai to Udupi tomorrow before 8 PM speed priority",
    }
    default_kwargs.update(kwargs)
    return JourneySearchRequest(**default_kwargs)


# ============================================================================
# 1. DETERMINISTIC ATTRIBUTES LABELED CORRECTLY
# ============================================================================

@pytest.mark.anyio
async def test_1_deterministic_attributes_labeled_correctly():
    """Verify that default corridor attributes are strictly labeled as deterministic estimates."""
    service = JourneyOrchestrationService()
    req = _sample_request()
    res = await service.search_journeys(req)

    assert len(res.journeys) > 0

    for journey in res.journeys:
        assert journey.provenance is not None
        assert journey.provenance.is_fully_confirmed is False

        for seg in journey.segments:
            assert seg.provenance is not None
            prov = seg.provenance
            assert prov.is_estimate is True
            assert prov.source_type in ("deterministic_estimate", "simulated", "unknown")

            # Check individual attribute provenance
            assert "fare" in prov.attributes
            fare_prov = prov.attributes["fare"]
            assert fare_prov.is_estimate is True
            assert fare_prov.source_type == "deterministic_estimate"

            assert "duration" in prov.attributes
            dur_prov = prov.attributes["duration"]
            assert dur_prov.is_estimate is True
            assert dur_prov.source_type == "deterministic_estimate"

            assert "departure_time" in prov.attributes
            dep_prov = prov.attributes["departure_time"]
            assert dep_prov.is_estimate is True
            assert dep_prov.source_type == "deterministic_estimate"

            assert "arrival_time" in prov.attributes
            arr_prov = prov.attributes["arrival_time"]
            assert arr_prov.is_estimate is True
            assert arr_prov.source_type == "deterministic_estimate"

            assert "carbon" in prov.attributes
            carbon_prov = prov.attributes["carbon"]
            assert carbon_prov.is_estimate is True
            assert carbon_prov.source_type == "deterministic_estimate"


# ============================================================================
# 2. PROVIDER-BACKED ATTRIBUTES RETAIN SOURCE
# ============================================================================

@pytest.mark.anyio
async def test_2_provider_backed_attributes_retain_source():
    """Verify provider-backed live travel attributes retain their live source without conflation."""
    async def mock_live_flight_provider(context):
        return {
            "duration": AttributeProvenanceSchema(
                source_type="provider_live",
                provider_name="IndiGo Live ADS-B Tracking",
                is_estimate=False,
                notes="Real-time corridor flight duration verified by provider.",
            )
        }

    provider_registry = {
        "IndiGo Air Express": mock_live_flight_provider,
    }
    service = JourneyOrchestrationService(provider_registry=provider_registry)
    req = _sample_request()
    res = await service.search_journeys(req)

    # Locate the flight archetype journey
    flight_journey = next((j for j in res.journeys if any(s.mode == "flight" for s in j.segments)), None)
    assert flight_journey is not None

    flight_seg = next(s for s in flight_journey.segments if s.mode == "flight")
    assert flight_seg.provenance is not None
    assert flight_seg.provenance.has_live_provider is True

    # Duration should be live
    dur_prov = flight_seg.provenance.attributes["duration"]
    assert dur_prov.source_type == "provider_live"
    assert dur_prov.is_estimate is False
    assert dur_prov.provider_name == "IndiGo Live ADS-B Tracking"


# ============================================================================
# 3. MIXED PROVENANCE LEG REPRESENTATION
# ============================================================================

@pytest.mark.anyio
async def test_3_mixed_provenance_leg_representation():
    """Verify that a leg with live duration and estimated fare is labeled with mixed provenance."""
    async def mock_flight_timing_only(context):
        return {
            "duration": AttributeProvenanceSchema(
                source_type="provider_live",
                provider_name="IndiGo Live Air Traffic",
                is_estimate=False,
                notes="Live flight duration.",
            )
        }

    service = JourneyOrchestrationService(provider_registry={"IndiGo Air Express": mock_flight_timing_only})
    res = await service.search_journeys(_sample_request())

    flight_journey = next(j for j in res.journeys if any(s.mode == "flight" for s in j.segments))
    flight_seg = next(s for s in flight_journey.segments if s.mode == "flight")

    # In the flight leg: duration is live, but fare is still deterministic estimate
    assert flight_seg.provenance.attributes["duration"].source_type == "provider_live"
    assert flight_seg.provenance.attributes["duration"].is_estimate is False

    assert flight_seg.provenance.attributes["fare"].source_type == "deterministic_estimate"
    assert flight_seg.provenance.attributes["fare"].is_estimate is True

    # Because fare is not live, the leg overall MUST NOT be labeled wholly provider_live
    assert flight_seg.provenance.source_type != "provider_live"
    assert flight_seg.provenance.is_estimate is True
    assert flight_seg.provenance.has_live_provider is True

    # And the journey overall is mixed
    assert flight_journey.provenance.overall_source_type == "mixed"
    assert flight_journey.provenance.has_live_attributes is True
    assert flight_journey.provenance.has_simulated_attributes is True
    assert flight_journey.provenance.is_fully_confirmed is False


# ============================================================================
# 4. UNKNOWN PROVENANCE NOT FALSELY LABELED LIVE
# ============================================================================

@pytest.mark.anyio
async def test_4_unknown_provenance_not_falsely_labeled_live():
    """Verify unverified attributes retain 'unknown' and are never labeled as provider_live."""
    def mock_unknown_provider(context):
        return {
            "fare": AttributeProvenanceSchema(
                source_type="unknown",
                provider_name=None,
                is_estimate=True,
                notes="Fare could not be determined or verified from provider.",
            )
        }

    service = JourneyOrchestrationService(provider_registry={"IndiGo Air Express": mock_unknown_provider})
    res = await service.search_journeys(_sample_request())

    flight_journey = next(j for j in res.journeys if any(s.mode == "flight" for s in j.segments))
    flight_seg = next(s for s in flight_journey.segments if s.mode == "flight")

    fare_prov = flight_seg.provenance.attributes["fare"]
    assert fare_prov.source_type == "unknown"
    assert fare_prov.is_estimate is True
    assert flight_seg.provenance.source_type != "provider_live"
    assert flight_seg.provenance.has_live_provider is False


# ============================================================================
# 5. GENERATED SCHEDULES NOT REPRESENTED AS CONFIRMED
# ============================================================================

@pytest.mark.anyio
async def test_5_generated_schedules_not_represented_as_confirmed():
    """Verify generated departure and arrival times are explicitly marked as estimates."""
    service = JourneyOrchestrationService()
    res = await service.search_journeys(_sample_request())

    for journey in res.journeys:
        assert journey.provenance.is_fully_confirmed is False

        for seg in journey.segments:
            dep_prov = seg.provenance.attributes["departure_time"]
            arr_prov = seg.provenance.attributes["arrival_time"]

            assert dep_prov.is_estimate is True
            assert arr_prov.is_estimate is True
            assert "estimated" in dep_prov.notes.lower() or "estimate" in dep_prov.notes.lower()
            assert "estimated" in arr_prov.notes.lower() or "estimate" in arr_prov.notes.lower()


# ============================================================================
# 6. SYNTHETIC AVAILABILITY NEVER REAL INVENTORY
# ============================================================================

@pytest.mark.anyio
async def test_6_synthetic_availability_never_real_inventory():
    """Verify simulated availability is marked as synthetic and is_real_inventory is False."""
    service = JourneyOrchestrationService()
    res = await service.search_journeys(_sample_request())

    for journey in res.journeys:
        assert journey.ai_explanation.is_availability_verified is False

        for seg in journey.segments:
            assert seg.availability.is_real_inventory is False

            avail_prov = seg.provenance.attributes["availability"]
            assert avail_prov.source_type == "simulated"
            assert avail_prov.is_estimate is True
            assert "simulated" in avail_prov.notes.lower()


# ============================================================================
# 7. PROVIDER TIMEOUT AND ERROR HANDLING
# ============================================================================

@pytest.mark.anyio
async def test_7_provider_timeout_and_error_handling():
    """Verify slow or crashing external providers fall back gracefully without leaking errors."""
    async def timeout_provider(context):
        # Simulate long delay exceeding 3.0s boundary
        await asyncio.sleep(4.0)
        return {}

    def crashing_provider(context):
        # Sensitive credentials or stack details that must NOT leak to client
        raise ValueError("SecretKey=xyz123 database connection timed out")

    service = JourneyOrchestrationService(
        provider_registry={
            "IndiGo Air Express": timeout_provider,
            "Indian Railways Vande Bharat": crashing_provider,
        }
    )

    # Must complete safely and return standard candidates
    res = await service.search_journeys(_sample_request())
    assert len(res.journeys) > 0

    # Provider statuses must record fallbacks
    assert res.provider_status["IndiGo Air Express"] == "timeout_fallback_deterministic"
    assert res.provider_status["Indian Railways Vande Bharat"] == "error_fallback_deterministic"

    # Leak check: no secret keys or internal exception details anywhere in serialized response
    serialized = res.model_dump_json()
    assert "SecretKey" not in serialized
    assert "xyz123" not in serialized
    assert "Traceback" not in serialized


# ============================================================================
# 8. EMPTY PROVIDER RESPONSE HANDLING
# ============================================================================

@pytest.mark.anyio
async def test_8_empty_provider_response_handling():
    """Verify empty provider responses (None or {}) cleanly degrade to estimates."""
    async def empty_provider(context):
        return {}

    def none_provider(context):
        return None

    service = JourneyOrchestrationService(
        provider_registry={
            "IndiGo Air Express": empty_provider,
            "Indian Railways Vande Bharat": none_provider,
        }
    )

    res = await service.search_journeys(_sample_request())
    assert len(res.journeys) > 0
    assert res.provider_status["IndiGo Air Express"] == "empty_fallback_deterministic"
    assert res.provider_status["Indian Railways Vande Bharat"] == "empty_fallback_deterministic"


# ============================================================================
# 9. HARD CONSTRAINTS WITH PROVENANCE
# ============================================================================

@pytest.mark.anyio
async def test_9_hard_constraints_remain_intact():
    """Verify budget and arrival hard constraints remain strictly enforced with provenance."""
    service = JourneyOrchestrationService()

    # Impossible budget constraint (zero relaxation)
    res_zero = await service.search_journeys(_sample_request(budget_max=100.0))
    assert len(res_zero.journeys) == 0
    assert res_zero.eligible_candidates == 0

    # Strict arrival deadline constraint
    res_arr = await service.search_journeys(_sample_request(preferred_arrival_before="14:00"))
    assert len(res_arr.journeys) > 0
    for j in res_arr.journeys:
        arr_time = j.arrival_time.split("T")[1][:5]
        assert arr_time <= "14:00"


# ============================================================================
# 10. OPTIMIZER RANKINGS AND PARETO SEMANTICS INTACT
# ============================================================================

@pytest.mark.anyio
async def test_10_optimizer_rankings_and_pareto_semantics_intact():
    """Verify Pareto frontier and multi-objective scoring remain intact with provenance tracking."""
    service = JourneyOrchestrationService()
    res = await service.search_journeys(_sample_request())

    assert res.pareto_frontier_count > 0
    assert res.recommended_journey_id is not None

    for j in res.journeys:
        assert j.is_pareto_optimal is True
        assert 0.0 <= j.ai_explanation.score <= 100.0
        assert j.optimization is not None
        assert j.optimization.score > 0.0


# ============================================================================
# 11. API RESPONSE COMPATIBILITY
# ============================================================================

def test_11_api_response_compatibility():
    """Verify POST /api/v1/journeys/search provides provenance metadata in a backward-compatible format."""
    payload = {
        "origin": "Chennai",
        "destination": "Udupi",
        "departure_date": "2026-11-02",
        "preferred_arrival_before": "20:00",
        "budget_max": 5000.0,
        "passengers_count": 1,
        "weights": {
            "cost": 0.20,
            "duration": 0.50,
            "comfort": 0.20,
            "carbon": 0.10,
        },
    }
    response = client.post("/api/v1/journeys/search", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "journeys" in data
    assert len(data["journeys"]) > 0

    first_j = data["journeys"][0]
    # Legacy fields
    assert "id" in first_j
    assert "title" in first_j
    assert "totalPrice" in first_j
    assert "segments" in first_j
    assert "aiExplanation" in first_j

    # New provenance fields
    assert "provenance" in first_j
    assert "overallSourceType" in first_j["provenance"]
    assert first_j["provenance"]["isFullyConfirmed"] is False

    first_seg = first_j["segments"][0]
    assert "provenance" in first_seg
    assert "sourceType" in first_seg["provenance"]
    assert "attributes" in first_seg["provenance"]
    assert first_seg["availability"]["isRealInventory"] is False


# ============================================================================
# 12. EXPLANATIONS ACCURATELY REFLECT PROVENANCE
# ============================================================================

@pytest.mark.anyio
async def test_12_explanations_accurately_reflect_provenance():
    """Verify AI explanations explicitly communicate data credibility and unverified availability."""
    service = JourneyOrchestrationService()
    res = await service.search_journeys(_sample_request())

    for j in res.journeys:
        ai = j.ai_explanation
        assert ai.data_credibility_notice is not None
        assert len(ai.data_credibility_notice) > 10
        assert "estimate" in ai.data_credibility_notice.lower()

        assert ai.is_fare_estimated is True
        assert ai.is_duration_estimated is True
        assert ai.is_availability_verified is False

        # Tradeoffs contain explicit corridor warning
        assert any("corridor-modeled estimates" in t.lower() for t in ai.trade_offs)
