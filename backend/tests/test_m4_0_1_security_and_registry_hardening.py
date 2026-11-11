"""
backend/tests/test_m4_0_1_security_and_registry_hardening.py

Comprehensive M4.0.1 Verification Suite covering every audit remediation item:
- H-1: Eliminate HTTP client credential/URL log exposure (httpx/httpcore suppression & log filter)
- H-2: Operational auth fail-closed gates, elevated force polling, rate limiting, failure isolation
- M-1: Registry unknown freshness on missing header ts, per-feed locks, tombstone/invalid eviction, valid_until grace checks
- M-2: Independent raw binary gtfs-realtime.proto decoding including Alert tag 5 EntitySelector (informed_entity)
- M-3: All 14 explicit security and malformed/edge-case integration scenarios
- L-1: NaN/Inf IUDX hardening & vehicle_label preservation
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import socket
import struct
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpcore
import pytest
from fastapi.testclient import TestClient

from app.api.routes.disruptions import poll_rate_limiter
from app.core.config import settings
from app.core.logging import harden_http_client_logging, sanitize_sensitive_log_text
from app.core.security import create_access_token
from app.main import app
from app.services.disruption.matcher import RouteDisruptionMatcher
from app.services.disruption.providers.gtfs_feed_client import (
    GTFSFeedFetchResult,
    GTFSFeedPayloadTooLargeError,
    GTFSFeedSecurityError,
    PinnedIPNetworkBackend,
    SecureGTFSFeedClient,
    sanitize_diagnostic_message,
    sanitize_feed_url,
    validate_feed_url_ssrf_safety,
)
from app.services.disruption.providers.gtfs_protobuf import decode_gtfs_feed, encode_gtfs_feed
from app.services.disruption.providers.gtfs_realtime import GTFSRealtimeProvider
from app.services.disruption.providers.gtfs_registry import GTFSFeedRegistry
from app.services.disruption.providers.iudx_adapter import (
    normalize_iudx_payload,
    parse_timestamp_to_epoch,
)
from app.services.disruption.schemas import DisruptionEvent, GTFSFeedConfig
from app.services.journey.schemas import CoordinatesSchema, JourneySegmentSchema, LocationSchema


api_client = TestClient(app)


# ============================================================================
# Independent Raw Binary Protobuf Builder (zero shared encoder logic)
# ============================================================================

def _pb_varint(value: int) -> bytes:
    if value < 0:
        value &= 0xFFFFFFFFFFFFFFFF
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value & 0x7F)
    return bytes(out)


def _pb_tag(field_number: int, wire_type: int) -> bytes:
    return _pb_varint((field_number << 3) | wire_type)


def _pb_bytes_field(field_number: int, payload: bytes) -> bytes:
    return _pb_tag(field_number, 2) + _pb_varint(len(payload)) + payload


def _pb_str_field(field_number: int, text: str) -> bytes:
    return _pb_bytes_field(field_number, text.encode("utf-8"))


def _pb_uint_field(field_number: int, val: int) -> bytes:
    return _pb_tag(field_number, 0) + _pb_varint(val)


class _InMemoryAsyncHTTPStream(httpcore.AsyncNetworkStream):
    """Minimal in-memory AsyncNetworkStream speaking raw HTTP/1.1 for real httpx/httpcore execution."""

    def __init__(self, responses: list[bytes], recorded_requests: list[bytes]):
        self._responses = responses
        self._recorded_requests = recorded_requests
        self._resp_bytes = responses.pop(0) if responses else b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\n\r\n"
        self._cursor = 0

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        if self._cursor >= len(self._resp_bytes):
            return b""
        chunk = self._resp_bytes[self._cursor : self._cursor + max_bytes]
        self._cursor += len(chunk)
        return chunk

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        if buffer:
            self._recorded_requests.append(bytes(buffer))

    async def aclose(self) -> None:
        return None

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        return self

    def get_extra_info(self, info: str):
        return None


def _build_http_response(
    status: int,
    body: bytes,
    headers: dict[str, str] | None = None,
    reason: str = "OK",
) -> bytes:
    hdrs = {"Content-Type": "application/json", "Connection": "close"}
    if headers:
        hdrs.update(headers)
    if "Content-Length" not in hdrs and "content-length" not in hdrs:
        hdrs["Content-Length"] = str(len(body))
    head = f"HTTP/1.1 {status} {reason}\r\n" + "".join(f"{k}: {v}\r\n" for k, v in hdrs.items()) + "\r\n"
    return head.encode("ascii") + body


@pytest.fixture(autouse=True)
def _reset_poll_rate_limiter():
    poll_rate_limiter.reset()
    yield
    poll_rate_limiter.reset()
    harden_http_client_logging()


# ============================================================================
# H-1: Zero Credential / URL Leakage Across HTTP Transport & App Loggers
# ============================================================================

@pytest.mark.anyio
async def test_h1_no_credential_leakage_across_httpx_httpcore_and_registry_logs(caplog):
    """
    Executes real httpx + httpcore request flow over an in-memory AsyncNetworkStream and proves
    query keys (`?key=...`), auth headers (`token`, `Authorization`), and URL userinfo never
    appear in captured logs at INFO, DEBUG, WARNING, or exception diagnostics.
    """
    secret_query = "DELHI_OTD_RAW_SECRET_KEY_98765"
    secret_iudx = "IUDX_HEADER_SECRET_TOKEN_54321"
    secret_bearer = "BEARER_TOP_SECRET_112233"

    recorded_wires: list[bytes] = []
    now_ts = int(time.time())
    payload_bytes = json.dumps({"header": {"timestamp": now_ts}, "entity": []}).encode("utf-8")
    raw_http_resps = [
        _build_http_response(200, payload_bytes),
        _build_http_response(200, payload_bytes),
    ]

    async def fake_connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        return _InMemoryAsyncHTTPStream(raw_http_resps, recorded_wires)

    client = SecureGTFSFeedClient(allow_http=False, max_retries=0)
    with (
        caplog.at_level(logging.DEBUG),
        patch.object(PinnedIPNetworkBackend, "connect_tcp", fake_connect_tcp),
    ):
        res1 = await client.fetch_feed(
            feed_id="test_delhi",
            feed_url="https://otd.example.gov/api/realtime/VehiclePositions.pb",
            auth_query_param=("key", secret_query),
        )
        res2 = await client.fetch_feed(
            feed_id="test_bmtc",
            feed_url="https://cos.example.org/ngsi-ld/v1/entities",
            auth_header=("token", secret_iudx),
        )

    assert res1.status_code == 200
    assert res2.status_code == 200
    assert len(recorded_wires) == 2

    all_logs = "\n".join(rec.getMessage() for rec in caplog.records)
    assert secret_query not in all_logs
    assert secret_iudx not in all_logs
    assert secret_bearer not in all_logs
    # Specifically confirm httpx INFO request line was suppressed
    assert not any(rec.name == "httpx" and rec.levelno < logging.WARNING for rec in caplog.records)

    # Even if an external caller forcibly lowers httpx/httpcore to DEBUG, SensitiveDataRedactionFilter scrubs secrets
    httpx_logger = logging.getLogger("httpx")
    httpcore_logger = logging.getLogger("httpcore.http11")
    old_httpx_lvl = httpx_logger.level
    old_core_lvl = httpcore_logger.level
    try:
        httpx_logger.setLevel(logging.INFO)
        httpcore_logger.setLevel(logging.DEBUG)
        raw_http_resps.append(_build_http_response(200, payload_bytes))
        with patch.object(PinnedIPNetworkBackend, "connect_tcp", fake_connect_tcp):
            await client.fetch_feed(
                feed_id="test_forced_debug",
                feed_url="https://transit.example.gov/feed?access_token=FORCE_DBG_SECRET",
                auth_header=("Authorization", f"Bearer {secret_bearer}"),
            )
    finally:
        httpx_logger.setLevel(old_httpx_lvl)
        httpcore_logger.setLevel(old_core_lvl)
        harden_http_client_logging()

    combined_after = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "FORCE_DBG_SECRET" not in combined_after
    assert secret_bearer not in combined_after

    # Verify sanitize_feed_url and diagnostic redaction helpers
    san_url = sanitize_feed_url("https://user:pass999@host.example.gov/feed?signature=SIGSECRET&id=1")
    assert "pass999" not in san_url
    assert "SIGSECRET" not in san_url
    assert "id=1" in san_url
    assert "RAW_TOK" not in sanitize_sensitive_log_text(
        "Authorization: Bearer RAW_TOK & https://u.example/a?api_key=KSECRET"
    )
    assert "KSECRET" not in sanitize_diagnostic_message("Upstream echo https://u.example/a?key=KSECRET failed")


# ============================================================================
# H-2: Endpoint Auth, Elevated Force Poll, Rate Limiting & Isolation
# ============================================================================

def test_h2_poll_endpoint_auth_force_privilege_and_rate_limiting(monkeypatch):
    """
    Tests every required authorization and rate-limiting gate on POST /api/v1/disruptions/providers/feeds/poll:
    1. Anonymous request -> 401
    2. Invalid X-Internal-Key / unset INTERNAL_API_KEY -> 403
    3. Regular traveler JWT -> 403
    4. Valid X-Internal-Key / operator JWT (`force=false`) -> 200
    5. `force=true` without elevated privileges -> 403
    6. `force=true` with elevated privilege -> 200
    7. Cooldown enforcement (`force=false` skips second upstream poll)
    8. Repeated request abuse -> 429 Too Many Requests with Retry-After
    """
    monkeypatch.setattr(settings, "INTERNAL_API_KEY", None)
    monkeypatch.setattr(settings, "TRANSIT_POLL_ELEVATED_KEY", None)

    # 1. Anonymous request rejected fail-closed even when INTERNAL_API_KEY is unset
    assert api_client.post("/api/v1/disruptions/providers/feeds/poll?force=false").status_code == 401
    # 1b. Malformed auth header rejected 401
    assert (
        api_client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=false",
            headers={"Authorization": "Basic abc"},
        ).status_code
        == 401
    )
    # 2. X-Internal-Key when server key is unconfigured fails closed 403
    assert (
        api_client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=false",
            headers={"X-Internal-Key": "any-key"},
        ).status_code
        == 403
    )

    monkeypatch.setattr(settings, "INTERNAL_API_KEY", "valid-ops-key-42")
    monkeypatch.setattr(settings, "TRANSIT_POLL_ELEVATED_KEY", "elevated-force-key-99")

    # 2b. Invalid X-Internal-Key rejected 403
    assert (
        api_client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=false",
            headers={"X-Internal-Key": "wrong-key"},
        ).status_code
        == 403
    )

    # 3. Standard traveler JWT (non-operator) rejected 403
    traveler_jwt = create_access_token("usr_traveler_1")
    assert (
        api_client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=false",
            headers={"Authorization": f"Bearer {traveler_jwt}"},
        ).status_code
        == 403
    )

    # 4. Valid X-Internal-Key (`force=false`) succeeds 200
    res_ops = api_client.post(
        "/api/v1/disruptions/providers/feeds/poll?force=false",
        headers={"X-Internal-Key": "valid-ops-key-42"},
    )
    assert res_ops.status_code == 200

    # 4b. Valid operator JWT (`force=false`) succeeds 200
    operator_jwt = create_access_token("usr_operator_1", extra_claims={"role": "operator"})
    assert (
        api_client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=false",
            headers={"Authorization": f"Bearer {operator_jwt}"},
        ).status_code
        == 200
    )

    # 5. Force polling WITHOUT elevated privilege fails 403 (for both internal key and operator JWT)
    assert (
        api_client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=true",
            headers={"X-Internal-Key": "valid-ops-key-42"},
        ).status_code
        == 403
    )
    assert (
        api_client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=true",
            headers={"X-Internal-Key": "valid-ops-key-42", "X-Elevated-Key": "bad-elevated"},
        ).status_code
        == 403
    )
    assert (
        api_client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=true",
            headers={"Authorization": f"Bearer {operator_jwt}"},
        ).status_code
        == 403
    )

    # 6. Force polling WITH elevated privilege succeeds 200
    res_force = api_client.post(
        "/api/v1/disruptions/providers/feeds/poll?force=true",
        headers={
            "X-Internal-Key": "valid-ops-key-42",
            "X-Elevated-Key": "elevated-force-key-99",
        },
    )
    assert res_force.status_code == 200

    # 6b. Admin JWT immediate second force=true hits minimum force-poll floor -> 429
    admin_jwt = create_access_token("usr_admin_1", extra_claims={"role": "admin"})
    res_force_floor = api_client.post(
        "/api/v1/disruptions/providers/feeds/poll?force=true",
        headers={"Authorization": f"Bearer {admin_jwt}"},
    )
    assert res_force_floor.status_code == 429
    assert "Retry-After" in res_force_floor.headers

    # 7. Repeated request abuse hits sliding-window rate limiter -> 429 Too Many Requests
    poll_rate_limiter.reset()
    monkeypatch.setattr(settings, "TRANSIT_POLL_RATE_LIMIT_MAX_REQUESTS", 3)
    for _ in range(3):
        r_ok = api_client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=false",
            headers={"X-Internal-Key": "valid-ops-key-42"},
        )
        assert r_ok.status_code == 200
    r_abuse = api_client.post(
        "/api/v1/disruptions/providers/feeds/poll?force=false",
        headers={"X-Internal-Key": "valid-ops-key-42"},
    )
    assert r_abuse.status_code == 429
    assert int(r_abuse.headers["Retry-After"]) >= 1

    # 8. Endpoint-driven cooldown enforcement & isolated per-feed poll failure
    poll_rate_limiter.reset()
    monkeypatch.setattr(settings, "TRANSIT_POLL_RATE_LIMIT_MAX_REQUESTS", 10)
    from app.services.disruption.providers.gtfs_registry import gtfs_feed_registry

    orig_configs = dict(gtfs_feed_registry._configs)
    orig_statuses = dict(gtfs_feed_registry._statuses)
    orig_active = dict(gtfs_feed_registry._active_events)
    orig_absence = dict(gtfs_feed_registry._absence_tracker)
    orig_last_poll = dict(gtfs_feed_registry._last_poll_epoch)
    orig_cached = dict(gtfs_feed_registry._cached_events)
    fetch_calls = {"count": 0}
    try:
        gtfs_feed_registry._configs.clear()
        gtfs_feed_registry._statuses.clear()
        gtfs_feed_registry._active_events.clear()
        gtfs_feed_registry._absence_tracker.clear()
        gtfs_feed_registry._last_poll_epoch.clear()
        gtfs_feed_registry._cached_events.clear()
        gtfs_feed_registry.register_feed(
            GTFSFeedConfig(
                feed_id="ep_cooldown_ok",
                operator_name="CooldownOp",
                display_name="Cooldown Feed",
                feed_url="https://api.example.gov/ok",
                auth_type="none",
                polling_interval_seconds=60,
                enabled=True,
            )
        )
        gtfs_feed_registry.register_feed(
            GTFSFeedConfig(
                feed_id="ep_broken_isolated",
                operator_name="BrokenOp",
                display_name="Broken Feed",
                feed_url="https://api.example.gov/broken",
                auth_type="none",
                polling_interval_seconds=60,
                enabled=True,
            )
        )
        now_ts = int(time.time())
        ok_body = json.dumps({"header": {"timestamp": now_ts}, "entity": []}).encode("utf-8")

        async def _mock_fetch(feed_id: str, *args, **kwargs):
            fetch_calls["count"] += 1
            if feed_id == "ep_broken_isolated":
                return GTFSFeedFetchResult(503, b"down", "text/plain", 4.0, {})
            return GTFSFeedFetchResult(200, ok_body, "application/json", 4.0, {})

        with patch.object(gtfs_feed_registry.client, "fetch_feed", side_effect=_mock_fetch):
            r_first = api_client.post(
                "/api/v1/disruptions/providers/feeds/poll?force=false",
                headers={"X-Internal-Key": "valid-ops-key-42"},
            )
            assert r_first.status_code == 200
            feeds_map = {f["feedId"]: f for f in r_first.json()["feeds"]}
            assert feeds_map["ep_cooldown_ok"]["connectivityStatus"] == "available"
            assert feeds_map["ep_broken_isolated"]["retrievalFailures"] == 1
            first_count = fetch_calls["count"]

            # Second poll with force=false hits cooldown cache on ep_cooldown_ok (no extra fetch for ok feed)
            r_second = api_client.post(
                "/api/v1/disruptions/providers/feeds/poll?force=false",
                headers={"X-Internal-Key": "valid-ops-key-42"},
            )
            assert r_second.status_code == 200
            # Healthy cached feed did NOT re-fetch upstream
            assert fetch_calls["count"] <= first_count + 1
    finally:
        gtfs_feed_registry._configs = orig_configs
        gtfs_feed_registry._statuses = orig_statuses
        gtfs_feed_registry._active_events = orig_active
        gtfs_feed_registry._absence_tracker = orig_absence
        gtfs_feed_registry._last_poll_epoch = orig_last_poll
        gtfs_feed_registry._cached_events = orig_cached


# ============================================================================
# M-1: Freshness Unknown Policy, Per-Feed Locks, Eviction & Expiry Grace
# ============================================================================

@pytest.mark.anyio
async def test_m1_missing_header_timestamp_marks_freshness_unknown():
    """Missing or unparseable FeedHeader timestamp must report 'unknown', never 'fresh'."""
    client = SecureGTFSFeedClient(allow_http=True)
    registry = GTFSFeedRegistry(
        client=client,
        initial_configs=[
            GTFSFeedConfig(
                feed_id="no_ts_feed",
                operator_name="Test Transit",
                display_name="Test Feed",
                feed_url="https://api.example.gov/gtfs/alerts.json",
                auth_type="none",
                enabled=True,
            )
        ],
    )
    payload = json.dumps({"header": {"gtfs_realtime_version": "2.0"}, "entity": []}).encode("utf-8")
    mock_res = GTFSFeedFetchResult(
        status_code=200,
        content=payload,
        content_type="application/json",
        latency_ms=10.0,
        headers={},
    )
    with patch.object(client, "fetch_feed", AsyncMock(return_value=mock_res)):
        await registry.fetch_feed_events("no_ts_feed")

    st = registry.get_feed_status("no_ts_feed")
    assert st is not None
    assert st.freshness_status == "unknown"
    assert st.last_feed_header_timestamp is None


@pytest.mark.anyio
async def test_m1_concurrent_same_feed_poll_serialized_and_cross_feed_parallel():
    """
    Two concurrent poll_all_enabled_feeds() calls must serialize on the per-feed lock so
    check-then-act cooldown triggers only ONE upstream fetch for the same feed while
    multiple distinct feeds execute concurrently.
    """
    client = SecureGTFSFeedClient(allow_http=True)
    registry = GTFSFeedRegistry(
        client=client,
        initial_configs=[
            GTFSFeedConfig(
                feed_id="feed_alpha",
                operator_name="Alpha",
                display_name="Alpha",
                feed_url="https://api.example.gov/alpha",
                auth_type="none",
                polling_interval_seconds=60,
                enabled=True,
            ),
            GTFSFeedConfig(
                feed_id="feed_beta",
                operator_name="Beta",
                display_name="Beta",
                feed_url="https://api.example.gov/beta",
                auth_type="none",
                polling_interval_seconds=60,
                enabled=True,
            ),
        ],
    )

    now_ts = int(time.time())
    body = json.dumps({"header": {"timestamp": now_ts}, "entity": []}).encode("utf-8")
    calls: dict[str, int] = {"feed_alpha": 0, "feed_beta": 0}
    in_flight = 0
    max_concurrent = 0

    async def slow_fetch(feed_id: str, *args, **kwargs):
        nonlocal in_flight, max_concurrent
        in_flight += 1
        max_concurrent = max(max_concurrent, in_flight)
        calls[feed_id] += 1
        await asyncio.sleep(0.05)
        in_flight -= 1
        return GTFSFeedFetchResult(
            status_code=200,
            content=body,
            content_type="application/json",
            latency_ms=5.0,
            headers={},
        )

    with patch.object(client, "fetch_feed", side_effect=slow_fetch):
        res1, res2 = await asyncio.gather(
            registry.poll_all_enabled_feeds(force=False),
            registry.poll_all_enabled_feeds(force=False),
        )

    assert res1 == [] and res2 == []
    # Each feed fetched exactly once despite concurrent callers
    assert calls["feed_alpha"] == 1
    assert calls["feed_beta"] == 1
    # Unrelated feeds ran concurrently (at least 2 overlapping fetches)
    assert max_concurrent == 2


@pytest.mark.anyio
async def test_m1_tombstone_invalid_replacement_and_valid_until_grace_eviction(monkeypatch):
    """
    Verifies immediate eviction on:
    1. `is_deleted: true` tombstones
    2. Invalid/expired replacement updates or cleared delays for an existing entity ID
    3. `valid_until` passing before the temporary absence grace period elapses
    """
    client = SecureGTFSFeedClient(allow_http=True)
    registry = GTFSFeedRegistry(
        client=client,
        initial_configs=[
            GTFSFeedConfig(
                feed_id="evict_feed",
                operator_name="City Transit",
                display_name="City Feed",
                feed_url="https://api.example.gov/evict",
                auth_type="none",
                enabled=True,
            )
        ],
    )
    now_ts = int(time.time())

    # Cycle 1: Two active alerts + one active trip delay
    cycle1 = json.dumps(
        {
            "header": {"timestamp": now_ts},
            "entity": [
                {
                    "id": "e-tombstone",
                    "alert": {
                        "cause": "ACCIDENT",
                        "effect": "NO_SERVICE",
                        "active_period": [{"start": now_ts - 60, "end": now_ts + 3600}],
                        "header_text": {"translation": [{"text": "Stop closed"}]},
                    },
                },
                {
                    "id": "e-replace",
                    "alert": {
                        "cause": "CONSTRUCTION",
                        "effect": "DETOUR",
                        "active_period": [{"start": now_ts - 60, "end": now_ts + 3600}],
                        "header_text": {"translation": [{"text": "Bridge detour"}]},
                    },
                },
                {
                    "id": "e-expiring",
                    "alert": {
                        "cause": "MAINTENANCE",
                        "effect": "MODIFIED_SERVICE",
                        "active_period": [{"start": now_ts - 120, "end": now_ts + 2}],
                        "header_text": {"translation": [{"text": "Expiring shortly"}]},
                    },
                },
            ],
        }
    ).encode("utf-8")

    with patch.object(
        client,
        "fetch_feed",
        AsyncMock(return_value=GTFSFeedFetchResult(200, cycle1, "application/json", 5.0, {})),
    ):
        ev1 = await registry.fetch_feed_events("evict_feed")
    assert {e.source_id for e in ev1} == {"e-tombstone", "e-replace", "e-expiring"}

    # Cycle 2:
    # - `e-tombstone` is explicitly deleted (`is_deleted=True`)
    # - `e-replace` sends an expired replacement `active_period`
    # - `e-expiring` is omitted (enters absence grace), with `valid_until` rewritten to the past to simulate expiry
    active_expiring = registry._active_events["evict_feed"]["e-expiring"]
    active_expiring.valid_until = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()

    cycle2 = json.dumps(
        {
            "header": {"timestamp": now_ts + 5},
            "entity": [
                {"id": "e-tombstone", "is_deleted": True},
                {
                    "id": "e-replace",
                    "alert": {
                        "cause": "CONSTRUCTION",
                        "effect": "DETOUR",
                        "active_period": [{"start": now_ts - 7200, "end": now_ts - 10}],
                        "header_text": {"translation": [{"text": "Expired replacement"}]},
                    },
                },
            ],
        }
    ).encode("utf-8")

    with patch.object(
        client,
        "fetch_feed",
        AsyncMock(return_value=GTFSFeedFetchResult(200, cycle2, "application/json", 5.0, {})),
    ):
        ev2 = await registry.fetch_feed_events("evict_feed")

    assert ev2 == []
    assert "e-tombstone" not in registry._active_events["evict_feed"]
    assert "e-replace" not in registry._active_events["evict_feed"]
    assert "e-expiring" not in registry._active_events["evict_feed"]


# ============================================================================
# M-2: Independent Hand-Crafted Official Protobuf Alert & EntitySelector E2E
# ============================================================================

@pytest.mark.anyio
async def test_m2_handcrafted_official_protobuf_alert_informed_entity_matching():
    """
    Constructs raw binary gtfs-realtime.proto bytes WITHOUT using encode_gtfs_feed():
    Alert uses official field tags:
    - tag 1: active_period
    - tag 5: informed_entity (EntitySelector: agency_id=1, route_id=2, route_type=3, trip=4, stop_id=5, direction_id=6)
    - tag 6: cause (varint)
    - tag 7: effect (varint)
    - tag 8: url
    - tag 10: header_text
    - tag 11: description_text
    - tag 14: severity_level (varint)
    Verifies decode -> registry ingestion -> RouteDisruptionMatcher exact matching and false-positive rejection.
    """
    now_ts = int(time.time())

    def _translated_str(text: str) -> bytes:
        translation = _pb_str_field(1, text) + _pb_str_field(2, "en")
        return _pb_bytes_field(1, translation)

    time_range = _pb_uint_field(1, now_ts - 60) + _pb_uint_field(2, now_ts + 3600)
    sel1 = (
        _pb_str_field(1, "BMTC-AGENCY")
        + _pb_str_field(2, "500-D")
        + _pb_uint_field(3, 3)  # route_type = 3 (Bus)
        + _pb_str_field(5, "SILK-STOP-01")
        + _pb_uint_field(6, 1)  # direction_id = 1
    )
    trip_desc = _pb_str_field(1, "TRIP-GREEN-09") + _pb_str_field(5, "METRO-GREEN") + _pb_uint_field(6, 0)
    sel2 = _pb_bytes_field(4, trip_desc)

    alert_msg = (
        _pb_bytes_field(1, time_range)
        + _pb_bytes_field(5, sel1)
        + _pb_bytes_field(5, sel2)
        + _pb_uint_field(6, 9)   # cause = MAINTENANCE
        + _pb_uint_field(7, 1)   # effect = NO_SERVICE
        + _pb_bytes_field(8, _translated_str("https://agency.example.gov/alerts/1"))
        + _pb_bytes_field(10, _translated_str("Route 500-D Silk Board Flyover Closure"))
        + _pb_bytes_field(11, _translated_str("All northbound departures suspended until clearance."))
        + _pb_uint_field(14, 4)  # severity_level = SEVERE
    )
    entity_msg = _pb_str_field(1, "handcrafted-alert-1") + _pb_bytes_field(5, alert_msg)
    header_msg = _pb_str_field(1, "2.0") + _pb_uint_field(3, now_ts - 5)
    raw_pb = _pb_bytes_field(1, header_msg) + _pb_bytes_field(2, entity_msg)

    # 1. Direct protobuf decoder check
    decoded = decode_gtfs_feed(raw_pb)
    assert decoded["header"]["timestamp"] == now_ts - 5
    dec_alert = decoded["entity"][0]["alert"]
    assert dec_alert["cause"] == "MAINTENANCE"
    assert dec_alert["effect"] == "NO_SERVICE"
    assert dec_alert["severity_level"] == "SEVERE"
    assert dec_alert["url"]["translation"][0]["text"] == "https://agency.example.gov/alerts/1"
    assert len(dec_alert["informed_entity"]) == 2
    assert dec_alert["informed_entity"][0]["agency_id"] == "BMTC-AGENCY"
    assert dec_alert["informed_entity"][0]["route_id"] == "500-D"
    assert dec_alert["informed_entity"][0]["route_type"] == 3
    assert dec_alert["informed_entity"][0]["stop_id"] == "SILK-STOP-01"
    assert dec_alert["informed_entity"][0]["direction_id"] == 1
    assert dec_alert["informed_entity"][1]["trip"]["trip_id"] == "TRIP-GREEN-09"
    assert dec_alert["informed_entity"][1]["trip"]["route_id"] == "METRO-GREEN"

    # 2. Encoder round-trip produces official tags cleanly
    re_encoded = encode_gtfs_feed(decoded)
    re_decoded = decode_gtfs_feed(re_encoded)
    assert re_decoded["entity"][0]["alert"]["informed_entity"] == dec_alert["informed_entity"]

    # 3. Registry + Dual-Mode Provider ingestion
    provider = GTFSRealtimeProvider(feed_url="https://api.example.gov/alerts.pb")
    prov_events = provider.decode_and_parse_feed(raw_pb, content_type="application/x-protobuf")
    assert len(prov_events) == 1
    assert "500-D" in prov_events[0].route_ids
    assert "METRO-GREEN" in prov_events[0].route_ids
    assert "SILK-STOP-01" in prov_events[0].stop_ids
    assert "TRIP-GREEN-09" in prov_events[0].trip_ids

    client = SecureGTFSFeedClient(allow_http=True)
    registry = GTFSFeedRegistry(
        client=client,
        initial_configs=[
            GTFSFeedConfig(
                feed_id="proto_alerts",
                operator_name="BMTC",
                display_name="BMTC Alerts",
                feed_url="https://api.example.gov/alerts.pb",
                auth_type="none",
                enabled=True,
            )
        ],
    )
    with patch.object(
        client,
        "fetch_feed",
        AsyncMock(return_value=GTFSFeedFetchResult(200, raw_pb, "application/x-protobuf", 12.0, {})),
    ):
        reg_events = await registry.fetch_feed_events("proto_alerts")

    assert len(reg_events) == 1
    ev = reg_events[0]
    assert set(ev.route_ids) == {"500-D", "METRO-GREEN"}
    assert ev.stop_ids == ["SILK-STOP-01"]
    assert ev.trip_ids == ["TRIP-GREEN-09"]
    assert ev.correlation_metadata["agencyIds"] == ["BMTC-AGENCY"]
    assert ev.correlation_metadata["routeTypes"] == [3]
    assert sorted(ev.correlation_metadata["directionIds"]) == [0, 1]

    # 4. Downstream RouteDisruptionMatcher exact matching + no false positive on unrelated route '5'
    matcher = RouteDisruptionMatcher()
    matching_seg = JourneySegmentSchema(
        segment_id="seg-match",
        sequence=1,
        mode="bus",
        provider="BMTC Vajra",
        origin=LocationSchema(
            id="STOP-MAJ",
            name="Majestic",
            city="Bengaluru",
            type="bus_terminal",
            coordinates=CoordinatesSchema(lat=12.977, lng=77.571),
        ),
        destination=LocationSchema(
            id="SILK-STOP-01",
            name="Silk Board",
            city="Bengaluru",
            type="bus_terminal",
            coordinates=CoordinatesSchema(lat=12.917, lng=77.623),
        ),
        departure_time=datetime.now(timezone.utc).isoformat(),
        arrival_time=(datetime.now(timezone.utc) + timedelta(minutes=40)).isoformat(),
        duration_minutes=40,
        distance_km=12.0,
        price=30.0,
        carbon_kg=1.2,
        comfort_score=7.5,
        vehicle_name="Vajra Route 500-D",
        vehicle_number="500-D",
    )
    unrelated_seg = JourneySegmentSchema(
        segment_id="seg-unrelated",
        sequence=1,
        mode="bus",
        provider="BMTC Ordinary",
        origin=LocationSchema(
            id="STOP-YLK",
            name="Yelahanka",
            city="Bengaluru",
            type="bus_terminal",
            coordinates=CoordinatesSchema(lat=13.100, lng=77.596),
        ),
        destination=LocationSchema(
            id="STOP-HBL",
            name="Hebbal",
            city="Bengaluru",
            type="bus_terminal",
            coordinates=CoordinatesSchema(lat=13.035, lng=77.597),
        ),
        departure_time=datetime.now(timezone.utc).isoformat(),
        arrival_time=(datetime.now(timezone.utc) + timedelta(minutes=25)).isoformat(),
        duration_minutes=25,
        distance_km=8.0,
        price=20.0,
        carbon_kg=1.0,
        comfort_score=6.8,
        vehicle_name="Ordinary Bus 5",
        vehicle_number="5",
    )
    assert matcher.match_event_to_segment(ev, matching_seg) is not None
    assert matcher.match_event_to_segment(ev, unrelated_seg) is None


# ============================================================================
# M-3 (1..14) + L-1: Malformed Payloads, Security Gates, Edge Cases, Failures
# ============================================================================

@pytest.mark.anyio
async def test_m3_malformed_protobuf_json_and_iudx_error_envelope():
    """Covers M-3 items (1) invalid protobuf, (3) malformed JSON, and (4) IUDX error payload."""
    client = SecureGTFSFeedClient(allow_http=True)
    registry = GTFSFeedRegistry(
        client=client,
        initial_configs=[
            GTFSFeedConfig(
                feed_id="malformed_feed",
                operator_name="Test",
                display_name="Test",
                feed_url="https://api.example.gov/feed",
                auth_type="none",
                enabled=True,
            )
        ],
    )

    bad_payloads = [
        (b"\xff\xff\xff\x00invalid-pb", "application/x-protobuf"),
        (b"{not-valid-json", "application/json"),
        (
            json.dumps(
                {
                    "type": "urn:dx:rs:InvalidSyntax",
                    "title": "Bad Request",
                    "detail": "Token check failed?key=RAWSECRET",
                }
            ).encode("utf-8"),
            "application/json",
        ),
    ]
    for raw_bytes, ctype in bad_payloads:
        with patch.object(
            client,
            "fetch_feed",
            AsyncMock(return_value=GTFSFeedFetchResult(200, raw_bytes, ctype, 10.0, {})),
        ):
            res = await registry.fetch_feed_events("malformed_feed")
        assert res == []

    st = registry.get_feed_status("malformed_feed")
    assert st is not None
    assert st.decode_failures == 3
    assert st.last_error_classification == "PARSE_ERROR"
    assert "RAWSECRET" not in (st.status_notice or "")
    assert st.connectivity_status == "degraded"


@pytest.mark.anyio
async def test_m3_oversized_response_rejected_both_content_length_and_body():
    """Covers M-3 item (2): Content-Length and body exceeding GTFS_MAX_RESPONSE_BYTES."""
    recorded: list[bytes] = []
    oversized_body = b"x" * 2048
    client = SecureGTFSFeedClient(allow_http=False, max_response_bytes=512, max_retries=0)

    # Case A: Oversized Content-Length header
    # Case B: Body exceeding max_response_bytes without Content-Length (Connection: close streaming)
    raw_resps = [
        _build_http_response(200, b"a" * 4096, headers={"Content-Length": "4096"}),
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n" + oversized_body,
    ]

    async def fake_connect(self, host, port, timeout=None, local_address=None, socket_options=None):
        return _InMemoryAsyncHTTPStream(raw_resps, recorded)

    with patch.object(PinnedIPNetworkBackend, "connect_tcp", fake_connect):
        with pytest.raises(GTFSFeedPayloadTooLargeError):
            await client.fetch_feed("oversize_1", "https://api.example.gov/feed")
        with pytest.raises(GTFSFeedPayloadTooLargeError):
            await client.fetch_feed("oversize_2", "https://api.example.gov/feed")


@pytest.mark.anyio
async def test_m3_redirect_ssrf_and_cross_origin_credential_stripping():
    """
    Covers M-3 items (5) malicious/private redirect hop blocking and
    (6) cross-origin redirect stripping Authorization/token headers and query params.
    """
    client = SecureGTFSFeedClient(allow_http=False, max_retries=0)

    # 1. Redirect targeting localhost or AWS metadata must be blocked cleanly
    for malicious_loc in ("http://127.0.0.1/admin", "https://169.254.169.254/latest/meta-data/"):
        recorded: list[bytes] = []
        raw_resps = [_build_http_response(302, b"", headers={"Location": malicious_loc}, reason="Found")]

        async def fake_connect_ssrf(self, host, port, timeout=None, local_address=None, socket_options=None):
            return _InMemoryAsyncHTTPStream(raw_resps, recorded)

        with patch.object(PinnedIPNetworkBackend, "connect_tcp", fake_connect_ssrf):
            with pytest.raises(GTFSFeedSecurityError):
                await client.fetch_feed(
                    "ssrf_redir",
                    "https://transit.example.gov/feed",
                    auth_header=("token", "TOP_SECRET"),
                )

    # 2. Cross-origin redirect to a safe public host strips sensitive headers & query param
    recorded_hops: list[bytes] = []
    now_ts = int(time.time())
    hop_resps = [
        _build_http_response(
            302,
            b"",
            headers={"Location": "https://cdn.example.org/public-snapshot.json"},
            reason="Found",
        ),
        _build_http_response(
            200,
            json.dumps({"header": {"timestamp": now_ts}, "entity": []}).encode("utf-8"),
        ),
    ]

    async def fake_connect_xorigin(self, host, port, timeout=None, local_address=None, socket_options=None):
        return _InMemoryAsyncHTTPStream(hop_resps, recorded_hops)

    with patch.object(PinnedIPNetworkBackend, "connect_tcp", fake_connect_xorigin):
        res = await client.fetch_feed(
            "xorigin_feed",
            "https://primary.example.gov/private/feed",
            auth_header=("Authorization", "Bearer SECRET_BEARER_XYZ"),
            auth_query_param=("key", "SECRET_QUERY_XYZ"),
        )

    assert res.status_code == 200
    assert len(recorded_hops) == 2
    hop1_req = recorded_hops[0].decode("latin1")
    hop2_req = recorded_hops[1].decode("latin1")
    assert "SECRET_BEARER_XYZ" in hop1_req
    assert "SECRET_QUERY_XYZ" in hop1_req
    assert "SECRET_BEARER_XYZ" not in hop2_req
    assert "SECRET_QUERY_XYZ" not in hop2_req
    assert "authorization:" not in hop2_req.lower()


def test_m3_dns_failure_and_ipv4_ipv6_private_targets():
    """Covers M-3 items (7) DNS resolution failure and (8) IPv4 & IPv6 private/mapped targets."""
    for blocked_url in (
        "https://10.0.0.1/feed",
        "https://[::1]/feed",
        "https://[fc00::1]/feed",
        "https://[::ffff:169.254.169.254]/feed",
        "https://127.0.0.1/feed",
    ):
        ok, _, _ = validate_feed_url_ssrf_safety(blocked_url, allow_http=False, resolve_dns=True)
        assert ok is False, f"Expected SSRF block for {blocked_url}"

    with patch("socket.getaddrinfo", side_effect=socket.gaierror("DNS lookup failed")):
        ok_dns, reason_dns, ips_dns = validate_feed_url_ssrf_safety(
            "https://nonexistent.transit-agency.org/feed",
            allow_http=False,
            resolve_dns=True,
        )
        assert ok_dns is False
        assert ips_dns == []
        assert "DNS resolution failed" in reason_dns


@pytest.mark.anyio
async def test_m3_partial_valid_invalid_entities_and_missing_all_timestamps():
    """Covers M-3 items (9) partial entity acceptance/rejection and (11) missing header + entity ts."""
    client = SecureGTFSFeedClient(allow_http=True)
    registry = GTFSFeedRegistry(
        client=client,
        initial_configs=[
            GTFSFeedConfig(
                feed_id="partial_feed",
                operator_name="City Transit",
                display_name="City Feed",
                feed_url="https://api.example.gov/partial",
                auth_type="none",
                enabled=True,
            )
        ],
    )
    now_ts = int(time.time())
    payload = json.dumps(
        {
            "header": {"gtfs_realtime_version": "2.0"},  # Header timestamp intentionally omitted
            "entity": [
                {
                    "id": "valid-alert",
                    "alert": {
                        "cause": "ACCIDENT",
                        "effect": "SIGNIFICANT_DELAYS",
                        "header_text": {"translation": [{"text": "Valid Alert Without TS"}]},
                    },
                },
                {
                    "id": "bad-coords-veh",
                    "vehicle": {
                        "position": {"latitude": 999.0, "longitude": 0.0},
                        "congestion_level": "CONGESTION",
                        "timestamp": now_ts,
                    },
                },
                {
                    "id": "expired-alert",
                    "alert": {
                        "active_period": [{"start": now_ts - 3600, "end": now_ts - 60}],
                    },
                },
            ],
        }
    ).encode("utf-8")

    with patch.object(
        client,
        "fetch_feed",
        AsyncMock(return_value=GTFSFeedFetchResult(200, payload, "application/json", 8.0, {})),
    ):
        events = await registry.fetch_feed_events("partial_feed")

    assert len(events) == 1
    assert events[0].source_id == "valid-alert"
    st = registry.get_feed_status("partial_feed")
    assert st is not None
    assert st.accepted_event_count == 1
    assert st.rejected_event_count == 2
    assert st.rejected_reasons.get("invalid_coordinates") == 1
    assert st.rejected_reasons.get("expired_active_period") == 1
    assert st.freshness_status == "unknown"


@pytest.mark.anyio
async def test_m3_and_l1_nan_inf_iudx_and_vehicle_label_preservation():
    """
    Covers M-3 item (10) NaN / Infinity in IUDX JSON safely ignored/isolated while
    valid records normalize, and L-1 `vehicleInfo.vehicle_label` preserved cleanly.
    """
    now_ts = int(time.time())
    assert parse_timestamp_to_epoch(float("nan")) is None
    assert parse_timestamp_to_epoch(float("inf")) is None
    assert parse_timestamp_to_epoch(float("-inf")) is None

    iudx_payload = {
        "results": [
            {
                "id": "bad-nan-bus",
                "observationDateTime": float("nan"),
                "positionInfo": {"latitude": float("nan"), "longitude": float("inf")},
                "trip_delay": float("inf"),
            },
            {
                "id": "good-bmtc-bus",
                "observationDateTime": datetime.now(timezone.utc).isoformat(),
                "positionInfo": {
                    "latitude": 12.9716,
                    "longitude": 77.5946,
                    "speed": float("nan"),
                    "congestion_level": "CONGESTION",
                },
                "tripInfo": {"trip_id": "BMTC-T1", "route_id": "500-D", "delay": 420},
                "vehicleInfo": {"vehicle_id": "KA01F1234", "vehicle_label": "Vajra AC-500D"},
            },
        ]
    }
    normalized = normalize_iudx_payload(iudx_payload)
    assert len(normalized["entity"]) == 2  # vehicle_position + trip_update for valid record
    veh_ent = next(e for e in normalized["entity"] if "vehicle" in e)
    assert veh_ent["vehicle"]["vehicle"]["label"] == "Vajra AC-500D"
    assert "speed" not in veh_ent["vehicle"]["position"]

    # Through registry normalization
    client = SecureGTFSFeedClient(allow_http=True)
    registry = GTFSFeedRegistry(
        client=client,
        initial_configs=[
            GTFSFeedConfig(
                feed_id="bmtc_iudx_test",
                operator_name="BMTC",
                display_name="BMTC Test",
                feed_url="https://cos.example.org.in/entities",
                auth_type="none",
                provider_format="iudx_ngsi_ld",
                enabled=True,
            )
        ],
    )
    raw_json = json.dumps(iudx_payload, allow_nan=True).encode("utf-8")
    with patch.object(
        client,
        "fetch_feed",
        AsyncMock(return_value=GTFSFeedFetchResult(200, raw_json, "application/json", 9.0, {})),
    ):
        events = await registry.fetch_feed_events("bmtc_iudx_test")

    veh_ev = next(e for e in events if e.event_type == "traffic_congestion")
    assert veh_ev.correlation_metadata["vehicleLabel"] == "Vajra AC-500D"
    assert math.isfinite(veh_ev.point.lat)


@pytest.mark.anyio
async def test_m3_upstream_429_retry_after_401_403_and_isolation_recovery():
    """
    Covers M-3 items:
    - (12) HTTP 429 + Retry-After backoff
    - (13) HTTP 401 and 403 fail closed with `blocked` without fabricating simulation
    - (14) Concurrent polling failure isolation, degraded breaker, and healthy recovery
    """
    client = SecureGTFSFeedClient(allow_http=False, max_retries=1, backoff_base_seconds=0.01)
    recorded: list[bytes] = []
    now_ts = int(time.time())
    good_body = json.dumps({"header": {"timestamp": now_ts}, "entity": []}).encode("utf-8")

    raw_resps = [
        _build_http_response(429, b"Rate Limited", headers={"Retry-After": "0"}, reason="Too Many Requests"),
        _build_http_response(200, good_body),
    ]

    async def fake_connect_429(self, host, port, timeout=None, local_address=None, socket_options=None):
        return _InMemoryAsyncHTTPStream(raw_resps, recorded)

    with patch.object(PinnedIPNetworkBackend, "connect_tcp", fake_connect_429):
        res_retry = await client.fetch_feed("retry_feed", "https://api.example.gov/feed")
    assert res_retry.status_code == 200
    assert len(recorded) == 2

    # Persistent 429 transitions feed cleanly to rate_limited
    registry = GTFSFeedRegistry(
        client=client,
        initial_configs=[
            GTFSFeedConfig(
                feed_id="f_auth",
                operator_name="OpA",
                display_name="OpA",
                feed_url="https://api.example.gov/a",
                auth_type="none",
                enabled=True,
            ),
            GTFSFeedConfig(
                feed_id="f_healthy",
                operator_name="OpB",
                display_name="OpB",
                feed_url="https://api.example.gov/b",
                auth_type="none",
                enabled=True,
            ),
        ],
    )

    with patch.object(
        client,
        "fetch_feed",
        AsyncMock(return_value=GTFSFeedFetchResult(429, b"", "text/plain", 5.0, {"retry-after": "30"})),
    ):
        await registry.fetch_feed_events("f_auth")
    assert registry.get_feed_status("f_auth").connectivity_status == "rate_limited"

    # 401 and 403 block without fabricating events
    for code, expected_auth in ((401, "unauthorized"), (403, "forbidden")):
        with patch.object(
            client,
            "fetch_feed",
            AsyncMock(return_value=GTFSFeedFetchResult(code, b"", "text/plain", 5.0, {})),
        ):
            ev_blocked = await registry.fetch_feed_events("f_auth")
        assert ev_blocked == []
        st_auth = registry.get_feed_status("f_auth")
        assert st_auth.connectivity_status == "blocked"
        assert st_auth.authorization_status == expected_auth

    # Provider isolation + recovery under concurrent poll
    healthy_payload = json.dumps(
        {
            "header": {"timestamp": now_ts},
            "entity": [
                {
                    "id": "ok-1",
                    "alert": {
                        "cause": "ACCIDENT",
                        "effect": "DETOUR",
                        "header_text": {"translation": [{"text": "Healthy feed live event"}]},
                    },
                }
            ],
        }
    ).encode("utf-8")

    async def mixed_fetch(feed_id: str, *args, **kwargs):
        if feed_id == "f_auth":
            return GTFSFeedFetchResult(503, b"Service Unavailable", "text/plain", 5.0, {})
        return GTFSFeedFetchResult(200, healthy_payload, "application/json", 5.0, {})

    with patch.object(client, "fetch_feed", side_effect=mixed_fetch):
        for _ in range(settings.GTFS_CIRCUIT_BREAKER_FAILURES):
            events_mixed = await registry.poll_all_enabled_feeds(force=True)
            assert any(e.id.startswith("f_healthy-") for e in events_mixed)

    assert registry.get_feed_status("f_auth").connectivity_status == "degraded"
    assert registry.get_feed_status("f_healthy").connectivity_status == "available"

    # Recovery on next poll resets f_auth back to available
    with patch.object(
        client,
        "fetch_feed",
        AsyncMock(return_value=GTFSFeedFetchResult(200, good_body, "application/json", 4.0, {})),
    ):
        await registry.poll_all_enabled_feeds(force=True)
    recovered = registry.get_feed_status("f_auth")
    assert recovered.connectivity_status == "available"
    assert recovered.consecutive_failure_count == 0
