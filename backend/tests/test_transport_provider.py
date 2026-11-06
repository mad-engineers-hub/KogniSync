"""
backend/tests/test_transport_provider.py

Unit and integration tests for transport provider adapter architecture, Google Routes integration,
normalized responses, attribute-level provenance, resilient fallbacks, and error classification.
Part of KogniSync M2.3: Real Transport Provider Integration Foundation.
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
    TransportProvider,
    TransportProviderError,
    TransportSegmentSearchRequest,
)
from app.services.journey.google_routes_adapter import (
    GOOGLE_ROUTES_V2_URL,
    GoogleRoutesTransportAdapter,
)
from app.services.journey.schemas import (
    JourneySearchRequest,
    OptimizationWeightsInput,
)
from app.services.journey.service import (
    JourneyOrchestrationService,
)

client = TestClient(app)


# ============================================================================
# 1. PROVIDER INTERFACE & CAPABILITIES
# ============================================================================

def test_1_provider_interface_and_capabilities():
    """Verify TransportProvider interface properties, capability reporting, and mode support."""
    # Disabled provider
    adapter_disabled = GoogleRoutesTransportAdapter(api_key=None, enabled=False)
    assert adapter_disabled.provider_id == "google_routes"
    assert adapter_disabled.name == "Google Routes API v2"
    assert "cab" in adapter_disabled.supported_modes
    assert "rapido" in adapter_disabled.supported_modes
    assert "walk" in adapter_disabled.supported_modes
    assert adapter_disabled.is_available() is False
    assert adapter_disabled.is_live_authenticated() is False

    cap_disabled = adapter_disabled.get_capabilities()
    assert isinstance(cap_disabled, ProviderCapabilities)
    assert cap_disabled.is_available is False
    assert cap_disabled.is_live_authenticated is False
    assert "cab" in cap_disabled.supported_modes

    # Enabled provider with key
    adapter_enabled = GoogleRoutesTransportAdapter(api_key="test_key_123", enabled=True, timeout_seconds=4.0)
    assert adapter_enabled.is_available() is True
    assert adapter_enabled.is_live_authenticated() is True
    cap_enabled = adapter_enabled.get_capabilities()
    assert cap_enabled.is_available is True
    assert cap_enabled.is_live_authenticated is True
    assert cap_enabled.timeout_seconds == 4.0


# ============================================================================
# 2. PROVIDER AUTHENTICATION & REJECTION OF UNCONFIGURED STATE
# ============================================================================

@pytest.mark.anyio
async def test_2_google_routes_auth_failure_unconfigured():
    """Verify adapter raises AUTH_FAILURE when unconfigured or disabled."""
    adapter = GoogleRoutesTransportAdapter(api_key=None, enabled=False)
    req = TransportSegmentSearchRequest(
        origin_title="Majestic Railway Hub",
        origin_city="Bangalore",
        origin_lat=12.978,
        origin_lng=77.572,
        destination_title="Indiranagar",
        destination_city="Bangalore",
        destination_lat=12.978,
        destination_lng=77.640,
        mode="cab",
    )

    with pytest.raises(TransportProviderError) as exc_info:
        await adapter.search_segment(req)

    assert exc_info.value.code == ProviderErrorCode.AUTH_FAILURE
    assert exc_info.value.provider_id == "google_routes"


# ============================================================================
# 3. HTTP 401/403 AUTHENTICATION REJECTION
# ============================================================================

@pytest.mark.anyio
async def test_3_google_routes_auth_failure_http_401():
    """Verify HTTP 401/403 from Google Routes raises AUTH_FAILURE without leaking credentials."""
    secret_key = "sensitive_ai_za_sy_key_999"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Goog-Api-Key"] == secret_key
        return httpx.Response(401, json={"error": {"code": 401, "message": "API key not valid."}})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GoogleRoutesTransportAdapter(
        api_key=secret_key,
        enabled=True,
        http_client=mock_client,
    )

    req = TransportSegmentSearchRequest(
        origin_title="Majestic",
        origin_city="Bangalore",
        origin_lat=12.978,
        origin_lng=77.572,
        destination_title="Indiranagar",
        destination_city="Bangalore",
        destination_lat=12.978,
        destination_lng=77.640,
        mode="cab",
    )

    with pytest.raises(TransportProviderError) as exc_info:
        await adapter.search_segment(req)

    assert exc_info.value.code == ProviderErrorCode.AUTH_FAILURE
    # Ensure sensitive key is never in the exception message
    assert secret_key not in str(exc_info.value)


# ============================================================================
# 4. SUCCESSFUL NORMALIZED RESPONSE
# ============================================================================

@pytest.mark.anyio
async def test_4_google_routes_successful_normalized_response():
    """Verify HTTP 200 normalizes duration, distance, timestamps, and attribute provenance."""
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "routes": [
                {
                    "duration": "1680s",  # 28 minutes
                    "distanceMeters": 21500,  # 21.5 km
                    "description": "Via Old Madras Road",
                    "warnings": [],
                }
            ]
        }
        return httpx.Response(200, json=payload)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GoogleRoutesTransportAdapter(
        api_key="valid_test_key",
        enabled=True,
        http_client=mock_client,
    )

    req = TransportSegmentSearchRequest(
        origin_title="Kempegowda Airport",
        origin_city="Bangalore",
        origin_lat=13.198,
        origin_lng=77.706,
        destination_title="MG Road",
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
    assert res.mode == "cab"

    # Retrieved at must be valid ISO timestamp
    dt = datetime.fromisoformat(res.retrieved_at)
    assert dt is not None

    # Attribute provenance verification
    assert "duration" in res.attribute_provenance
    assert "distance" in res.attribute_provenance

    dur_prov = res.attribute_provenance["duration"]
    assert dur_prov.source_type == "provider_live"
    assert dur_prov.is_estimate is False
    assert dur_prov.provider_name == "Google Routes API v2"
    assert "Live traffic-aware" in dur_prov.notes

    dist_prov = res.attribute_provenance["distance"]
    assert dist_prov.source_type == "provider_live"
    assert dist_prov.is_estimate is False
    assert dist_prov.provider_name == "Google Routes API v2"


# ============================================================================
# 5. PARTIAL ATTRIBUTE PROVENANCE (NO FARE OR INVENTORY FROM MAPS)
# ============================================================================

@pytest.mark.anyio
async def test_5_google_routes_partial_attribute_provenance():
    """Verify that Google Routes adapter isolates duration/distance and never fabricates live fares or seats."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"routes": [{"duration": "900s", "distanceMeters": 10000}]})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GoogleRoutesTransportAdapter(api_key="key", enabled=True, http_client=mock_client)
    req = TransportSegmentSearchRequest(
        origin_title="A", origin_city="CityA", origin_lat=12.0, origin_lng=77.0,
        destination_title="B", destination_city="CityA", destination_lat=12.1, destination_lng=77.1,
        mode="rapido",
    )

    res = await adapter.search_segment(req)
    # Fares and availability must NOT be claimed as live by Google Routes
    assert "fare" not in res.attribute_provenance
    assert "availability" not in res.attribute_provenance
    assert res.fare is None


# ============================================================================
# 6. TIMEOUT HANDLING
# ============================================================================

@pytest.mark.anyio
async def test_6_google_routes_timeout():
    """Verify httpx.TimeoutException is classified as ProviderErrorCode.TIMEOUT."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Connection timed out")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GoogleRoutesTransportAdapter(api_key="key", enabled=True, http_client=mock_client)
    req = TransportSegmentSearchRequest(
        origin_title="A", origin_city="CityA", origin_lat=12.0, origin_lng=77.0,
        destination_title="B", destination_city="CityA", destination_lat=12.1, destination_lng=77.1,
        mode="cab",
    )

    with pytest.raises(TransportProviderError) as exc_info:
        await adapter.search_segment(req)

    assert exc_info.value.code == ProviderErrorCode.TIMEOUT
    assert exc_info.value.provider_id == "google_routes"


# ============================================================================
# 7. RATE LIMITING (HTTP 429)
# ============================================================================

@pytest.mark.anyio
async def test_7_google_routes_rate_limiting():
    """Verify HTTP 429 is classified as ProviderErrorCode.RATE_LIMITED."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"code": 429, "message": "Resource exhausted"}})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GoogleRoutesTransportAdapter(api_key="key", enabled=True, http_client=mock_client)
    req = TransportSegmentSearchRequest(
        origin_title="A", origin_city="CityA", origin_lat=12.0, origin_lng=77.0,
        destination_title="B", destination_city="CityA", destination_lat=12.1, destination_lng=77.1,
        mode="cab",
    )

    with pytest.raises(TransportProviderError) as exc_info:
        await adapter.search_segment(req)

    assert exc_info.value.code == ProviderErrorCode.RATE_LIMITED


# ============================================================================
# 8. EMPTY ROUTE RESULT (HTTP 200 BUT NO ROUTES)
# ============================================================================

@pytest.mark.anyio
async def test_8_google_routes_empty_response():
    """Verify 200 OK with empty routes array is classified as ProviderErrorCode.EMPTY_RESULT."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"routes": []})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GoogleRoutesTransportAdapter(api_key="key", enabled=True, http_client=mock_client)
    req = TransportSegmentSearchRequest(
        origin_title="A", origin_city="CityA", origin_lat=12.0, origin_lng=77.0,
        destination_title="B", destination_city="CityA", destination_lat=12.1, destination_lng=77.1,
        mode="cab",
    )

    with pytest.raises(TransportProviderError) as exc_info:
        await adapter.search_segment(req)

    assert exc_info.value.code == ProviderErrorCode.EMPTY_RESULT


# ============================================================================
# 9. MALFORMED RESPONSE
# ============================================================================

@pytest.mark.anyio
async def test_9_google_routes_malformed_response():
    """Verify payload missing duration or containing invalid JSON raises MALFORMED_RESPONSE."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"routes": [{"distanceMeters": 5000}]})  # Missing duration

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GoogleRoutesTransportAdapter(api_key="key", enabled=True, http_client=mock_client)
    req = TransportSegmentSearchRequest(
        origin_title="A", origin_city="CityA", origin_lat=12.0, origin_lng=77.0,
        destination_title="B", destination_city="CityA", destination_lat=12.1, destination_lng=77.1,
        mode="cab",
    )

    with pytest.raises(TransportProviderError) as exc_info:
        await adapter.search_segment(req)

    assert exc_info.value.code == ProviderErrorCode.MALFORMED_RESPONSE


# ============================================================================
# 10. UPSTREAM 5XX UNAVAILABLE
# ============================================================================

@pytest.mark.anyio
async def test_10_google_routes_upstream_503():
    """Verify HTTP 503 is classified as ProviderErrorCode.UNAVAILABLE."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"code": 503, "message": "Service unavailable"}})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GoogleRoutesTransportAdapter(api_key="key", enabled=True, http_client=mock_client)
    req = TransportSegmentSearchRequest(
        origin_title="A", origin_city="CityA", origin_lat=12.0, origin_lng=77.0,
        destination_title="B", destination_city="CityA", destination_lat=12.1, destination_lng=77.1,
        mode="cab",
    )

    with pytest.raises(TransportProviderError) as exc_info:
        await adapter.search_segment(req)

    assert exc_info.value.code == ProviderErrorCode.UNAVAILABLE


# ============================================================================
# 11. JOURNEY ORCHESTRATION WITH LIVE PROVIDER INTEGRATION
# ============================================================================

@pytest.mark.anyio
async def test_11_journey_orchestration_with_live_provider():
    """
    Verify JourneyOrchestrationService incorporates live duration and distance from GoogleRoutesTransportAdapter,
    updates segment times, constructs mixed provenance, and sets providerStatus to active_live.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        # Return 22 minutes (1320s), 14.5 km (14500m)
        return httpx.Response(200, json={"routes": [{"duration": "1320s", "distanceMeters": 14500}]})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    live_adapter = GoogleRoutesTransportAdapter(
        api_key="mock_live_key",
        enabled=True,
        http_client=mock_client,
    )

    orchestrator = JourneyOrchestrationService(transport_providers=[live_adapter])

    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
        preferred_arrival_before="18:00",
    )

    res = await orchestrator.search_journeys(req)
    assert res.provider_status["google_routes"] == "active_live"
    assert len(res.journeys) > 0

    # Inspect fastest journey (which has cab first-mile and last-mile)
    fastest = next(j for j in res.journeys if j.recommendation_category == "fastest")
    seg1 = fastest.segments[0]
    assert seg1.mode == "cab"
    assert seg1.duration_minutes == 22
    assert seg1.distance_km == 14.5

    # Check attribute provenance on live segment
    assert seg1.provenance is not None
    assert seg1.provenance.has_live_provider is True
    assert seg1.provenance.attributes["duration"].source_type == "provider_live"
    assert seg1.provenance.attributes["duration"].is_estimate is False
    assert seg1.provenance.attributes["fare"].source_type == "deterministic_estimate"
    assert seg1.provenance.attributes["availability"].source_type == "simulated"

    # Overall journey provenance must be mixed (live duration + estimated fare/availability)
    assert fastest.provenance.overall_source_type == "mixed"
    assert fastest.provenance.has_live_attributes is True
    assert fastest.provenance.has_simulated_attributes is True
    assert fastest.provenance.is_fully_confirmed is False


# ============================================================================
# 12. RESILIENT FALLBACK ON PROVIDER FAILURE
# ============================================================================

@pytest.mark.anyio
async def test_12_journey_orchestration_fallback_on_provider_error():
    """Verify JourneyOrchestrationService falls back cleanly to deterministic estimates when provider fails."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Google backend error"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    failing_adapter = GoogleRoutesTransportAdapter(
        api_key="mock_key",
        enabled=True,
        http_client=mock_client,
    )

    orchestrator = JourneyOrchestrationService(transport_providers=[failing_adapter])

    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
    )

    # Journey search must succeed gracefully without raising 500
    res = await orchestrator.search_journeys(req)
    assert len(res.journeys) > 0
    assert res.provider_status["google_routes"] == "unavailable_fallback_deterministic"

    # All journeys remain valid deterministic corridor estimates
    for j in res.journeys:
        assert j.provenance.overall_source_type == "deterministic_estimate"
        assert j.total_price > 0
        assert j.total_duration_minutes > 0


# ============================================================================
# 13. OPTIMIZER & HARD CONSTRAINTS WITH LIVE PROVIDER DATA
# ============================================================================

@pytest.mark.anyio
async def test_13_optimizer_and_hard_constraints_with_live_provider():
    """Verify Pareto optimality and hard constraint enforcement work with live provider data."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"routes": [{"duration": "1200s", "distanceMeters": 15000}]})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    live_adapter = GoogleRoutesTransportAdapter(
        api_key="mock_live_key",
        enabled=True,
        http_client=mock_client,
    )

    orchestrator = JourneyOrchestrationService(transport_providers=[live_adapter])

    # Enforce budget cap of ₹1,500
    budget_cap = 1500.0
    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
        budget_max=budget_cap,
    )

    res = await orchestrator.search_journeys(req)
    # Every returned journey must satisfy the budget cap
    for j in res.journeys:
        assert j.total_price <= budget_cap
    assert res.pareto_frontier_count >= 1


# ============================================================================
# 14. NO CREDENTIAL LEAKAGE
# ============================================================================

@pytest.mark.anyio
async def test_14_no_credential_leakage():
    """Verify API keys are never exposed in error details, responses, or provider status."""
    secret_key = "very_secret_api_key_xyz_777"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "Forbidden"})

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
    res_json = res.model_dump_json()

    # Secret key must not appear anywhere in JSON output
    assert secret_key not in res_json
    assert secret_key not in res.provider_status["google_routes"]


# ============================================================================
# 15. HEALTH & PROVIDER CAPABILITIES ENDPOINTS
# ============================================================================

def test_15_api_endpoints_health_and_providers():
    """Verify GET /api/v1/journeys/health and GET /api/v1/journeys/providers."""
    resp_health = client.get("/api/v1/journeys/health")
    assert resp_health.status_code == 200
    data_health = resp_health.json()
    assert data_health["status"] == "healthy"
    assert "providers_registered" in data_health

    resp_providers = client.get("/api/v1/journeys/providers")
    assert resp_providers.status_code == 200
    data_providers = resp_providers.json()
    assert "providers" in data_providers
    assert len(data_providers["providers"]) >= 1

    p0 = data_providers["providers"][0]
    assert p0["providerId"] == "google_routes"
    assert p0["name"] == "Google Routes API v2"
    assert "cab" in p0["supportedModes"]
    assert "isAvailable" in p0
    assert "isLiveAuthenticated" in p0
