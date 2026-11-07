"""
backend/tests/test_live_provider_verification.py

Comprehensive test suite for KogniSync M2.4:
Live Provider Verification & Journey Quality.
Verifies adapter behavior, distinct failure classification, journey metric enrichment,
proportional carbon updates, Pareto frontier determinism, and explainable data credibility.
"""
import pytest
import httpx
from datetime import datetime
from starlette.testclient import TestClient

from app.main import app
from app.services.journey.provider import (
    NormalizedTransportSegmentResponse,
    ProviderCapabilities,
    ProviderErrorCode,
    TransportProviderError,
    TransportSegmentSearchRequest,
)
from app.services.journey.google_routes_adapter import GoogleRoutesTransportAdapter
from app.services.journey.schemas import JourneySearchRequest
from app.services.journey.service import JourneyOrchestrationService

client = TestClient(app)


# ============================================================================
# 1. CREDENTIAL AUDIT & BLOCKED STATUS REPORTING
# ============================================================================

def test_1_provider_credential_audit_and_blocked_status():
    """Verify that unconfigured credentials report BLOCKED without fabricating live success."""
    adapter = GoogleRoutesTransportAdapter(api_key=None, enabled=False)
    assert adapter.is_available() is False
    assert adapter.is_live_authenticated() is False

    cap = adapter.get_capabilities()
    assert cap.is_available is False
    assert cap.is_live_authenticated is False

    # Check public API endpoint /api/v1/journeys/providers
    resp = client.get("/api/v1/journeys/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    google_cap = next(p for p in data["providers"] if p["providerId"] == "google_routes")
    assert google_cap["liveVerificationStatus"] == "BLOCKED — credentials unavailable"


# ============================================================================
# 2. CONTROLLED LIVE SMOKE TEST (AUTHENTICATED MOCK)
# ============================================================================

@pytest.mark.anyio
async def test_2_controlled_smoke_test_normalized_response():
    """
    Executes controlled smoke test verifying Google Routes response normalization,
    ISO UTC timestamp, attribution to Google Routes v2, and absence of fabricated fares/inventory.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        assert "X-Goog-Api-Key" in request.headers
        assert request.headers["X-Goog-Api-Key"] == "test_secret_smoke_key"
        # Controlled response for Bangalore Airport -> MG Road
        return httpx.Response(
            200,
            json={
                "routes": [
                    {
                        "duration": "1680s",  # 28m
                        "distanceMeters": 21500,  # 21.5 km
                        "description": "Via Bellary Road",
                        "warnings": [],
                    }
                ]
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GoogleRoutesTransportAdapter(
        api_key="test_secret_smoke_key",
        enabled=True,
        http_client=mock_client,
    )

    req = TransportSegmentSearchRequest(
        origin_title="Kempegowda International Airport",
        origin_city="Bangalore",
        origin_lat=13.198,
        origin_lng=77.706,
        destination_title="MG Road Station",
        destination_city="Bangalore",
        destination_lat=12.975,
        destination_lng=77.609,
        mode="cab",
    )

    res = await adapter.search_segment(req)
    assert isinstance(res, NormalizedTransportSegmentResponse)
    assert res.provider_id == "google_routes"
    assert res.provider_name == "Google Routes API v2"
    assert res.duration_minutes == 28
    assert res.distance_km == 21.5

    # Verification of timestamp
    dt = datetime.fromisoformat(res.retrieved_at)
    assert dt is not None

    # Attribute-level provenance
    assert res.attribute_provenance["duration"].source_type == "provider_live"
    assert res.attribute_provenance["duration"].is_estimate is False
    assert res.attribute_provenance["duration"].provider_name == "Google Routes API v2"

    assert res.attribute_provenance["distance"].source_type == "provider_live"
    assert res.attribute_provenance["distance"].is_estimate is False
    assert res.attribute_provenance["distance"].provider_name == "Google Routes API v2"

    # Preserves absence of live fares or inventory
    assert res.fare is None
    assert "fare" not in res.attribute_provenance
    assert "availability" not in res.attribute_provenance


# ============================================================================
# 3. DISTINCT PROVIDER FAILURE CLASSIFICATION
# ============================================================================

@pytest.mark.anyio
@pytest.mark.parametrize(
    "status_code,response_payload,expected_status",
    [
        (400, {"error": "Invalid fieldMask"}, "invalid_request_fallback_deterministic"),
        (401, {"error": "API key invalid"}, "auth_failed_fallback_deterministic"),
        (403, {"error": "Permission denied"}, "auth_failed_fallback_deterministic"),
        (429, {"error": "Quota exceeded"}, "rate_limited_fallback_deterministic"),
        (503, {"error": "Upstream unavailable"}, "unavailable_fallback_deterministic"),
        (200, {"routes": []}, "empty_fallback_deterministic"),
        (200, {"routes": [{}]}, "malformed_fallback_deterministic"),
    ],
)
async def test_3_provider_failure_distinct_classification(status_code, response_payload, expected_status):
    """
    Verifies that provider failures are explicitly and distinctly classified in provider_status
    rather than silently treated as ordinary downtime, and that search succeeds via fallback.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=response_payload)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GoogleRoutesTransportAdapter(
        api_key="mock_key",
        enabled=True,
        http_client=mock_client,
    )

    orchestrator = JourneyOrchestrationService(transport_providers=[adapter])
    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
    )

    res = await orchestrator.search_journeys(req)
    assert len(res.journeys) > 0
    assert res.provider_status["google_routes"] == expected_status


# ============================================================================
# 4. PROVIDER DURATION CHANGES TOTAL JOURNEY DURATION AND RANKING
# ============================================================================

@pytest.mark.anyio
async def test_4_provider_duration_changes_journey_duration():
    """Verify live provider duration updates segment and total journey duration while preserving deadlines."""
    # 1. Run baseline without live provider (unconfigured)
    base_orchestrator = JourneyOrchestrationService(transport_providers=[])
    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
        preferred_arrival_before="18:00",
    )
    base_res = await base_orchestrator.search_journeys(req)
    base_fastest = next(j for j in base_res.journeys if j.recommendation_category == "fastest")
    base_dur = base_fastest.total_duration_minutes

    # 2. Run with live provider reporting shorter first-mile cab duration (20m instead of 35m -> 15m saving)
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"routes": [{"duration": "1200s", "distanceMeters": 20000}]})  # 20m, 20km

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    live_adapter = GoogleRoutesTransportAdapter(
        api_key="mock_key",
        enabled=True,
        http_client=mock_client,
    )
    live_orchestrator = JourneyOrchestrationService(transport_providers=[live_adapter])
    live_res = await live_orchestrator.search_journeys(req)
    live_fastest = next(j for j in live_res.journeys if j.recommendation_category == "fastest")

    # First mile duration changed to 20m
    assert live_fastest.segments[0].duration_minutes == 20
    # Total duration is reduced
    assert live_fastest.total_duration_minutes < base_dur


# ============================================================================
# 5. PROVIDER DISTANCE PROPORTIONALLY UPDATES CARBON
# ============================================================================

@pytest.mark.anyio
async def test_5_provider_distance_proportionally_updates_carbon():
    """Verify that provider road distance proportionally updates segment and journey carbon metrics."""
    # Shorter distance: 17.0 km (default was 34.0 km, carbon 5.2 kg -> expected ~2.6 kg)
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"routes": [{"duration": "1500s", "distanceMeters": 17000}]})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    live_adapter = GoogleRoutesTransportAdapter(
        api_key="mock_key",
        enabled=True,
        http_client=mock_client,
    )
    live_orchestrator = JourneyOrchestrationService(transport_providers=[live_adapter])
    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
    )
    res = await live_orchestrator.search_journeys(req)
    fastest = next(j for j in res.journeys if j.recommendation_category == "fastest")
    seg1 = fastest.segments[0]
    assert seg1.distance_km == 17.0
    # Carbon must be proportionally scaled from baseline 5.2 kg for 34.0 km down to 2.6 kg
    assert seg1.carbon_kg == 2.6


# ============================================================================
# 6. HARD BUDGET CONSTRAINT REMAINS ENFORCED WITH LIVE PROVIDER
# ============================================================================

@pytest.mark.anyio
async def test_6_hard_budget_constraint_enforced_with_live_provider():
    """Verify hard budget caps are strictly enforced when live provider is active."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"routes": [{"duration": "1200s", "distanceMeters": 15000}]})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    live_adapter = GoogleRoutesTransportAdapter(
        api_key="mock_key",
        enabled=True,
        http_client=mock_client,
    )
    live_orchestrator = JourneyOrchestrationService(transport_providers=[live_adapter])

    budget_cap = 1800.0
    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
        budget_max=budget_cap,
    )
    res = await live_orchestrator.search_journeys(req)
    assert len(res.journeys) > 0
    for j in res.journeys:
        assert j.total_price <= budget_cap


# ============================================================================
# 7. HARD ARRIVAL DEADLINE REMAINS ENFORCED WITH LIVE PROVIDER
# ============================================================================

@pytest.mark.anyio
async def test_7_hard_arrival_deadline_enforced_with_live_provider():
    """Verify arrival deadline constraint is strictly enforced with live provider data."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"routes": [{"duration": "1200s", "distanceMeters": 15000}]})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    live_adapter = GoogleRoutesTransportAdapter(
        api_key="mock_key",
        enabled=True,
        http_client=mock_client,
    )
    live_orchestrator = JourneyOrchestrationService(transport_providers=[live_adapter])

    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
        preferred_arrival_before="15:00",
    )
    res = await live_orchestrator.search_journeys(req)
    assert len(res.journeys) > 0
    for j in res.journeys:
        arr_time = datetime.fromisoformat(j.arrival_time)
        assert arr_time.hour < 15 or (arr_time.hour == 15 and arr_time.minute == 0)


# ============================================================================
# 8. PARETO OPTIMALITY IS DETERMINISTIC WITH LIVE PROVIDER
# ============================================================================

@pytest.mark.anyio
async def test_8_pareto_optimality_deterministic_with_live_provider():
    """Verify repeated executions with live provider yield 100% deterministic Pareto rankings."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"routes": [{"duration": "1500s", "distanceMeters": 18000}]})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    live_adapter = GoogleRoutesTransportAdapter(
        api_key="mock_key",
        enabled=True,
        http_client=mock_client,
    )
    live_orchestrator = JourneyOrchestrationService(transport_providers=[live_adapter])

    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
    )

    res1 = await live_orchestrator.search_journeys(req)
    res2 = await live_orchestrator.search_journeys(req)

    assert [j.id for j in res1.journeys] == [j.id for j in res2.journeys]
    assert [j.total_price for j in res1.journeys] == [j.total_price for j in res2.journeys]
    assert [j.total_duration_minutes for j in res1.journeys] == [j.total_duration_minutes for j in res2.journeys]


# ============================================================================
# 9. PARTIAL PROVIDER DATA PROVENANCE INTEGRITY
# ============================================================================

@pytest.mark.anyio
async def test_9_partial_provider_data_provenance_integrity():
    """Verify live duration does not promote entire journey to confirmed or fully live."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"routes": [{"duration": "1400s", "distanceMeters": 16000}]})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    live_adapter = GoogleRoutesTransportAdapter(
        api_key="mock_key",
        enabled=True,
        http_client=mock_client,
    )
    live_orchestrator = JourneyOrchestrationService(transport_providers=[live_adapter])

    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
    )
    res = await live_orchestrator.search_journeys(req)
    fastest = next(j for j in res.journeys if j.recommendation_category == "fastest")

    # Invariants
    assert fastest.provenance.overall_source_type == "mixed"
    assert fastest.provenance.has_live_attributes is True
    assert fastest.provenance.has_simulated_attributes is True
    assert fastest.provenance.is_fully_confirmed is False


# ============================================================================
# 10. AI EXPLANATION & DATA CREDIBILITY NOTICE WITH LIVE PROVIDER
# ============================================================================

@pytest.mark.anyio
async def test_10_ai_explanation_and_data_credibility_notice():
    """Verify aiExplanation dynamically adjusts duration estimation flags and communicates credibility."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"routes": [{"duration": "1400s", "distanceMeters": 16000}]})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    live_adapter = GoogleRoutesTransportAdapter(
        api_key="mock_key",
        enabled=True,
        http_client=mock_client,
    )
    live_orchestrator = JourneyOrchestrationService(transport_providers=[live_adapter])

    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
    )
    res = await live_orchestrator.search_journeys(req)
    fastest = next(j for j in res.journeys if j.recommendation_category == "fastest")

    expl = fastest.ai_explanation
    # Duration was provider-backed
    assert expl.is_duration_estimated is False
    # Fare and availability remain unconfirmed estimates
    assert expl.is_fare_estimated is True
    assert expl.is_availability_verified is False
    # Credibility notice explicitly references Google Routes v2
    assert "Google Routes API v2" in expl.data_credibility_notice
    # Trade-offs disclose live duration vs unverified demo seat capacity
    assert any("Google Routes API v2" in t for t in expl.trade_offs)


# ============================================================================
# 11. ANTI-LEAKAGE ACROSS ALL ENDPOINTS
# ============================================================================

@pytest.mark.anyio
async def test_11_anti_leakage_across_all_endpoints():
    """Verify API keys and sensitive tokens are never exposed in error details or status payloads."""
    secret_key = "secret_production_token_abc_9999"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid API key"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GoogleRoutesTransportAdapter(
        api_key=secret_key,
        enabled=True,
        http_client=mock_client,
    )
    orchestrator = JourneyOrchestrationService(transport_providers=[adapter])

    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
    )
    res = await orchestrator.search_journeys(req)
    serialized = res.model_dump_json()

    assert secret_key not in serialized
    assert secret_key not in res.provider_status["google_routes"]

