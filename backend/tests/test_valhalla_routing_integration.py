"""
backend/tests/test_valhalla_routing_integration.py

Comprehensive test suite for KogniSync Milestone M3.1: OpenStreetMap & Valhalla Routing Integration.
Covers:
1. Successful Valhalla response normalization.
2. Driving route response (costing: auto).
3. Walking route response (costing: pedestrian).
4. Unsupported transport modes explicitly rejected (flight, train, metro).
5. Connection & response timeout handling.
6. HTTP error classification (400, 401, 403, 429, 500, 503).
7. Malformed response handling (missing trip, missing summary, invalid JSON).
8. Empty route results (empty legs, no path found error code 170).
9. Disabled and unconfigured provider behavior.
10. Provider health reporting via GET /api/v1/journeys/providers.
11. Resilient journey fallback on Valhalla failure with explicit provider_status.
12. Granular provenance correctness and unconfirmed booking guard.
13. Journey distance and duration aggregation with proportional carbon scaling.
14. Optimizer ranking consistency and Pareto determinism.
15. Hard budget and arrival deadline constraint preservation.
16. Existing Google Routes adapter independence and regression protection.
17. Real Valhalla container health probe (distinguishing mock from live service).
"""
import asyncio
from datetime import datetime
import httpx
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.services.journey.google_routes_adapter import GoogleRoutesTransportAdapter
from app.services.journey.provider import (
    NormalizedTransportSegmentResponse,
    ProviderCapabilities,
    ProviderErrorCode,
    TransportProviderError,
    TransportSegmentSearchRequest,
)
from app.services.journey.schemas import (
    JourneySearchRequest,
    OptimizationWeightsInput,
)
from app.services.journey.service import JourneyOrchestrationService
from app.services.journey.valhalla_adapter import ValhallaTransportAdapter

client = TestClient(app)


# ============================================================================
# 1. VALHALLA INTERFACE & CAPABILITIES
# ============================================================================

def test_1_valhalla_interface_and_capabilities():
    """Verify ValhallaTransportAdapter capabilities reporting, supported modes, and status."""
    # Disabled adapter
    adapter_disabled = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=False)
    assert adapter_disabled.provider_id == "valhalla"
    assert adapter_disabled.name == "Valhalla OSM Routing Engine"
    assert "cab" in adapter_disabled.supported_modes
    assert "walk" in adapter_disabled.supported_modes
    assert "rapido" in adapter_disabled.supported_modes
    assert "auto" in adapter_disabled.supported_modes
    assert "bus" in adapter_disabled.supported_modes
    assert adapter_disabled.is_available() is False
    assert adapter_disabled.is_live_authenticated() is True

    cap_disabled = adapter_disabled.get_capabilities()
    assert isinstance(cap_disabled, ProviderCapabilities)
    assert cap_disabled.is_available is False
    assert cap_disabled.provider_id == "valhalla"

    # Enabled adapter
    adapter_enabled = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True, timeout_seconds=4.0)
    assert adapter_enabled.is_available() is True
    cap_enabled = adapter_enabled.get_capabilities()
    assert cap_enabled.is_available is True
    assert cap_enabled.timeout_seconds == 4.0


# ============================================================================
# 2. DRIVING ROUTE NORMALIZATION
# ============================================================================

@pytest.mark.anyio
async def test_2_valhalla_driving_route_normalization():
    """Verify Valhalla driving route normalizes duration (seconds->minutes) and distance (km)."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/route"
        payload = request.read().decode("utf-8")
        assert '"costing":"auto"' in payload or '"costing": "auto"' in payload
        assert "units" in payload
        return httpx.Response(
            200,
            json={
                "trip": {
                    "status": 0,
                    "status_message": "Found route between points",
                    "units": "kilometers",
                    "summary": {
                        "time": 1560.0,  # 26 minutes
                        "length": 21.8,   # 21.8 km
                        "cost": 1800.0,
                    },
                    "legs": [
                        {
                            "summary": {"time": 1560.0, "length": 21.8},
                            "shape": "encoded_polyline_mock",
                        }
                    ],
                }
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaTransportAdapter(
        base_url="http://localhost:8002",
        enabled=True,
        http_client=mock_client,
    )

    req = TransportSegmentSearchRequest(
        origin_title="Majestic Railway Hub",
        origin_city="Bangalore",
        origin_lat=12.978,
        origin_lng=77.572,
        destination_title="Indiranagar Concourse",
        destination_city="Bangalore",
        destination_lat=12.978,
        destination_lng=77.640,
        mode="cab",
    )

    res = await adapter.search_segment(req)
    assert isinstance(res, NormalizedTransportSegmentResponse)
    assert res.provider_id == "valhalla"
    assert res.provider_name == "Valhalla OSM Routing Engine"
    assert res.duration_minutes == 26
    assert res.distance_km == 21.8
    assert res.mode == "cab"

    # Retrieved at must be valid ISO timestamp
    dt = datetime.fromisoformat(res.retrieved_at)
    assert dt is not None

    # Attribute-level provenance
    assert res.attribute_provenance["duration"].source_type == "provider_live"
    assert res.attribute_provenance["duration"].is_estimate is False
    assert res.attribute_provenance["duration"].provider_name == "Valhalla OSM Routing Engine"
    assert "OpenStreetMap" in res.attribute_provenance["duration"].notes

    assert res.attribute_provenance["distance"].source_type == "provider_live"
    assert res.attribute_provenance["distance"].is_estimate is False
    assert res.attribute_provenance["distance"].provider_name == "Valhalla OSM Routing Engine"

    # Fares and availability must remain unpopulated by routing engine
    assert res.fare is None
    assert "fare" not in res.attribute_provenance
    assert "availability" not in res.attribute_provenance


# ============================================================================
# 3. WALKING ROUTE NORMALIZATION
# ============================================================================

@pytest.mark.anyio
async def test_3_valhalla_walking_route_normalization():
    """Verify Valhalla pedestrian route uses costing 'pedestrian' and normalizes correctly."""
    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read().decode("utf-8")
        assert '"costing":"pedestrian"' in payload or '"costing": "pedestrian"' in payload
        return httpx.Response(
            200,
            json={
                "trip": {
                    "status": 0,
                    "status_message": "Found route between points",
                    "units": "kilometers",
                    "summary": {
                        "time": 900.0,  # 15 minutes
                        "length": 1.2,   # 1.2 km
                    },
                    "legs": [{"summary": {"time": 900.0, "length": 1.2}}],
                }
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaTransportAdapter(
        base_url="http://localhost:8002",
        enabled=True,
        http_client=mock_client,
    )

    req = TransportSegmentSearchRequest(
        origin_title="Platform 1",
        origin_city="Bangalore",
        origin_lat=12.978,
        origin_lng=77.572,
        destination_title="Subway Concourse",
        destination_city="Bangalore",
        destination_lat=12.979,
        destination_lng=77.574,
        mode="walk",
    )

    res = await adapter.search_segment(req)
    assert res.duration_minutes == 15
    assert res.distance_km == 1.2
    assert res.mode == "walk"
    assert res.attribute_provenance["duration"].source_type == "provider_live"


# ============================================================================
# 4. UNSUPPORTED TRANSPORT MODES REJECTED
# ============================================================================

@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["flight", "train", "metro"])
async def test_4_valhalla_unsupported_modes(mode):
    """Verify that non-road transit modes (flight, train, metro) are explicitly rejected."""
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True)
    req = TransportSegmentSearchRequest(
        origin_title="A", origin_city="CityA", origin_lat=12.0, origin_lng=77.0,
        destination_title="B", destination_city="CityA", destination_lat=12.1, destination_lng=77.1,
        mode=mode,
    )

    with pytest.raises(TransportProviderError) as exc_info:
        await adapter.search_segment(req)

    assert exc_info.value.code == ProviderErrorCode.UNSUPPORTED_MODE
    assert exc_info.value.provider_id == "valhalla"


# ============================================================================
# 5. CONNECTION & RESPONSE TIMEOUT
# ============================================================================

@pytest.mark.anyio
async def test_5_valhalla_connection_timeout():
    """Verify timeout on slow Valhalla service raises ProviderErrorCode.TIMEOUT."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Valhalla request timed out")

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True, http_client=mock_client)
    req = TransportSegmentSearchRequest(
        origin_title="A", origin_city="CityA", origin_lat=12.0, origin_lng=77.0,
        destination_title="B", destination_city="CityA", destination_lat=12.1, destination_lng=77.1,
        mode="cab",
    )

    with pytest.raises(TransportProviderError) as exc_info:
        await adapter.search_segment(req)

    assert exc_info.value.code == ProviderErrorCode.TIMEOUT
    assert exc_info.value.provider_id == "valhalla"


# ============================================================================
# 6. HTTP ERROR CLASSIFICATION
# ============================================================================

@pytest.mark.anyio
@pytest.mark.parametrize(
    "status_code,payload,expected_code",
    [
        (400, {"error": "Invalid locations array"}, ProviderErrorCode.INVALID_REQUEST),
        (401, {"error": "Unauthorized"}, ProviderErrorCode.AUTH_FAILURE),
        (403, {"error": "Forbidden"}, ProviderErrorCode.AUTH_FAILURE),
        (429, {"error": "Too Many Requests"}, ProviderErrorCode.RATE_LIMITED),
        (500, {"error": "Internal Server Error"}, ProviderErrorCode.UNAVAILABLE),
        (503, {"error": "Valhalla tileset not loaded"}, ProviderErrorCode.UNAVAILABLE),
    ],
)
async def test_6_valhalla_http_errors(status_code, payload, expected_code):
    """Verify HTTP error codes are cleanly classified without exception leakage."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True, http_client=mock_client)
    req = TransportSegmentSearchRequest(
        origin_title="A", origin_city="CityA", origin_lat=12.0, origin_lng=77.0,
        destination_title="B", destination_city="CityA", destination_lat=12.1, destination_lng=77.1,
        mode="cab",
    )

    with pytest.raises(TransportProviderError) as exc_info:
        await adapter.search_segment(req)

    assert exc_info.value.code == expected_code
    assert exc_info.value.provider_id == "valhalla"


# ============================================================================
# 7. MALFORMED RESPONSE
# ============================================================================

@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {},                                                 # Empty dictionary
        {"trip": {}},                                       # Missing summary
        {"trip": {"summary": {"time": -1, "length": 5.0}}}, # Negative time
        {"trip": {"summary": {"length": 5.0}}},             # Missing time
        {"trip": {"summary": {"time": 600}}},               # Missing length
    ],
)
async def test_7_valhalla_malformed_response(payload):
    """Verify missing trip attributes or invalid data raises MALFORMED_RESPONSE."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True, http_client=mock_client)
    req = TransportSegmentSearchRequest(
        origin_title="A", origin_city="CityA", origin_lat=12.0, origin_lng=77.0,
        destination_title="B", destination_city="CityA", destination_lat=12.1, destination_lng=77.1,
        mode="cab",
    )

    with pytest.raises(TransportProviderError) as exc_info:
        await adapter.search_segment(req)

    assert exc_info.value.code == ProviderErrorCode.MALFORMED_RESPONSE


# ============================================================================
# 8. EMPTY ROUTE RESULT
# ============================================================================

@pytest.mark.anyio
async def test_8_valhalla_empty_route_result():
    """Verify Valhalla empty legs or 'no path' error code is classified as EMPTY_RESULT."""
    # Case A: 200 OK but empty legs
    def empty_legs_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"trip": {"status": 0, "summary": {"time": 0.0, "length": 0.0}, "legs": []}},
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(empty_legs_handler))
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True, http_client=mock_client)
    req = TransportSegmentSearchRequest(
        origin_title="A", origin_city="CityA", origin_lat=12.0, origin_lng=77.0,
        destination_title="B", destination_city="CityA", destination_lat=12.1, destination_lng=77.1,
        mode="cab",
    )

    with pytest.raises(TransportProviderError) as exc_info:
        await adapter.search_segment(req)
    assert exc_info.value.code == ProviderErrorCode.EMPTY_RESULT

    # Case B: 400 Bad Request with error_code 170 (No path could be found)
    def no_path_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error_code": 170, "error": "No path could be found for input locations"},
        )

    mock_client_no_path = httpx.AsyncClient(transport=httpx.MockTransport(no_path_handler))
    adapter_no_path = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True, http_client=mock_client_no_path)

    with pytest.raises(TransportProviderError) as exc_info:
        await adapter_no_path.search_segment(req)
    assert exc_info.value.code == ProviderErrorCode.EMPTY_RESULT


# ============================================================================
# 9. DISABLED / UNCONFIGURED PROVIDER
# ============================================================================

@pytest.mark.anyio
async def test_9_valhalla_disabled_behavior():
    """Verify disabled adapter raises AUTH_FAILURE and reports is_available=False."""
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=False)
    assert adapter.is_available() is False

    req = TransportSegmentSearchRequest(
        origin_title="A", origin_city="CityA", origin_lat=12.0, origin_lng=77.0,
        destination_title="B", destination_city="CityA", destination_lat=12.1, destination_lng=77.1,
        mode="cab",
    )

    with pytest.raises(TransportProviderError) as exc_info:
        await adapter.search_segment(req)
    assert exc_info.value.code == ProviderErrorCode.AUTH_FAILURE


# ============================================================================
# 10. PROVIDER HEALTH REPORTING
# ============================================================================

def test_10_provider_health_reporting():
    """Verify GET /api/v1/journeys/providers reports both Google Routes and Valhalla."""
    resp = client.get("/api/v1/journeys/providers")
    assert resp.status_code == 200
    data = resp.json()

    assert "providers" in data
    provider_ids = [p["providerId"] for p in data["providers"]]
    assert "google_routes" in provider_ids
    assert "valhalla" in provider_ids

    valhalla_cap = next(p for p in data["providers"] if p["providerId"] == "valhalla")
    assert valhalla_cap["name"] == "Valhalla OSM Routing Engine"
    assert "cab" in valhalla_cap["supportedModes"]
    assert "walk" in valhalla_cap["supportedModes"]


# ============================================================================
# 11. JOURNEY ORCHESTRATION & RESILIENT FALLBACK
# ============================================================================

@pytest.mark.anyio
async def test_11_journey_orchestration_valhalla_fallback():
    """Verify that when Valhalla fails, search_journeys degrades cleanly to deterministic estimates."""
    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Valhalla tiles error"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(failing_handler))
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True, http_client=mock_client)
    orchestrator = JourneyOrchestrationService(transport_providers=[adapter])

    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
    )

    res = await orchestrator.search_journeys(req)
    assert len(res.journeys) > 0
    assert res.provider_status["valhalla"] == "unavailable_fallback_deterministic"

    # All journeys remain valid deterministic corridor estimates
    for j in res.journeys:
        assert j.provenance.overall_source_type == "deterministic_estimate"
        assert j.total_price > 0
        assert j.total_duration_minutes > 0


# ============================================================================
# 12. PROVENANCE CORRECTNESS WITH VALHALLA
# ============================================================================

@pytest.mark.anyio
async def test_12_provenance_correctness_with_valhalla():
    """Verify Valhalla duration/distance have provider_live provenance without claiming confirmed journey."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "trip": {
                    "status": 0,
                    "units": "kilometers",
                    "summary": {"time": 1200.0, "length": 18.5},
                    "legs": [{"summary": {"time": 1200.0, "length": 18.5}}],
                }
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True, http_client=mock_client)
    orchestrator = JourneyOrchestrationService(transport_providers=[adapter])

    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
    )

    res = await orchestrator.search_journeys(req)
    assert res.provider_status["valhalla"] == "active_live"

    fastest = next(j for j in res.journeys if j.recommendation_category == "fastest")
    seg1 = fastest.segments[0]
    assert seg1.mode == "cab"
    assert seg1.duration_minutes == 20
    assert seg1.distance_km == 18.5

    # Segment provenance
    assert seg1.provenance.has_live_provider is True
    assert seg1.provenance.attributes["duration"].source_type == "provider_live"
    assert seg1.provenance.attributes["duration"].provider_name == "Valhalla OSM Routing Engine"
    assert seg1.provenance.attributes["distance"].source_type == "provider_live"
    assert seg1.provenance.attributes["fare"].source_type == "deterministic_estimate"
    assert seg1.provenance.attributes["availability"].source_type == "simulated"

    # Journey overall provenance
    assert fastest.provenance.overall_source_type == "mixed"
    assert fastest.provenance.is_fully_confirmed is False
    assert fastest.ai_explanation.is_availability_verified is False


# ============================================================================
# 13. JOURNEY DISTANCE, DURATION & CARBON AGGREGATION
# ============================================================================

@pytest.mark.anyio
async def test_13_journey_distance_duration_and_carbon_aggregation():
    """Verify Valhalla metrics update journey total duration and proportionally scale road carbon."""
    # Report 17.0 km (baseline was 34.0 km with 5.2 kg CO2 -> scaled to ~2.6 kg CO2)
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "trip": {
                    "status": 0,
                    "units": "kilometers",
                    "summary": {"time": 1200.0, "length": 17.0},
                    "legs": [{"summary": {"time": 1200.0, "length": 17.0}}],
                }
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True, http_client=mock_client)
    orchestrator = JourneyOrchestrationService(transport_providers=[adapter])

    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
    )

    res = await orchestrator.search_journeys(req)
    fastest = next(j for j in res.journeys if j.recommendation_category == "fastest")
    seg1 = fastest.segments[0]
    assert seg1.distance_km == 17.0
    assert seg1.carbon_kg == 2.6  # Half the baseline 5.2 kg


# ============================================================================
# 14. OPTIMIZER RANKING CONSISTENCY & DETERMINISM
# ============================================================================

@pytest.mark.anyio
async def test_14_optimizer_ranking_consistency_with_valhalla():
    """Verify Pareto optimization is 100% deterministic when Valhalla is active."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "trip": {
                    "status": 0,
                    "units": "kilometers",
                    "summary": {"time": 1320.0, "length": 19.0},
                    "legs": [{"summary": {"time": 1320.0, "length": 19.0}}],
                }
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True, http_client=mock_client)
    orchestrator = JourneyOrchestrationService(transport_providers=[adapter])

    req = JourneySearchRequest(
        origin="Bangalore",
        destination="Chennai",
        departure_date="2026-11-06",
        weights=OptimizationWeightsInput(duration=0.5, cost=0.3, comfort=0.1, carbon=0.1),
    )

    res1 = await orchestrator.search_journeys(req)
    res2 = await orchestrator.search_journeys(req)

    assert [j.id for j in res1.journeys] == [j.id for j in res2.journeys]
    assert [j.total_price for j in res1.journeys] == [j.total_price for j in res2.journeys]
    assert [j.total_duration_minutes for j in res1.journeys] == [j.total_duration_minutes for j in res2.journeys]


# ============================================================================
# 15. HARD BUDGET AND DEADLINE CONSTRAINTS
# ============================================================================

@pytest.mark.anyio
async def test_15_hard_constraints_preserved_with_valhalla():
    """Verify hard budget caps and arrival deadlines remain absolute with Valhalla active."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "trip": {
                    "status": 0,
                    "units": "kilometers",
                    "summary": {"time": 1200.0, "length": 15.0},
                    "legs": [{"summary": {"time": 1200.0, "length": 15.0}}],
                }
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True, http_client=mock_client)
    orchestrator = JourneyOrchestrationService(transport_providers=[adapter])

    # 1. Budget cap
    budget_cap = 1800.0
    res_b = await orchestrator.search_journeys(
        JourneySearchRequest(origin="Bangalore", destination="Chennai", departure_date="2026-11-06", budget_max=budget_cap)
    )
    assert len(res_b.journeys) > 0
    for j in res_b.journeys:
        assert j.total_price <= budget_cap

    # 2. Strict arrival deadline
    res_d = await orchestrator.search_journeys(
        JourneySearchRequest(origin="Bangalore", destination="Chennai", departure_date="2026-11-06", preferred_arrival_before="17:00")
    )
    assert len(res_d.journeys) > 0
    for j in res_d.journeys:
        arr_time = datetime.fromisoformat(j.arrival_time)
        assert arr_time.hour < 17 or (arr_time.hour == 17 and arr_time.minute == 0)


# ============================================================================
# 16. GOOGLE ADAPTER REGRESSION PROTECTION
# ============================================================================

@pytest.mark.anyio
async def test_16_google_adapter_regression_protection():
    """Verify GoogleRoutesTransportAdapter remains completely functional and unimpacted by Valhalla."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"routes": [{"duration": "1440s", "distanceMeters": 18000}]})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    google_adapter = GoogleRoutesTransportAdapter(api_key="valid_google_key", enabled=True, http_client=mock_client)
    valhalla_adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=False)

    orchestrator = JourneyOrchestrationService(transport_providers=[google_adapter, valhalla_adapter])

    req = JourneySearchRequest(origin="Bangalore", destination="Chennai", departure_date="2026-11-06")
    res = await orchestrator.search_journeys(req)

    assert res.provider_status["google_routes"] == "active_live"
    assert res.provider_status["valhalla"] == "unconfigured_fallback_deterministic"

    fastest = next(j for j in res.journeys if j.recommendation_category == "fastest")
    assert fastest.segments[0].duration_minutes == 24
    assert fastest.segments[0].provenance.attributes["duration"].provider_name == "Google Routes API v2"


# ============================================================================
# 17. REAL VALHALLA PROBE (DISTINGUISHING MOCK FROM LIVE SERVICE)
# ============================================================================

@pytest.mark.anyio
async def test_17_real_valhalla_health_probe():
    """
    Probes real Valhalla instance if running at localhost:8002.
    Demonstrates live service verification without failing CI if Docker profile is unstarted.
    """
    adapter = ValhallaTransportAdapter(base_url="http://localhost:8002", enabled=True)
    health = await adapter.check_health()
    assert "provider_id" in health
    assert health["provider_id"] == "valhalla"
    assert "status" in health

    # If the local Docker Valhalla profile is started: status == "healthy", is_available == True
    # If unstarted: status in ("unreachable", "degraded", "unconfigured"), is_available == False
    assert health["status"] in ("healthy", "unreachable", "degraded", "unconfigured")

