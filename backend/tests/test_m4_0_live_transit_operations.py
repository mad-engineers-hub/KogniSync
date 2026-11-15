"""
backend/tests/test_m4_0_live_transit_operations.py

Comprehensive M4.0 Test Suite:
Authorized Live Transit Feed Activation, IUDX NGSI-LD Adaptation, Independent Protobuf
Fixtures, Auth Adapters (`api_key_query`, `api_key_header`), Validation/Freshness Gates,
Controlled Polling, Multimodal Journey Impact/Recovery, and Live API Smoke Probes.
"""
from __future__ import annotations

import json
import os
import socket
import struct
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.disruption.assessment import JourneyImpactAssessor
from app.services.disruption.matcher import RouteDisruptionMatcher
from app.services.disruption.providers.gtfs_feed_client import (
    GTFSFeedFetchResult,
    SecureGTFSFeedClient,
    sanitize_feed_url,
)
from app.services.disruption.providers.gtfs_realtime import GTFSRealtimeProvider
from app.services.disruption.providers.gtfs_registry import GTFSFeedRegistry
from app.services.disruption.recovery import JourneyRecoveryEngine
from app.services.disruption.schemas import (
    DisruptionEvent,
    GTFSFeedConfig,
)
from app.services.journey.schemas import (
    AIExplanationSchema,
    BookingFeasibilitySchema,
    CoordinatesSchema,
    JourneySchema,
    JourneySegmentSchema,
    LocationSchema,
)

api_client = TestClient(app)


# ----------------------------------------------------------------------------
# Independent Hand-Crafted Protobuf Wire Helper (does NOT use gtfs_protobuf.py)
# ----------------------------------------------------------------------------

def _raw_varint(value: int) -> bytes:
    if value < 0:
        value &= (1 << 64) - 1
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def _raw_ld(field_num: int, payload: bytes) -> bytes:
    tag = (field_num << 3) | 2
    return _raw_varint(tag) + _raw_varint(len(payload)) + payload


def _raw_vi(field_num: int, value: int) -> bytes:
    tag = (field_num << 3) | 0
    return _raw_varint(tag) + _raw_varint(value)


def _raw_f32(field_num: int, value: float) -> bytes:
    tag = (field_num << 3) | 5
    return _raw_varint(tag) + struct.pack("<f", value)


def build_independent_gtfs_rt_pb(now_ts: int) -> bytes:
    """Constructs valid GTFS-RT v2.0 FeedMessage bytes independently from wire primitives."""
    header = (
        _raw_ld(1, b"2.0")
        + _raw_vi(2, 0)       # FULL_DATASET
        + _raw_vi(3, now_ts)  # timestamp
    )

    # Entity 1: VehiclePosition on route DTC-534 with SEVERE_CONGESTION (enum 4)
    trip_vp = _raw_ld(1, b"TRIP-DTC-534-A") + _raw_ld(5, b"DTC-534")
    pos_vp = _raw_f32(1, 28.6139) + _raw_f32(2, 77.2090)
    vp_msg = _raw_ld(1, trip_vp) + _raw_ld(2, pos_vp) + _raw_vi(5, now_ts) + _raw_vi(6, 4)
    ent_vp = _raw_ld(1, b"veh-dtc-01") + _raw_ld(4, vp_msg)

    # Entity 2: TripUpdate on route DTC-534 delayed 900s at stop ISBT-KASHMERE
    trip_tu = _raw_ld(1, b"TRIP-DTC-534-B") + _raw_ld(5, b"DTC-534") + _raw_vi(4, 0)
    stop_evt = _raw_vi(1, 900)
    stu = _raw_ld(4, b"ISBT-KASHMERE") + _raw_ld(2, stop_evt)
    tu_msg = _raw_ld(1, trip_tu) + _raw_ld(3, stu) + _raw_vi(4, now_ts) + _raw_vi(5, 900)
    ent_tu = _raw_ld(1, b"tu-dtc-02") + _raw_ld(3, tu_msg)

    return _raw_ld(1, header) + _raw_ld(2, ent_vp) + _raw_ld(2, ent_tu)


# ============================================================================
# 1. ENVIRONMENT PRESETS, AUTHENTICATION ADAPTERS & SECRET HYGIENE
# ============================================================================

def test_default_indian_agency_presets_fail_closed_without_tokens():
    """Verify default Bengaluru BMTC IUDX and Delhi OTD feeds stay unactivated without credentials."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BMTC_IUDX_AUTH_TOKEN", None)
        os.environ.pop("IUDX_AUTH_TOKEN", None)
        os.environ.pop("DELHI_OTD_API_KEY", None)
        registry = GTFSFeedRegistry(client=SecureGTFSFeedClient())

    bmtc = registry.get_feed_status("bmtc_iudx_vehicle_positions")
    delhi = registry.get_feed_status("delhi_otd_vehicle_positions")
    assert bmtc is not None
    assert delhi is not None
    assert bmtc.enabled is False
    assert delhi.enabled is False
    assert bmtc.authorization_status == "pending_credentials"
    assert delhi.authorization_status == "pending_credentials"
    assert bmtc.connectivity_status != "available"
    assert delhi.connectivity_status != "available"
    assert bmtc.live_blocker_reason is not None
    assert delhi.live_blocker_reason is not None


@pytest.mark.anyio
async def test_api_key_query_and_iudx_token_header_injection_without_leakage(monkeypatch):
    """Verify api_key_query (`?key=...`) and custom `token` header are injected safely and redacted."""
    monkeypatch.setenv("TEST_DELHI_OTD_KEY", "SUPER_SECRET_DELHI_KEY_999")
    monkeypatch.setenv("TEST_IUDX_JWT", "eyJhbGciOiJFUzI1NiJ9.mockjwt.sig")

    mock_client = SecureGTFSFeedClient(allow_http=False, max_retries=0)
    registry = GTFSFeedRegistry(
        client=mock_client,
        initial_configs=[
            GTFSFeedConfig(
                feed_id="delhi_otd_test",
                operator_name="Delhi OTD",
                display_name="Delhi OTD Vehicle Positions",
                geographic_coverage="Delhi NCR",
                feed_url="https://otd.transit.example.gov/api/realtime/VehiclePositions.pb",
                auth_type="api_key_query",
                auth_query_param_name="key",
                auth_token_env_var="TEST_DELHI_OTD_KEY",
                enabled=True,
            ),
            GTFSFeedConfig(
                feed_id="bmtc_iudx_test",
                operator_name="BMTC",
                display_name="BMTC IUDX Live Bus",
                geographic_coverage="Bengaluru",
                feed_url="https://rs.iudx.example.gov/ngsi-ld/v1/entities?id=8a9c53c2",
                auth_type="api_key_header",
                auth_header_name="token",
                auth_token_env_var="TEST_IUDX_JWT",
                provider_format="iudx_ngsi_ld",
                enabled=True,
            ),
        ],
    )

    # Must NEVER report available before verified upstream response
    assert registry.get_feed_status("delhi_otd_test").connectivity_status == "configured"
    assert registry.get_feed_status("bmtc_iudx_test").connectivity_status == "configured"

    now_ts = int(time.time())
    pb_bytes = build_independent_gtfs_rt_pb(now_ts)
    iudx_json = {
        "type": "urn:dx:rs:Success",
        "results": [
            {
                "id": "KA01F1234",
                "observationDateTime": datetime.now(timezone.utc).isoformat(),
                "location": {"type": "Point", "coordinates": [77.5946, 12.9716]},
                "tripInfo": {"route_id": "335E", "trip_id": "BMTC-335E-101", "delay": 720},
                "positionInfo": {"congestion_level": "SEVERE_CONGESTION", "speed": 4.2},
            },
            {
                "id": "KA01F5678",
                "observationDateTime": datetime.now(timezone.utc).isoformat(),
                "location": {"type": "Point", "coordinates": [77.6100, 12.9300]},
                "tripInfo": {"route_id": "500D", "trip_id": "BMTC-500D-202"},
                "positionInfo": {"congestion_level": "RUNNING_SMOOTHLY", "speed": 28.0},
            },
        ],
    }

    captured_calls: list[tuple[str, dict[str, str]]] = []

    async def fake_httpx_get(self, url, **kwargs):
        hdrs = dict(kwargs.get("headers") or {})
        captured_calls.append((str(url), hdrs))
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        if "otd.transit.example.gov" in str(url):
            resp.content = pb_bytes
            resp.headers = {"content-type": "application/x-protobuf"}
        else:
            resp.content = json.dumps(iudx_json).encode("utf-8")
            resp.headers = {"content-type": "application/json"}
        return resp

    with patch.object(httpx.AsyncClient, "get", new=fake_httpx_get):
        events = await registry.poll_all_enabled_feeds(force=True)

    # Verify outbound requests used exact credentials cleanly
    delhi_call = next(c for c in captured_calls if "otd.transit.example.gov" in c[0])
    assert "key=SUPER_SECRET_DELHI_KEY_999" in delhi_call[0]

    bmtc_call = next(c for c in captured_calls if "rs.iudx.example.gov" in c[0])
    assert bmtc_call[1].get("token") == "eyJhbGciOiJFUzI1NiJ9.mockjwt.sig"

    # Verify zero secret leakage in statuses & transitions
    for st in registry.get_feed_statuses():
        dumped = json.dumps(st.model_dump(by_alias=True))
        assert "SUPER_SECRET_DELHI_KEY_999" not in dumped
        assert "eyJhbGciOiJFUzI1NiJ9" not in dumped
        assert st.connectivity_status == "available"
        assert st.last_successful_fetch is not None
        assert len(st.availability_transitions) >= 1

    # Verify parsed events: 2 from independent .pb (VP + TU), 2 from IUDX KA01F1234 (VP + TU);
    # smooth KA01F5678 must NOT manufacture false congestion!
    assert len(events) == 4
    assert all(ev.provenance == "provider_live" for ev in events)
    bmtc_st = registry.get_feed_status("bmtc_iudx_test")
    assert bmtc_st.entity_counts.get("vehicle_positions") == 2
    assert bmtc_st.entity_counts.get("trip_updates") == 1


@pytest.mark.anyio
async def test_cross_origin_redirect_strips_credentials():
    """Verify cross-origin 302 redirect strips auth headers and query secrets."""
    client = SecureGTFSFeedClient(allow_http=False, max_retries=0)
    captured_headers: list[dict[str, str]] = []
    captured_urls: list[str] = []

    resp_302 = MagicMock(spec=httpx.Response)
    resp_302.status_code = 302
    resp_302.headers = {"location": "https://cdn.other-domain.org/gtfs.pb"}

    resp_200 = MagicMock(spec=httpx.Response)
    resp_200.status_code = 200
    resp_200.headers = {"content-type": "application/x-protobuf"}
    resp_200.content = build_independent_gtfs_rt_pb(int(time.time()))

    async def fake_get(self, url, **kwargs):
        captured_urls.append(str(url))
        captured_headers.append(dict(kwargs.get("headers") or {}))
        return resp_302 if len(captured_urls) == 1 else resp_200

    with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]):
        with patch.object(httpx.AsyncClient, "get", new=fake_get):
            result = await client.fetch_feed(
                feed_id="redir_sec",
                feed_url="https://api.transit-agency.gov/feed.pb",
                auth_header=("token", "SECRET_TOKEN"),
                auth_query_param=("key", "SECRET_QUERY_KEY"),
            )

    assert result.status_code == 200
    assert len(captured_urls) == 2
    assert "SECRET_QUERY_KEY" in captured_urls[0]
    assert captured_headers[0].get("token") == "SECRET_TOKEN"
    # Second hop to cdn.other-domain.org MUST NOT carry either credential
    assert "SECRET_QUERY_KEY" not in captured_urls[1]
    assert "token" not in {k.lower() for k in captured_headers[1]}


# ============================================================================
# 2. ENTITY VALIDATION, BOUNDS, STALENESS & POLLING COOLDOWN
# ============================================================================

@pytest.mark.anyio
async def test_vehicle_bounds_stale_entities_and_expired_alerts_rejected():
    """Verify invalid coordinates, stale entity timestamps, and expired alerts are cleanly rejected."""
    mock_client = SecureGTFSFeedClient(allow_http=True, max_retries=0)
    registry = GTFSFeedRegistry(
        client=mock_client,
        initial_configs=[
            GTFSFeedConfig(
                feed_id="validation_test",
                operator_name="Test Agency",
                display_name="Validation Test Feed",
                feed_url="https://transit.example.gov/feed.json",
                auth_type="none",
                polling_interval_seconds=60,
                enabled=True,
            )
        ],
    )

    now_ts = int(time.time())
    payload = {
        "header": {"gtfs_realtime_version": "2.0", "timestamp": now_ts - 10},
        "entity": [
            # Invalid coordinate out of latitude bounds
            {
                "id": "veh-bad-lat",
                "vehicle": {
                    "position": {"latitude": 120.5, "longitude": 77.5},
                    "congestion_level": "SEVERE_CONGESTION",
                    "timestamp": now_ts - 10,
                },
            },
            # Null-Island (0, 0) coordinate
            {
                "id": "veh-null-island",
                "vehicle": {
                    "position": {"latitude": 0.0, "longitude": 0.0},
                    "congestion_level": "CONGESTION",
                    "timestamp": now_ts - 10,
                },
            },
            # Stale vehicle observation (> 180s)
            {
                "id": "veh-stale",
                "vehicle": {
                    "position": {"latitude": 12.9716, "longitude": 77.5946},
                    "congestion_level": "SEVERE_CONGESTION",
                    "timestamp": now_ts - 500,
                },
            },
            # Expired service alert
            {
                "id": "alert-expired",
                "alert": {
                    "header_text": {"translation": [{"text": "Yesterday Detour"}]},
                    "effect": "DETOUR",
                    "active_period": [{"start": now_ts - 7200, "end": now_ts - 600}],
                },
            },
            # Valid TripUpdate (>= 300s threshold)
            {
                "id": "tu-valid",
                "trip_update": {
                    "trip": {"trip_id": "BMTC-201R-1", "route_id": "201R"},
                    "delay": 480,
                    "timestamp": now_ts - 20,
                },
            },
        ],
    }

    mock_res = GTFSFeedFetchResult(
        status_code=200,
        content=json.dumps(payload).encode("utf-8"),
        content_type="application/json",
        latency_ms=15.0,
        headers={},
    )

    with patch.object(mock_client, "fetch_feed", new_callable=AsyncMock, return_value=mock_res) as mock_fetch:
        events = await registry.poll_all_enabled_feeds(force=False)
        # Second poll within 60s cooldown must reuse cache without hitting upstream again
        events_cached = await registry.poll_all_enabled_feeds(force=False)
        assert mock_fetch.call_count == 1
        assert len(events_cached) == len(events)

        # Force=True triggers fresh upstream poll
        await registry.poll_all_enabled_feeds(force=True)
        assert mock_fetch.call_count == 2

    assert len(events) == 1
    assert events[0].route_ids == ["201R"]
    st = registry.get_feed_status("validation_test")
    assert st.accepted_event_count == 1
    assert st.rejected_event_count == 4
    assert st.rejected_reasons.get("invalid_coordinates") == 2
    assert st.rejected_reasons.get("stale_vehicle_timestamp") == 1
    assert st.rejected_reasons.get("expired_active_period") == 1
    assert st.stale_rejections >= 1


# ============================================================================
# 3. UNIFIED PROVIDER SSRF ENFORCEMENT + MULTIMODAL CORRELATION & RECOVERY
# ============================================================================

@pytest.mark.anyio
async def test_unified_gtfs_provider_uses_pinned_client_and_registry():
    """Verify GTFSRealtimeProvider delegates to GTFSFeedRegistry and blocks direct SSRF URLs."""
    # Direct private URL blocked by SSRF even before network request
    ssrf_provider = GTFSRealtimeProvider(feed_url="https://169.254.169.254/latest/meta-data/")
    with patch("app.core.config.settings.GTFS_REALTIME_ENABLED", True):
        assert ssrf_provider.is_configured() is False
        assert ssrf_provider.get_connectivity_status() == "blocked"
        assert await ssrf_provider.fetch_disruptions() == []

    # Registry-backed multi-feed mode
    mock_client = SecureGTFSFeedClient(allow_http=False, max_retries=0)
    registry = GTFSFeedRegistry(
        client=mock_client,
        initial_configs=[
            GTFSFeedConfig(
                feed_id="multi_test",
                operator_name="BMTC",
                display_name="BMTC Multi",
                feed_url="https://rs.cos.example.org/bmtc",
                enabled=True,
            )
        ],
    )
    unified_provider = GTFSRealtimeProvider(registry=registry)
    assert unified_provider.is_configured() is True
    # Must NOT be available prior to verified response
    assert unified_provider.get_connectivity_status() == "unknown"


def test_multimodal_exact_matching_and_manual_rebooking_recovery():
    """Verify live transit + road disruption correlation, exact matching, and manual rebooking safety."""
    now_iso = datetime.now(timezone.utc).isoformat()
    transit_event = DisruptionEvent(
        id="bmtc-335e-delay",
        source="gtfs_realtime",
        event_type="transport_delay",
        severity="high",
        title="BMTC Delay (25m): Route 335E",
        description="Official transit delay on 335E corridor",
        affected_modes=["bus"],
        valid_from=now_iso,
        observed_at=now_iso,
        last_verified_at=now_iso,
        provenance="provider_live",
        estimated_delay_minutes=25,
        route_ids=["335E"],
        stop_ids=["STOP-MAJESTIC-01"],
    )
    # Non-matching route "335" must NEVER false-match "335E" (M3.9.1 regression check)
    false_route_event = DisruptionEvent(
        id="bmtc-335-delay",
        source="gtfs_realtime",
        event_type="transport_delay",
        severity="critical",
        title="BMTC Delay (40m): Route 335",
        description="Unrelated short route 335",
        affected_modes=["bus"],
        valid_from=now_iso,
        observed_at=now_iso,
        last_verified_at=now_iso,
        provenance="provider_live",
        estimated_delay_minutes=40,
        route_ids=["335"],
    )

    now_dt = datetime.now(timezone.utc)
    t0 = (now_dt + timedelta(minutes=10)).isoformat()
    t1 = (now_dt + timedelta(minutes=50)).isoformat()
    t2 = (now_dt + timedelta(minutes=60)).isoformat()  # 10 min transfer buffer -> breached by 25m delay!
    t3 = (now_dt + timedelta(minutes=110)).isoformat()

    majestic = LocationSchema(
        id="STOP-MAJESTIC-01",
        name="Kempegowda Bus Station Majestic",
        city="Bengaluru",
        type="bus_terminal",
        coordinates=CoordinatesSchema(lat=12.9767, lng=77.5713),
    )
    whitefield = LocationSchema(
        id="STOP-WHITEFIELD",
        name="ITPL Whitefield",
        city="Bengaluru",
        type="bus_terminal",
        coordinates=CoordinatesSchema(lat=12.9850, lng=77.7365),
    )
    hub_final = LocationSchema(
        id="STATION-SBC",
        name="KSR Bengaluru City",
        city="Bengaluru",
        type="railway_station",
        coordinates=CoordinatesSchema(lat=12.9781, lng=77.5695),
    )

    journey = JourneySchema(
        id="jny-m4-multimodal",
        title="Majestic to KSR via 335E",
        origin=majestic,
        destination=hub_final,
        departure_time=t0,
        arrival_time=t3,
        total_duration_minutes=100,
        total_price=180.0,
        total_transfers=1,
        modes=["bus", "metro"],
        segments=[
            JourneySegmentSchema(
                segment_id="seg-bmtc-335e",
                sequence=1,
                mode="bus",
                provider="BMTC Volvo",
                vehicle_number="335E",
                vehicle_name="BMTC Volvo Route 335E",
                origin=majestic,
                destination=whitefield,
                departure_time=t0,
                arrival_time=t1,
                duration_minutes=40,
                price=80.0,
                distance_km=20.0,
                carbon_kg=1.2,
                comfort_score=7.5,
                transfer_buffer_minutes=10,
            ),
            JourneySegmentSchema(
                segment_id="seg-metro-purple",
                sequence=2,
                mode="metro",
                provider="Namma Metro",
                vehicle_number="PURPLE",
                vehicle_name="Namma Metro Purple Line",
                origin=whitefield,
                destination=hub_final,
                departure_time=t2,
                arrival_time=t3,
                duration_minutes=50,
                price=100.0,
                distance_km=22.0,
                carbon_kg=0.5,
                comfort_score=8.8,
                transfer_buffer_minutes=15,
            ),
        ],
        carbon_kg=1.7,
        comfort_score=8.2,
        recommendation_category="best_value",
        ai_explanation=AIExplanationSchema(
            summary="Multimodal bus + metro trip", trade_offs=[], rank_reason="Test", score=80.0
        ),
        booking_feasibility=BookingFeasibilitySchema(hold_supported=True, concurrency_safe=True),
    )

    matcher = RouteDisruptionMatcher()
    assessor = JourneyImpactAssessor(matcher=matcher)
    assessment = assessor.assess_journey(journey, [transit_event, false_route_event])

    assert assessment.is_disrupted is True
    assert assessment.provenance == "provider_live"
    assert len(assessment.active_disruptions) == 1
    assert assessment.active_disruptions[0].id == "bmtc-335e-delay"
    assert assessment.total_estimated_delay_minutes == 25
    assert assessment.critical_connection_risk_count >= 1

    recovery = JourneyRecoveryEngine().recover_journey(journey=journey, assessment=assessment)
    assert len(recovery.recommendations) > 0
    for rec in recovery.recommendations:
        assert rec.manual_rebooking_required is True


def test_api_feeds_and_poll_endpoints_sanitized(monkeypatch):
    """Verify API GET /providers/feeds, secured POST /providers/feeds/poll, and GET /health contracts."""
    from app.api.routes.disruptions import poll_rate_limiter
    from app.core.config import settings

    poll_rate_limiter.reset()
    try:
        # Anonymous poll trigger must fail closed with 401
        anon_res = api_client.post("/api/v1/disruptions/providers/feeds/poll?force=false")
        assert anon_res.status_code == 401

        monkeypatch.setattr(settings, "INTERNAL_API_KEY", "m4-test-internal-key")
        res_poll = api_client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=false",
            headers={"X-Internal-Key": "m4-test-internal-key"},
        )
        assert res_poll.status_code == 200
        body = res_poll.json()
        assert "feeds" in body
        assert "totalOperational" in body
        assert "notice" in body

        for feed in body["feeds"]:
            assert "authToken" not in feed
            assert "apiKey" not in feed
            assert "authTokenEnvVar" not in feed
            assert "connectionAttempts" in feed
            assert "availabilityTransitions" in feed

        res_health = api_client.get("/api/v1/disruptions/health")
        assert res_health.status_code == 200
        health_data = res_health.json()
        assert "gtfs_feeds_registered" in health_data
        assert "live_transit_connected" in health_data
    finally:
        poll_rate_limiter.reset()


# ============================================================================
# 4. OPT-IN LIVE NETWORK SMOKE TESTS (RUN_LIVE_PROVIDER_TESTS=1)
# ============================================================================

@pytest.mark.anyio
@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_PROVIDER_TESTS") != "1",
    reason="Opt-in live integration verification requires RUN_LIVE_PROVIDER_TESTS=1",
)
async def test_live_provider_endpoints_smoke():
    """Live verification against TomTom (if key configured) and Indian agency unauthenticated fail-closed gates."""
    from app.core.config import settings
    from app.services.disruption.providers.live_traffic import LiveTrafficIncidentProvider

    # 1. TomTom Orbis live road check
    if settings.TOMTOM_API_KEY:
        tomtom = LiveTrafficIncidentProvider()
        events = await tomtom.fetch_disruptions(bbox=(77.55, 12.90, 77.65, 13.00))
        cap = tomtom.get_capabilities()
        assert cap.connectivity_status == "available"
        assert cap.last_successful_request is not None
        assert all(ev.provenance == "provider_live" for ev in events)

    # 2. Unauthenticated probe against real Indian IUDX / Delhi OTD endpoints fails closed (HTTP 401)
    async with httpx.AsyncClient(timeout=8.0) as http:
        bmtc_res = await http.get(
            "https://rs.cos.iudx.org.in/ngsi-ld/v1/entities?id=8a9c53c2-7291-454e-b173-2d9bfe893eb1"
        )
        assert bmtc_res.status_code in (401, 403)

        delhi_res = await http.get("https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb")
        assert delhi_res.status_code in (401, 403)
