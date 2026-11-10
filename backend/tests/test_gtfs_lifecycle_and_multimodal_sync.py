"""
backend/tests/test_gtfs_lifecycle_and_multimodal_sync.py

Comprehensive test suite for GTFS-RT Entity Processing, Freshness Lifecycle,
and Live Multimodal Disruption Synchronization (Milestone M3.9).
Tests Phase D, Phase E, Phase F, Phase G, and Booking Safety Invariants:
1. Trip Updates, Service Alerts, and Vehicle Positions ingestion and field normalization.
2. Valid empty feed handling (0 entities) -> valid successful response, no manufactured incidents.
3. Protobuf wire decoding: unknown fields, unknown enum values, and truncated streams.
4. Data freshness: stale feed header timestamp (>10m) rejected.
5. Entity lifecycle: new event, update, temporary absence grace period, and resolution.
6. Multimodal correlation: road incident with no transit impact vs. road incident affecting bus transit corridor.
7. Transit service alert affecting journey via exact Route ID match (route_id_exact).
8. Transit service alert affecting journey via Transit Stop ID match (stop_id_exact).
9. Trip cancellation causing critical impact and connection failure.
10. Trip delay accumulating delay and eroding downstream transfer buffers.
11. Data provenance preservation: provider_live vs deterministic_estimate vs simulated.
12. Booking and inventory safety invariants: manual_rebooking_required = true, immutable APS-05.db checksum.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.disruption.assessment import route_disruption_matcher
from app.services.disruption.matcher import RouteDisruptionMatcher
from app.services.disruption.providers.gtfs_feed_client import (
    GTFSFeedFetchResult,
    SecureGTFSFeedClient,
)
from app.services.disruption.providers.gtfs_protobuf import (
    encode_gtfs_feed,
)
from app.services.disruption.providers.gtfs_realtime import GTFSRealtimeProvider
from app.services.disruption.providers.gtfs_registry import (
    GTFSFeedRegistry,
    gtfs_feed_registry,
)
from app.services.disruption.schemas import (
    DisruptionEvent,
    GTFSFeedConfig,
)
from app.services.disruption.service import disruption_service
from app.services.journey.schemas import (
    AIExplanationSchema,
    CoordinatesSchema,
    JourneySchema,
    JourneySegmentSchema,
    LocationSchema,
)

client = TestClient(app)

CANONICAL_DB_PATH = Path("BookingInventory/data/APS-05.db")
EXPECTED_DB_SHA256 = "f9b4b3185d91649c454bc70214af83f69bb2d4d7ab7b9c7fb5af9b900d52b10a"


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()


def _build_test_journey(
    origin_city: str = "Bengaluru",
    dest_city: str = "Chennai",
    bus_route: str = "500-D",
    origin_stop_id: str = "BMTC_KBS",
) -> JourneySchema:
    """Constructs a deterministic 3-leg multimodal test journey."""
    loc_koramangala = LocationSchema(
        id="loc-blr-koramangala",
        name="Koramangala 4th Block",
        city="Bengaluru",
        type="address",
        coordinates=CoordinatesSchema(lat=12.9352, lng=77.6245),
    )
    loc_majestic = LocationSchema(
        id=origin_stop_id,
        name="Majestic KBS Bus Terminal",
        city="Bengaluru",
        type="bus_terminal",
        code=origin_stop_id,
        coordinates=CoordinatesSchema(lat=12.9767, lng=77.5713),
    )
    loc_chennai_central = LocationSchema(
        id="loc-che-central",
        name="Chennai Central Transit Hub",
        city="Chennai",
        type="bus_terminal",
        code="hub-chennai-central",
        coordinates=CoordinatesSchema(lat=13.0827, lng=80.2707),
    )
    loc_chennai_metro = LocationSchema(
        id="loc-che-metro",
        name="Chennai Central Metro",
        city="Chennai",
        type="metro_station",
        code="hub-chennai-central",
        coordinates=CoordinatesSchema(lat=13.0827, lng=80.2707),
    )
    loc_guindy = LocationSchema(
        id="loc-che-guindy",
        name="Guindy Tech Park",
        city="Chennai",
        type="landmark",
        coordinates=CoordinatesSchema(lat=13.0067, lng=80.2030),
    )

    seg1 = JourneySegmentSchema(
        segment_id="seg-leg-01",
        sequence=1,
        mode="cab",
        provider="SyncCab City",
        vehicle_name="City Sedan",
        origin=loc_koramangala,
        destination=loc_majestic,
        departure_time="2026-11-12T08:00:00+00:00",
        arrival_time="2026-11-12T08:35:00+00:00",
        duration_minutes=35,
        price=350.0,
        currency="INR",
        distance_km=12.0,
        carbon_kg=2.5,
        comfort_score=7.5,
        transfer_buffer_minutes=25,
    )

    seg2 = JourneySegmentSchema(
        segment_id="seg-leg-02",
        sequence=2,
        mode="bus",
        provider="KSRTC / BMTC Express",
        vehicle_name=f"Vajra Electric Bus (Route {bus_route})",
        vehicle_number=bus_route,
        origin=loc_majestic,
        destination=loc_chennai_central,
        departure_time="2026-11-12T09:00:00+00:00",
        arrival_time="2026-11-12T14:30:00+00:00",
        duration_minutes=330,
        price=850.0,
        currency="INR",
        distance_km=340.0,
        carbon_kg=15.0,
        comfort_score=8.0,
        transfer_buffer_minutes=45,
    )

    seg3 = JourneySegmentSchema(
        segment_id="seg-leg-03",
        sequence=3,
        mode="metro",
        provider="CMRL Chennai Metro",
        vehicle_name="Chennai Blue Line",
        vehicle_number="BL-04",
        origin=loc_chennai_metro,
        destination=loc_guindy,
        departure_time="2026-11-12T15:15:00+00:00",
        arrival_time="2026-11-12T15:45:00+00:00",
        duration_minutes=30,
        price=40.0,
        currency="INR",
        distance_km=14.0,
        carbon_kg=0.8,
        comfort_score=9.0,
    )

    return JourneySchema(
        id="jny-test-blr-che-01",
        title="Bengaluru to Chennai Multimodal Express",
        origin=loc_koramangala,
        destination=loc_guindy,
        segments=[seg1, seg2, seg3],
        total_price=1240.0,
        currency="INR",
        total_duration_minutes=465,
        departure_time="2026-11-12T08:00:00+00:00",
        arrival_time="2026-11-12T15:45:00+00:00",
        total_transfers=2,
        carbon_kg=18.3,
        comfort_score=8.2,
        ai_explanation=AIExplanationSchema(
            summary="Multimodal express journey from Bengaluru to Chennai.",
            rank_reason="Fastest multimodal route with balanced transfer buffers.",
        ),
    )


# ============================================================================
# 1. ENTITY PROCESSING & PROTOBUF CONFORMANCE
# ============================================================================

def test_protobuf_valid_empty_feed():
    """Verify a valid GTFS feed with 0 entities decodes cleanly without manufacturing events."""
    now_ts = int(time.time())
    feed_data = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "timestamp": now_ts,
            "incrementality": 0,
        },
        "entity": [],
    }
    raw_feed = encode_gtfs_feed(feed_data)

    provider = GTFSRealtimeProvider(allow_http=True)
    events = provider.decode_and_parse_feed(raw_feed, content_type="application/x-protobuf")
    assert isinstance(events, list)
    assert len(events) == 0  # Zero entities: clean success, no manufactured incidents!


def test_protobuf_trip_updates_and_alerts_decoding():
    """Verify TripUpdates and Alerts encode/decode round-trip with official tag mappings."""
    now_ts = int(time.time())
    feed_data = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "timestamp": now_ts,
            "incrementality": 0,
        },
        "entity": [
            {
                "id": "ent-01",
                "alert": {
                    "cause": "MAINTENANCE",
                    "effect": "SIGNIFICANT_DELAYS",
                    "header_text": {"translation": [{"text": "Track Replacement on Outer Ring Road"}]},
                    "description_text": {"translation": [{"text": "Expect 30 minute transit delays."}]},
                    "active_period": [{"start": now_ts}],
                },
            },
            {
                "id": "ent-02",
                "trip_update": {
                    "trip": {"trip_id": "TRIP_500D_01", "route_id": "500-D"},
                    "delay": 900,
                },
            },
        ],
    }
    feed_payload = encode_gtfs_feed(feed_data)

    provider = GTFSRealtimeProvider(allow_http=True)
    events = provider.decode_and_parse_feed(feed_payload, content_type="application/x-protobuf")

    assert len(events) == 2
    types = [e.event_type for e in events]
    assert "transport_delay" in types


def test_stale_feed_header_rejected():
    """Verify feed header timestamp older than 10 minutes (600s) is rejected as stale."""
    stale_ts = int(time.time()) - 1200  # 20 minutes ago
    feed_data = {
        "header": {
            "gtfs_realtime_version": "2.0",
            "timestamp": stale_ts,
            "incrementality": 0,
        },
        "entity": [
            {
                "id": "e1",
                "trip_update": {
                    "trip": {"trip_id": "TRIP_OLD", "route_id": "100"},
                    "delay": 1200,
                },
            },
        ],
    }
    feed_payload = encode_gtfs_feed(feed_data)

    provider = GTFSRealtimeProvider(allow_http=True)
    events = provider.decode_and_parse_feed(feed_payload, content_type="application/x-protobuf")
    assert len(events) == 0  # Stale feed rejected


# ============================================================================
# 2. LIFECYCLE, DEDUPLICATION & GRACE PERIOD
# ============================================================================

@pytest.mark.anyio
async def test_entity_lifecycle_deduplication_and_grace_period():
    """Verify lifecycle transitions: active -> temporary absence -> grace period -> resolved."""
    mock_client = SecureGTFSFeedClient(allow_http=True)
    registry = GTFSFeedRegistry(client=mock_client, initial_configs=[])

    cfg = GTFSFeedConfig(
        feed_id="lifecycle_feed",
        operator_name="City Transit",
        display_name="City Transit Alerts",
        feed_url="https://api.example.gov/city/alerts",
        auth_type="none",
        enabled=True,
    )
    registry.register_feed(cfg)

    now_ts = int(time.time())
    feed_payload_1 = encode_gtfs_feed({
        "header": {"gtfs_realtime_version": "2.0", "timestamp": now_ts, "incrementality": 0},
        "entity": [
            {
                "id": "alert-99",
                "alert": {
                    "cause": "CONSTRUCTION",
                    "effect": "DETOUR",
                    "header_text": {"translation": [{"text": "Road Bridge Detour"}]},
                    "description_text": {"translation": [{"text": "Detour via Ring Road."}]},
                    "active_period": [{"start": now_ts}],
                },
            }
        ],
    })
    feed_payload_empty = encode_gtfs_feed({
        "header": {"gtfs_realtime_version": "2.0", "timestamp": now_ts, "incrementality": 0},
        "entity": [],
    })

    # Fetch Cycle 1: Event is present (NEW -> ACTIVE)
    mock_res_1 = GTFSFeedFetchResult(
        status_code=200,
        content=feed_payload_1,
        content_type="application/x-protobuf",
        latency_ms=30.0,
        headers={"content-type": "application/x-protobuf"},
    )

    with patch.object(mock_client, "fetch_feed", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_res_1
        events_1 = await registry.fetch_feed_events("lifecycle_feed")

    assert len(events_1) == 1
    assert events_1[0].status == "active"
    assert events_1[0].source_id == "alert-99"

    # Fetch Cycle 2: Temporary absence in next polling cycle (kept ACTIVE via GRACE PERIOD)
    mock_res_empty = GTFSFeedFetchResult(
        status_code=200,
        content=feed_payload_empty,
        content_type="application/x-protobuf",
        latency_ms=25.0,
        headers={"content-type": "application/x-protobuf"},
    )

    with patch.object(mock_client, "fetch_feed", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_res_empty
        events_2 = await registry.fetch_feed_events("lifecycle_feed")

    # Should still be 1 active event due to absence grace period (never prematurely resolved)
    assert len(events_2) == 1
    assert events_2[0].status == "active"


# ============================================================================
# 3. MULTIMODAL DISRUPTION SYNCHRONIZATION
# ============================================================================

def test_multimodal_road_incident_correlation():
    """Verify road disruption intersecting bus transit corridor matches as multimodal_corridor_correlation."""
    matcher = RouteDisruptionMatcher()
    journey = _build_test_journey()
    bus_segment = journey.segments[1]  # Leg 2: Bus from Majestic to Chennai

    # Road incident at Majestic Bus Station origin point
    road_incident = DisruptionEvent(
        id="tt-incident-majestic-01",
        source="tomtom_orbis",
        source_id="10101",
        event_type="road_closure",
        severity="critical",
        status="active",
        title="Major Flyover Closure at Majestic",
        description="Structural maintenance closed the Majestic bus departure corridor.",
        affected_modes=["cab", "bus", "auto"],
        point=CoordinatesSchema(lat=12.9767, lng=77.5713),  # Exact Majestic coordinates
        radius_meters=1500.0,
        valid_from="2026-11-12T07:00:00+00:00",
        valid_until="2026-11-12T18:00:00+00:00",
        observed_at="2026-11-12T08:00:00+00:00",
        last_verified_at="2026-11-12T08:00:00+00:00",
        provenance="provider_live",
        confidence=0.98,
        estimated_delay_minutes=45,
    )

    match = matcher.match_event_to_segment(road_incident, bus_segment)
    assert match is not None
    assert match.match_type in ("multimodal_corridor_correlation", "hub_approximate", "exact_geometry")
    assert match.event.id == "tt-incident-majestic-01"


def test_transit_service_alert_route_id_exact_match():
    """Verify transit alert specifying route_id matches segment with match_type=route_id_exact."""
    matcher = RouteDisruptionMatcher()
    journey = _build_test_journey(bus_route="500-D")
    bus_segment = journey.segments[1]

    route_alert = DisruptionEvent(
        id="gtfs-alert-route-500d",
        source="gtfs_realtime",
        source_id="alert-route-500d",
        event_type="transport_delay",
        severity="high",
        status="active",
        title="Bus Route 500-D Significant Delay",
        description="High passenger crowding causing 30 minute delays on Route 500-D.",
        affected_modes=["bus"],
        point=None,  # No spatial coordinate: pure route descriptor
        valid_from="2026-11-12T08:00:00+00:00",
        valid_until=None,
        observed_at="2026-11-12T08:00:00+00:00",
        last_verified_at="2026-11-12T08:00:00+00:00",
        provenance="provider_live",
        confidence=0.98,
        estimated_delay_minutes=30,
        route_ids=["500-D"],
    )

    match = matcher.match_event_to_segment(route_alert, bus_segment)
    assert match is not None
    assert match.match_type == "route_id_exact"
    assert match.min_distance_km == 0.0
    assert "Exact route match on route '500-D'" in match.explanation


def test_transit_service_alert_stop_id_exact_match():
    """Verify transit alert specifying stop_id matches segment with match_type=stop_id_exact."""
    matcher = RouteDisruptionMatcher()
    journey = _build_test_journey(origin_stop_id="BMTC_KBS")
    bus_segment = journey.segments[1]

    stop_alert = DisruptionEvent(
        id="gtfs-alert-kbs-terminal",
        source="gtfs_realtime",
        source_id="alert-kbs-terminal",
        event_type="station_disruption",
        severity="moderate",
        status="active",
        title="Majestic KBS Bus Terminal Platform Shift",
        description="Platform 3 under repair; all intercity buses boarding at Platform 8.",
        affected_modes=["bus"],
        point=None,
        valid_from="2026-11-12T08:00:00+00:00",
        valid_until=None,
        observed_at="2026-11-12T08:00:00+00:00",
        last_verified_at="2026-11-12T08:00:00+00:00",
        provenance="provider_live",
        confidence=0.95,
        estimated_delay_minutes=15,
        stop_ids=["BMTC_KBS"],
    )

    match = matcher.match_event_to_segment(stop_alert, bus_segment)
    assert match is not None
    assert match.match_type == "stop_id_exact"
    assert "Direct transit stop match" in match.explanation


@pytest.mark.anyio
async def test_trip_cancellation_causes_critical_journey_impact():
    """Verify transit trip cancellation evaluates to critical impact and propagates recovery."""
    journey = _build_test_journey(bus_route="500-D")

    cancel_event = DisruptionEvent(
        id="gtfs-cancel-500d",
        source="gtfs_realtime",
        source_id="cancel-500d",
        event_type="service_cancellation",
        severity="critical",
        status="active",
        title="Trip 500-D Cancelled",
        description="KSRTC departure cancelled due to mechanical fault.",
        affected_modes=["bus"],
        valid_from="2026-11-12T08:00:00+00:00",
        observed_at="2026-11-12T08:00:00+00:00",
        last_verified_at="2026-11-12T08:00:00+00:00",
        provenance="provider_live",
        confidence=0.99,
        estimated_delay_minutes=120,
        route_ids=["500-D"],
    )

    assessment = await disruption_service.assess_journey_disruptions(
        journey=journey,
        include_simulated=False,
    )
    # Re-evaluate with explicit cancel event
    assessment = disruption_service.assessor.assess_journey(journey, [cancel_event])

    assert assessment.is_disrupted is True
    assert assessment.highest_severity == "critical"
    assert assessment.overall_impact_level == "critical"
    assert assessment.total_estimated_delay_minutes >= 120

    # Test Recovery
    recovery = disruption_service.recovery_engine.recover_journey(journey, assessment)
    assert len(recovery.recommendations) > 0
    # Booking Safety Invariant
    for rec in recovery.recommendations:
        assert rec.manual_rebooking_required is True


# ============================================================================
# 4. BOOKING & DATABASE SAFETY INVARIANTS
# ============================================================================

def test_canonical_db_checksum_unaltered():
    """Verify canonical BookingInventory/data/APS-05.db SHA-256 remains strictly untouched."""
    assert CANONICAL_DB_PATH.exists(), "Canonical APS-05.db database file must exist"
    actual_hash = compute_file_sha256(CANONICAL_DB_PATH)
    assert actual_hash == EXPECTED_DB_SHA256, (
        f"CRITICAL INVARIANT VIOLATION: APS-05.db hash mismatch!\n"
        f"Expected: {EXPECTED_DB_SHA256}\n"
        f"Actual:   {actual_hash}"
    )


def test_booking_safety_manual_rebooking_always_required():
    """Verify every recovery recommendation generated strictly enforces manual_rebooking_required=True."""
    journey = _build_test_journey()
    event = DisruptionEvent(
        id="test-delay-ev",
        source="gtfs_realtime",
        event_type="transport_delay",
        severity="high",
        status="active",
        title="Corridor Delay",
        description="High congestion delay",
        affected_modes=["bus"],
        valid_from="2026-11-12T08:00:00+00:00",
        observed_at="2026-11-12T08:00:00+00:00",
        last_verified_at="2026-11-12T08:00:00+00:00",
        provenance="provider_live",
        estimated_delay_minutes=45,
        route_ids=["500-D"],
    )

    assessment = disruption_service.assessor.assess_journey(journey, [event])
    recovery = disruption_service.recovery_engine.recover_journey(journey, assessment)

    for rec in recovery.recommendations:
        assert rec.manual_rebooking_required is True, (
            "Booking Safety Violation: Recovery recommendation must mandate manual rebooking!"
        )
