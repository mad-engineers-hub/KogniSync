"""
Regression & Security Verification Suite for Milestone M4.0.2:
- HIGH-02: Zero hardcoded JWT fallback secret; fail-closed across all environments
- MED-01: Complete exception & config diagnostic sanitization
- MED-02 & LOW-01: Unbypassable log redaction (post-init handlers, httpcore.http2, expanded syntax, zero false positives)
- MED-03: Full GTFS EntitySelector / TripDescriptor extraction, compound constraints & namespace isolation
- MED-04: Bounded PollRateLimiter, inactive expiry, shared Redis Lua coordination & fail-safe fallback
- LOW-02: End-to-end SecureGTFSFeedClient.fetch_feed() mixed public/private DNS SSRF fail-closed checks
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import io
import json
import logging
from pathlib import Path
import secrets
import socket
import time
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx
import jwt
import pytest

from app.api.routes.disruptions import PollRateLimiter, poll_rate_limiter
from app.core.config import settings
from app.core.logging import (
    SensitiveDataRedactionFilter,
    harden_http_client_logging,
    sanitize_sensitive_log_text,
    setup_logging,
)
from app.core.security import create_access_token, decode_access_token, get_jwt_secret
from app.main import app
from app.services.disruption.matcher import RouteDisruptionMatcher
from app.services.disruption.providers.gtfs_feed_client import (
    GTFSFeedFetchResult,
    GTFSFeedSecurityError,
    PinnedIPNetworkBackend,
    SecureGTFSFeedClient,
)
from app.services.disruption.providers.gtfs_protobuf import encode_gtfs_feed
from app.services.disruption.providers.gtfs_realtime import GTFSRealtimeProvider
from app.services.disruption.providers.gtfs_registry import GTFSFeedConfig, GTFSFeedRegistry
from app.services.disruption.providers.tomtom_orbis import TomTomOrbisTrafficProvider
from app.services.disruption.schemas import DisruptionEvent
from app.services.disruption.service import disruption_service
from app.services.journey.schemas import (
    AIExplanationSchema,
    CoordinatesSchema,
    JourneySchema,
    JourneySegmentSchema,
    LocationSchema,
)


def _make_segment(
    *,
    segment_id: str = "seg-1",
    mode: str = "bus",
    provider: str = "BMTC",
    vehicle_number: str | None = "500-D",
    vehicle_name: str | None = "BMTC Route 500-D",
    origin_id: str = "STOP-MAJ",
    origin_name: str = "Majestic",
    dest_id: str = "SILK-STOP-01",
    dest_name: str = "Silk Board",
    trip_id: str | None = None,
    route_id: str | None = None,
    agency_id: str | None = None,
    route_type: int | None = None,
    direction_id: int | None = None,
    orig_lat: float = 12.977,
    orig_lng: float = 77.571,
    dest_lat: float = 12.917,
    dest_lng: float = 77.623,
) -> JourneySegmentSchema:
    now = datetime.now(timezone.utc)
    return JourneySegmentSchema(
        segment_id=segment_id,
        sequence=1,
        mode=mode,  # type: ignore[arg-type]
        provider=provider,
        vehicle_name=vehicle_name,
        vehicle_number=vehicle_number,
        trip_id=trip_id,
        route_id=route_id,
        agency_id=agency_id,
        route_type=route_type,
        direction_id=direction_id,
        origin=LocationSchema(
            id=origin_id,
            name=origin_name,
            city="Bengaluru",
            type="bus_terminal",
            coordinates=CoordinatesSchema(lat=orig_lat, lng=orig_lng),
        ),
        destination=LocationSchema(
            id=dest_id,
            name=dest_name,
            city="Bengaluru",
            type="bus_terminal",
            coordinates=CoordinatesSchema(lat=dest_lat, lng=dest_lng),
        ),
        departure_time=now.isoformat(),
        arrival_time=(now + timedelta(minutes=30)).isoformat(),
        duration_minutes=30,
        price=25.0,
        distance_km=10.0,
        carbon_kg=1.0,
        comfort_score=7.5,
    )


def _legacy_fallback_material() -> str:
    # Constructed dynamically only inside this negative regression test to assert
    # tokens signed with the removed legacy fallback secret are rejected.
    return "".join(["kognisync_insecure_", "development_jwt_secret_key_", "384729"])


# ============================================================================
# HIGH-02: Remove Hardcoded JWT Fallback Secret & Fail Closed Uniformly
# ============================================================================


def test_high02_security_module_has_no_hardcoded_secret_and_fails_closed_all_envs(monkeypatch):
    security_path = Path(__file__).resolve().parents[1] / "app" / "core" / "security.py"
    source_text = security_path.read_text(encoding="utf-8")
    assert _legacy_fallback_material() not in source_text

    client = TestClient(app)
    forged_legacy_jwt = jwt.encode(
        {
            "sub": "attacker-admin",
            "role": "admin",
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=15)).timestamp()),
        },
        _legacy_fallback_material(),
        algorithm="HS256",
    )

    for env_name in ("development", "staging", "testing", "production"):
        monkeypatch.setattr(settings, "ENVIRONMENT", env_name)

        # 1. Missing JWT_SECRET_KEY fails closed across EVERY environment
        monkeypatch.setattr(settings, "JWT_SECRET_KEY", None)
        with pytest.raises(HTTPException) as exc_missing:
            get_jwt_secret()
        assert exc_missing.value.status_code == 500

        with pytest.raises(HTTPException) as exc_dec_missing:
            decode_access_token(forged_legacy_jwt)
        assert exc_dec_missing.value.status_code == 500

        res_poll_missing = client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=true",
            headers={"Authorization": f"Bearer {forged_legacy_jwt}"},
        )
        assert res_poll_missing.status_code in (401, 403, 500)
        assert res_poll_missing.status_code != 200

        # 2. Short (< 32 chars) JWT_SECRET_KEY fails closed across EVERY environment
        monkeypatch.setattr(settings, "JWT_SECRET_KEY", "short_dev_secret_only_28char")
        with pytest.raises(HTTPException) as exc_short:
            get_jwt_secret()
        assert exc_short.value.status_code == 500

        # 3. Legacy fallback secret is explicitly prohibited even if configured
        monkeypatch.setattr(settings, "JWT_SECRET_KEY", _legacy_fallback_material())
        with pytest.raises(HTTPException) as exc_legacy:
            get_jwt_secret()
        assert exc_legacy.value.status_code == 500

        res_poll_legacy = client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=true",
            headers={"Authorization": f"Bearer {forged_legacy_jwt}"},
        )
        assert res_poll_legacy.status_code in (401, 403, 500)
        assert res_poll_legacy.status_code != 200

    # 4. Random strong test secret (>= 32 chars) rejects forged JWT (401) and accepts valid JWT (200)
    strong_secret = secrets.token_urlsafe(40)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", strong_secret)
    poll_rate_limiter.reset()

    res_forged = client.post(
        "/api/v1/disruptions/providers/feeds/poll?force=true",
        headers={"Authorization": f"Bearer {forged_legacy_jwt}"},
    )
    assert res_forged.status_code == 401

    valid_admin_jwt = create_access_token("usr_m402_admin", extra_claims={"role": "admin"})
    valid_operator_jwt = create_access_token("usr_m402_operator", extra_claims={"role": "operator"})
    res_expired = client.post(
        "/api/v1/disruptions/providers/feeds/poll",
        headers={
            "Authorization": f"Bearer {create_access_token('usr_exp', expires_delta=timedelta(seconds=-10), extra_claims={'role': 'admin'})}"
        },
    )
    assert res_expired.status_code == 401

    # 5. Non-elevated operator role is denied force=true (403) but allowed normal force=false (200)
    with patch(
        "app.api.routes.disruptions.gtfs_feed_registry.poll_all_enabled_feeds",
        new=AsyncMock(return_value=[]),
    ):
        res_op_force = client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=true",
            headers={"Authorization": f"Bearer {valid_operator_jwt}"},
        )
        assert res_op_force.status_code == 403

        res_op_normal = client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=false",
            headers={"Authorization": f"Bearer {valid_operator_jwt}"},
        )
        assert res_op_normal.status_code == 200

        # Admin role is allowed force=true
        res_valid = client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=true",
            headers={"Authorization": f"Bearer {valid_admin_jwt}"},
        )
        assert res_valid.status_code == 200

    # 6. Operational X-Internal-Key authentication and elevated key requirement
    internal_key = secrets.token_hex(20)
    elevated_key = secrets.token_hex(20)
    monkeypatch.setattr(settings, "INTERNAL_API_KEY", internal_key)
    monkeypatch.setattr(settings, "TRANSIT_POLL_ELEVATED_KEY", elevated_key)

    with patch(
        "app.api.routes.disruptions.gtfs_feed_registry.poll_all_enabled_feeds",
        new=AsyncMock(return_value=[]),
    ):
        # Missing or bad key -> 401 or 403
        assert client.post("/api/v1/disruptions/providers/feeds/poll").status_code == 401
        assert (
            client.post(
                "/api/v1/disruptions/providers/feeds/poll",
                headers={"X-Internal-Key": "wrong-key"},
            ).status_code
            == 403
        )

        # Valid internal key without elevated key: force=true denied (403), normal allowed (200)
        res_int_force_denied = client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=true",
            headers={"X-Internal-Key": internal_key},
        )
        assert res_int_force_denied.status_code == 403

        res_int_normal = client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=false",
            headers={"X-Internal-Key": internal_key},
        )
        assert res_int_normal.status_code == 200

        # Valid internal key WITH elevated key: force=true allowed (200)
        poll_rate_limiter.reset()
        res_int_elevated = client.post(
            "/api/v1/disruptions/providers/feeds/poll?force=true",
            headers={"X-Internal-Key": internal_key, "X-Elevated-Key": elevated_key},
        )
        assert res_int_elevated.status_code == 200


# ============================================================================
# MED-01: GTFS & Provider Exception / Config Diagnostic Sanitization
# ============================================================================


@pytest.mark.anyio
async def test_med01_gtfs_parse_security_and_config_exceptions_sanitized(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    provider = GTFSRealtimeProvider(
        feed_url="https://api.example.gov/alerts?subscription-key=PROV_SUB_SECRET_777",
        allow_http=True,
    )

    # 1. Corrupt JSON echoing credentials must not leak into warnings or raised ValueError
    bad_json = (
        b"{bad json from https://JSON_USER:JSON_PASS_888@feed.example.gov/pb?api_key=JSON_KEY_999"
    )
    with pytest.raises(ValueError) as exc_json:
        provider.decode_and_parse_feed(bad_json, content_type="application/json", raise_on_error=True)
    assert "JSON_PASS_888" not in str(exc_json.value)
    assert "JSON_KEY_999" not in str(exc_json.value)

    # 1b. Mocked parser exception echoing raw credentials in str(err) is properly redacted
    with patch(
        "app.services.disruption.providers.gtfs_realtime.json.loads",
        side_effect=ValueError("Token decode error at https://JSON_USER:JSON_PASS_888@feed.example.gov/pb?api_key=JSON_KEY_999"),
    ):
        with pytest.raises(ValueError) as exc_mocked:
            provider.decode_and_parse_feed(b'{"dummy": 1}', content_type="application/json", raise_on_error=True)
        assert "JSON_PASS_888" not in str(exc_mocked.value)
        assert "JSON_KEY_999" not in str(exc_mocked.value)
        assert "[REDACTED]" in str(exc_mocked.value)

    # 2. Fetch failure with parse_err / security_err must sanitize _last_status_reason
    sec_msg = "Blocked URL https://SEC_PASS_111@internal.corp/gtfs?token=SEC_TOK_222"
    monkeypatch.setattr(settings, "GTFS_REALTIME_ENABLED", True)
    with patch.object(provider, "is_available", return_value=True), patch.object(
        provider._direct_client,
        "fetch_feed",
        AsyncMock(side_effect=GTFSFeedSecurityError(sec_msg)),
    ):
        events = await provider.fetch_disruptions()
    assert events == []
    assert "SEC_PASS_111" not in provider._last_status_reason
    assert "SEC_TOK_222" not in provider._last_status_reason
    assert "[REDACTED]" in provider._last_status_reason

    # 3. Malformed entity inside parse_gtfs_payload sanitizes entity.get('id') and error details
    bad_entity_payload = {
        "header": {"timestamp": int(datetime.now(timezone.utc).timestamp())},
        "entity": [
            {
                "id": "ent-https://ENT_USER_333@bad.host?key=ENT_KEY_444",
                "alert": {
                    "active_period": [{"start": "not_an_int Bearer ENT_BEAR_555"}],
                },
            }
        ],
    }
    parsed_bad = provider.parse_gtfs_payload(bad_entity_payload)
    assert parsed_bad == []

    # 4. Registry config JSON parse failure sanitizes any embedded credential syntax
    monkeypatch.setattr(
        settings,
        "GTFS_FEEDS_CONFIG_JSON",
        '[{"feed_url":"https://CFG_SECRET_666@bad.gov/x?token=CFG_TOK_777" broken',
    )
    monkeypatch.setattr(settings, "GTFS_REALTIME_FEED_URL", None)
    GTFSFeedRegistry()

    # 4b. Config validation exception containing credentials is also sanitized
    monkeypatch.setattr(
        settings,
        "GTFS_FEEDS_CONFIG_JSON",
        '[{"feed_url":"https://CFG_SECRET_666@bad.gov/x?token=CFG_TOK_777"}]',
    )
    GTFSFeedRegistry()

    # 5. Registry SSRF security error sanitizes status_notice and live_blocker_reason
    client = SecureGTFSFeedClient(allow_http=True)
    reg = GTFSFeedRegistry(
        client=client,
        initial_configs=[
            GTFSFeedConfig(
                feed_id="sec_leak_check",
                operator_name="TestOp",
                display_name="Sec Leak Check",
                feed_url="https://api.example.gov/gtfs?subscription-key=REG_SUB_SECRET_000",
                auth_type="none",
                enabled=True,
            )
        ],
    )
    with patch.object(
        client,
        "fetch_feed",
        AsyncMock(
            side_effect=GTFSFeedSecurityError(
                "Blocked redirect https://REG_USER_PASS@10.0.0.1/pb?api-key=REG_KEY_123"
            )
        ),
    ):
        await reg.fetch_feed_events("sec_leak_check")
    st = reg.get_feed_status("sec_leak_check")
    assert st is not None
    assert "REG_USER_PASS" not in st.status_notice
    assert "REG_KEY_123" not in st.status_notice
    assert "REG_USER_PASS" not in (st.live_blocker_reason or "")
    assert "REG_KEY_123" not in (st.live_blocker_reason or "")

    # 6. TomTom normalization exception log is sanitized
    tomtom = TomTomOrbisTrafficProvider()
    tomtom._normalize_response({"incidents": [{"properties": {}, "geometry": {"type": "Point", "coordinates": ["Bearer TOM_TOK_987", 77.0]}}]})

    all_logs = caplog.text
    for leaked in (
        "JSON_PASS_888",
        "JSON_KEY_999",
        "SEC_PASS_111",
        "SEC_TOK_222",
        "ENT_USER_333",
        "ENT_KEY_444",
        "ENT_BEAR_555",
        "CFG_SECRET_666",
        "CFG_TOK_777",
        "REG_USER_PASS",
        "REG_KEY_123",
        "TOM_TOK_987",
    ):
        assert leaked not in all_logs


# ============================================================================
# MED-02 & LOW-01: Unbypassable Log Redaction & Expanded Sanitizer Patterns
# ============================================================================


def test_low01_expanded_sanitizer_syntax_and_false_positive_safety():
    # Userinfo without colon + with colon
    assert "SECRET_ONLY" not in sanitize_sensitive_log_text("https://SECRET_ONLY@feed.gov/alerts.pb")
    assert "https://[REDACTED]@feed.gov/alerts.pb" in sanitize_sensitive_log_text(
        "https://SECRET_ONLY@feed.gov/alerts.pb"
    )
    assert "PASS_WITH_USER" not in sanitize_sensitive_log_text("http://usr:PASS_WITH_USER@feed.gov/pb")

    # Hyphenated query params + benign params preserved
    hyp = sanitize_sensitive_log_text(
        "GET https://api.gov/v1?subscription-key=SUB_999&api-key=AK_888&stop_id=KBS_01"
    )
    assert "SUB_999" not in hyp
    assert "AK_888" not in hyp
    assert "stop_id=KBS_01" in hyp

    # URL-encoded query credentials & URL-encoded userinfo
    enc = sanitize_sensitive_log_text(
        "proxy=https%3A%2F%2FENC_USER%40host.gov%2Ffeed%3Fapi_key%3DENC_SECRET_55%26route_id%3D500D"
    )
    assert "ENC_USER" not in enc
    assert "ENC_SECRET_55" not in enc
    assert "route_id%3D500D" in enc

    # JSON-quoted tokens & headers & Bearer/Basic + bytes tuples
    js = sanitize_sensitive_log_text(
        '{"token": "JSON_TOK_11", "x-api-key": "JSON_XAPI_22", "authorization": "Bearer JSON_BEAR_33"}'
    )
    assert "JSON_TOK_11" not in js
    assert "JSON_XAPI_22" not in js
    assert "JSON_BEAR_33" not in js

    hdr = sanitize_sensitive_log_text(
        "Authorization: Bearer HDR_BEAR_44; Authorization: Basic dXNlcjpzZWNyZXQ=; "
        "[(b'x-api-key', b'BYTES_KEY_55'), (b'authorization', b'Bearer BYTES_BEAR_66')]"
    )
    assert "HDR_BEAR_44" not in hdr
    assert "dXNlcjpzZWNyZXQ=" not in hdr
    assert "BYTES_KEY_55" not in hdr
    assert "BYTES_BEAR_66" not in hdr

    # Bare JWT redaction
    jwt_str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTYifQ.sig_value_here_999"
    assert "sig_value_here_999" not in sanitize_sensitive_log_text(f"token failed validation {jwt_str}")

    # False-positive protection on harmless English log prose
    harmless = (
        "Bearer token expired | Bearer token required | Basic routing fallback active | "
        "query?author=alice&monkey=2&stop_id=12"
    )
    assert sanitize_sensitive_log_text(harmless) == harmless

    # Redaction idempotency: repeated passes never corrupt or append extra brackets to already-redacted text
    multi_target = "https://USER_1:PASS_2@feed.gov/pb?api-key=AK_888&token=TOK_999"
    pass1 = sanitize_sensitive_log_text(multi_target)
    pass2 = sanitize_sensitive_log_text(pass1)
    pass3 = sanitize_sensitive_log_text(pass2)
    assert pass1 == pass2 == pass3
    assert "https://[REDACTED]@feed.gov/pb?api-key=[REDACTED]&token=[REDACTED]" in pass1
    assert "]]]]" not in pass3


def test_med02_unbypassable_redaction_post_init_handlers_and_httpcore_http2():
    setup_logging()
    harden_http_client_logging()
    harden_http_client_logging()

    # No duplicate filter instances on hardened loggers/handlers
    for name in ("httpx", "httpcore", "httpcore.http11", "httpcore.http2", "httpcore.connection", "kognisync", ""):
        lg = logging.getLogger(name)
        assert sum(isinstance(f, SensitiveDataRedactionFilter) for f in lg.filters) <= 1

    # Create brand-new logger & post-init handler AFTER setup_logging / harden_http_client_logging
    post_stream = io.StringIO()
    post_handler = logging.StreamHandler(post_stream)
    post_logger = logging.getLogger(f"kognisync.test.postinit.{secrets.token_hex(4)}")
    post_logger.setLevel(logging.DEBUG)
    post_logger.propagate = False
    post_logger.addHandler(post_handler)
    post_logger.addHandler(post_handler)  # Repeated call stays idempotent
    assert sum(isinstance(f, SensitiveDataRedactionFilter) for f in post_handler.filters) == 1

    post_logger.info(
        "Requesting https://POST_USER_PASS@feed.gov/pb?subscription-key=POST_SUB_KEY "
        'payload={"x-api-key": "POST_JSON_KEY"} header Authorization: Bearer POST_HDR_BEAR'
    )
    post_logger.info("Harmless message: Bearer token required; Bearer token expired")

    # Also verify exception traceback URL redaction
    try:
        raise RuntimeError("Upstream failed at https://EXC_SECRET@bad.gov/feed?api_key=EXC_KEY_777")
    except RuntimeError:
        post_logger.error("Transport crash", exc_info=True)

    # Also test httpcore.http2 post-init handler and debug level
    h2_stream = io.StringIO()
    h2_handler = logging.StreamHandler(h2_stream)
    h2_logger = logging.getLogger("httpcore.http2")
    orig_level = h2_logger.level
    try:
        assert h2_logger.level == logging.WARNING
        h2_logger.setLevel(logging.DEBUG)
        h2_logger.addHandler(h2_handler)
        h2_logger.debug("HTTP/2 debug stream https://H2_SECRET@feed.gov/stream?token=H2_TOK_888")
        h2_logger.warning("HTTP/2 stream error https://H2_SECRET@feed.gov/stream?token=H2_TOK_888")
    finally:
        h2_logger.removeHandler(h2_handler)
        h2_logger.setLevel(orig_level)
        post_logger.removeHandler(post_handler)

    rendered = post_stream.getvalue() + h2_stream.getvalue()
    for secret_val in (
        "POST_USER_PASS",
        "POST_SUB_KEY",
        "POST_JSON_KEY",
        "POST_HDR_BEAR",
        "EXC_SECRET",
        "EXC_KEY_777",
        "H2_SECRET",
        "H2_TOK_888",
    ):
        assert secret_val not in rendered
    assert "Bearer token required" in rendered
    assert "Bearer token expired" in rendered


# ============================================================================
# MED-03: Authoritative GTFS EntitySelector Correlation & Collision Isolation
# ============================================================================


def test_med03_raw_protobuf_informed_entity_correlation_and_isolation():
    now_ts = int(datetime.now(timezone.utc).timestamp())
    provider = GTFSRealtimeProvider(feed_url="https://api.example.gov/alerts.pb")

    # 1. Compound bus alert (agency_id + route_type=3 + route_id + direction_id=0)
    raw_bus_alert = encode_gtfs_feed(
        {
            "header": {"gtfs_realtime_version": "2.0", "timestamp": now_ts},
            "entity": [
                {
                    "id": "alert-bus-compound",
                    "alert": {
                        "informed_entity": [
                            {
                                "agency_id": "BMTC-AGY",
                                "route_type": 3,
                                "route_id": "500-D",
                                "direction_id": 0,
                            }
                        ],
                        "effect": 2,  # SIGNIFICANT_DELAYS
                        "header_text": {"translation": [{"text": "BMTC 500-D Outbound Delay"}]},
                    },
                },
                {
                    "id": "alert-trip-scoped",
                    "alert": {
                        "informed_entity": [
                            {
                                "agency_id": "BMRCL",
                                "route_type": 1,
                                "trip": {
                                    "trip_id": "TRIP-GREEN-888",
                                    "route_id": "METRO-GREEN",
                                    "direction_id": 1,
                                },
                            }
                        ],
                        "effect": 1,  # NO_SERVICE
                        "header_text": {"translation": [{"text": "Green Line Trip 888 Cancelled"}]},
                    },
                },
                {
                    "id": "alert-bare-direction",
                    "alert": {
                        "informed_entity": [{"direction_id": 0}],
                        "effect": 2,
                        "header_text": {"translation": [{"text": "Ambiguous Direction Only"}]},
                    },
                },
                {
                    "id": "alert-bare-routetype",
                    "alert": {
                        "informed_entity": [{"route_type": 3}],
                        "effect": 2,
                        "header_text": {"translation": [{"text": "Ambiguous Route Type Only"}]},
                    },
                },
                {
                    "id": "alert-agency-only",
                    "alert": {
                        "informed_entity": [{"agency_id": "NMMT", "route_type": 3}],
                        "effect": 2,
                        "header_text": {"translation": [{"text": "NMMT Bus Strike"}]},
                    },
                },
                {
                    "id": "alert-route-stop-compound",
                    "alert": {
                        "informed_entity": [{"route_id": "V-335E", "stop_id": "SILK-STOP-01"}],
                        "effect": 5,
                        "header_text": {"translation": [{"text": "V-335E Stop Bypass at Silk Board"}]},
                    },
                },
            ],
        }
    )

    events = provider.decode_and_parse_feed(raw_bus_alert, content_type="application/x-protobuf")
    ev_by_id = {e.source_id: e for e in events}

    # route_type derives affected_modes accurately
    assert ev_by_id["alert-bus-compound"].affected_modes == ["bus"]
    assert ev_by_id["alert-trip-scoped"].affected_modes == ["metro"]
    assert ev_by_id["alert-agency-only"].affected_modes == ["bus"]

    matcher = RouteDisruptionMatcher()

    # Exact bus match -> YES, propagates into JourneyImpactAssessor
    seg_bus_match = _make_segment(
        segment_id="seg-bus-ok",
        mode="bus",
        agency_id="BMTC-AGY",
        route_type=3,
        route_id="500-D",
        direction_id=0,
    )
    journey = JourneySchema(
        id="j-med03",
        title="Transit Test",
        origin=seg_bus_match.origin,
        destination=seg_bus_match.destination,
        departure_time=seg_bus_match.departure_time,
        arrival_time=seg_bus_match.arrival_time,
        total_duration_minutes=30,
        total_price=25.0,
        total_transfers=0,
        modes=["bus"],
        segments=[seg_bus_match],
        carbon_kg=1.0,
        comfort_score=7.5,
        ai_explanation=AIExplanationSchema(summary="Test journey"),
    )
    assessment = disruption_service.assessor.assess_journey(journey, [ev_by_id["alert-bus-compound"]])
    assert assessment.is_disrupted is True
    assert assessment.segment_impacts[0].match_type == "route_id_exact"

    # Opposite direction -> NO match
    seg_bus_opp_dir = _make_segment(
        mode="bus", agency_id="BMTC-AGY", route_type=3, route_id="500-D", direction_id=1
    )
    assert matcher.match_event_to_segment(ev_by_id["alert-bus-compound"], seg_bus_opp_dir) is None

    # Wrong agency on same route number -> NO match
    seg_bus_other_agy = _make_segment(
        mode="bus", agency_id="KSRTC", route_type=3, route_id="500-D", direction_id=0
    )
    assert matcher.match_event_to_segment(ev_by_id["alert-bus-compound"], seg_bus_other_agy) is None

    # Wrong mode on same route number -> NO match
    seg_metro_same_num = _make_segment(
        mode="metro", agency_id="BMTC-AGY", route_type=1, route_id="500-D", direction_id=0
    )
    assert matcher.match_event_to_segment(ev_by_id["alert-bus-compound"], seg_metro_same_num) is None

    # Trip-scoped alert -> matches exact trip_id (`trip_id_exact`), rejects sibling trip & wrong namespace
    seg_trip_ok = _make_segment(
        mode="metro",
        agency_id="BMRCL",
        route_type=1,
        trip_id="TRIP-GREEN-888",
        route_id="METRO-GREEN",
        direction_id=1,
    )
    trip_m = matcher.match_event_to_segment(ev_by_id["alert-trip-scoped"], seg_trip_ok)
    assert trip_m is not None
    assert trip_m.match_type == "trip_id_exact"

    seg_trip_other = _make_segment(
        mode="metro",
        agency_id="BMRCL",
        route_type=1,
        trip_id="TRIP-GREEN-999",
        route_id="METRO-GREEN",
        direction_id=1,
    )
    assert matcher.match_event_to_segment(ev_by_id["alert-trip-scoped"], seg_trip_other) is None

    # Namespace isolation: vehicle_number holding a trip_id must NOT match trip_id selector
    seg_wrong_ns = _make_segment(
        mode="metro", agency_id="BMRCL", vehicle_number="TRIP-GREEN-888", route_id=None, trip_id=None
    )
    assert matcher.match_event_to_segment(ev_by_id["alert-trip-scoped"], seg_wrong_ns) is None

    # Bare direction_id and bare route_type (without primary ID or geometry) NEVER falsely match
    assert matcher.match_event_to_segment(ev_by_id["alert-bare-direction"], seg_bus_match) is None
    assert matcher.match_event_to_segment(ev_by_id["alert-bare-routetype"], seg_bus_match) is None

    # Spatial fallback still works cleanly for bare route_type=3 event WHEN point exists (and excludes trains)
    spatial_bus_ev = DisruptionEvent(
        id="sp-bus-only",
        source="gtfs_realtime",
        event_type="traffic_congestion",
        severity="high",
        status="active",
        title="Bus corridor delay",
        description="Spatial point near Majestic",
        affected_modes=["bus"],
        point=CoordinatesSchema(lat=12.977, lng=77.571),
        radius_meters=1000.0,
        valid_from=datetime.now(timezone.utc).isoformat(),
        observed_at=datetime.now(timezone.utc).isoformat(),
        last_verified_at=datetime.now(timezone.utc).isoformat(),
        provenance="provider_live",
        correlation_metadata={"routeTypes": [3]},
    )
    assert matcher.match_event_to_segment(spatial_bus_ev, seg_bus_match) is not None
    seg_train_same_loc = _make_segment(mode="train", orig_lat=12.977, orig_lng=77.571)
    assert matcher.match_event_to_segment(spatial_bus_ev, seg_train_same_loc) is None

    # Agency-only alert matches exact agency_id, does not collide with route_id="NMMT"
    seg_agency_ok = _make_segment(mode="bus", agency_id="NMMT", route_type=3, route_id="BUS-1")
    ag_m = matcher.match_event_to_segment(ev_by_id["alert-agency-only"], seg_agency_ok)
    assert ag_m is not None
    assert ag_m.match_type == "agency_id_exact"

    seg_agency_ns_collision = _make_segment(
        mode="bus", agency_id="OTHER-OP", provider="OtherOp", route_type=3, route_id="NMMT"
    )
    assert matcher.match_event_to_segment(ev_by_id["alert-agency-only"], seg_agency_ns_collision) is None

    # Compound route_id + stop_id requires both when declared on one EntitySelector
    seg_rs_ok = _make_segment(mode="bus", route_id="V-335E", dest_id="SILK-STOP-01")
    seg_rs_wrong_stop = _make_segment(mode="bus", route_id="V-335E", dest_id="HEBBAL-STOP-99")
    assert matcher.match_event_to_segment(ev_by_id["alert-route-stop-compound"], seg_rs_ok) is not None
    assert matcher.match_event_to_segment(ev_by_id["alert-route-stop-compound"], seg_rs_wrong_stop) is None


@pytest.mark.anyio
async def test_med03_malformed_protobuf_recorded_as_failures_not_empty_success():
    corrupt_pb = b"\x08\x96\x01\x12\x04\xff\xff\xff\xff\xff"
    provider = GTFSRealtimeProvider(feed_url="https://api.example.gov/alerts.pb")

    # 1. GTFSRealtimeProvider decode_and_parse_feed raises ValueError on corrupt protobuf
    with pytest.raises(ValueError) as exc_pb:
        provider.decode_and_parse_feed(corrupt_pb, content_type="application/x-protobuf", raise_on_error=True)
    assert "corrupt" in str(exc_pb.value).lower() or "protobuf" in str(exc_pb.value).lower()

    # 2. Provider fetch records failure, incrementing consecutive_failure_count
    with patch.object(provider, "is_available", return_value=True), patch.object(
        provider._direct_client,
        "fetch_feed",
        AsyncMock(return_value=GTFSFeedFetchResult(200, corrupt_pb, "application/x-protobuf", 10.0, {})),
    ):
        events = await provider.fetch_disruptions()
    assert events == []
    assert provider._consecutive_failure_count == 1
    assert "Malformed feed payload" in (provider._last_status_reason or "")
    assert provider._last_successful_request is None

    # 3. GTFSFeedRegistry records decode_failures and PARSE_ERROR, not empty success
    reg = GTFSFeedRegistry(
        client=provider._direct_client,
        initial_configs=[
            GTFSFeedConfig(
                feed_id="corrupt_pb_feed",
                operator_name="TestOp",
                display_name="Corrupt PB Feed",
                feed_url="https://api.example.gov/alerts.pb",
                auth_type="none",
                enabled=True,
            )
        ],
    )
    with patch.object(
        reg.client,
        "fetch_feed",
        AsyncMock(return_value=GTFSFeedFetchResult(200, corrupt_pb, "application/x-protobuf", 10.0, {})),
    ):
        await reg.fetch_feed_events("corrupt_pb_feed")
    st = reg.get_feed_status("corrupt_pb_feed")
    assert st is not None
    assert st.decode_failures == 1
    assert st.last_error_classification == "PARSE_ERROR"
    assert st.accepted_event_count == 0
    assert st.connectivity_status != "available"


# ============================================================================
# MED-04: Bounded PollRateLimiter, Inactive Expiry, Shared Redis & Fallback
# ============================================================================


def test_med04_bounded_principals_expiry_and_force_rotation_resistance(monkeypatch):
    limiter = PollRateLimiter(use_redis=False)
    monkeypatch.setattr(settings, "TRANSIT_POLL_RATE_LIMIT_MAX_TRACKED_PRINCIPALS", 4)
    monkeypatch.setattr(settings, "TRANSIT_POLL_RATE_LIMIT_MAX_REQUESTS", 100)
    monkeypatch.setattr(settings, "TRANSIT_POLL_RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "TRANSIT_FORCE_POLL_MIN_INTERVAL_SECONDS", 10.0)

    clock = {"now": 1000.0}
    monkeypatch.setattr("app.api.routes.disruptions.time.monotonic", lambda: clock["now"])

    # Rotating 25 principals stays strictly bounded <= 4
    for i in range(25):
        clock["now"] += 0.1
        limiter.check_and_record(f"rotator-{i}", force=False)

    diag = limiter.get_diagnostics()
    assert diag["tracked_principals"] <= 4
    assert diag["evicted_principals"] >= 21

    # Global force-poll cooldown holds across principal rotation + LRU eviction
    limiter.check_and_record("admin-a", force=True)
    for j in range(10):
        clock["now"] += 0.1
        with pytest.raises(HTTPException) as exc_fc:
            limiter.check_and_record(f"admin-rotator-{j}", force=True)
        assert exc_fc.value.status_code == 429

    # Advance clock past window -> inactive buckets expire cleanly
    clock["now"] += 120.0
    limiter.check_and_record("fresh-caller", force=False)
    assert limiter.get_diagnostics()["tracked_principals"] == 1


class _FakeAtomicAsyncRedis:
    """Thread/async-safe deterministic Redis stub modeling Lua TIME/ZSET/SET PX semantics."""

    def __init__(self) -> None:
        self.zsets: dict[str, list[tuple[int, str]]] = {}
        self.kv: dict[str, tuple[str, int]] = {}
        self.seq = 0
        self.clock_ms = 1_700_000_000_000
        self.fail_with: Exception | None = None

    async def eval(self, script: str, numkeys: int, *args):
        if self.fail_with is not None:
            raise self.fail_with
        p_key, g_key, f_key, _s_key = args[:numkeys]
        win_ms, max_req, g_max, is_force, force_min_ms, ttl_ms = [int(x) for x in args[numkeys:]]
        now_ms = self.clock_ms

        if is_force == 1 and force_min_ms > 0 and f_key in self.kv:
            raw_val, exp_at = self.kv[f_key]
            if now_ms < exp_at:
                last_force = int(raw_val)
                elapsed = now_ms - last_force
                if elapsed < force_min_ms:
                    return [0, "force_cooldown", force_min_ms - elapsed]

        cutoff = now_ms - win_ms
        p_items = [item for item in self.zsets.get(p_key, []) if item[0] > cutoff]
        g_items = [item for item in self.zsets.get(g_key, []) if item[0] > cutoff]
        self.zsets[p_key] = p_items
        self.zsets[g_key] = g_items

        if len(p_items) >= max_req or len(g_items) >= g_max:
            oldest = p_items[0][0] if p_items else g_items[0][0]
            return [0, "rate_limit", max(1000, win_ms - (now_ms - oldest))]

        self.seq += 1
        member = f"{now_ms}:{self.seq}"
        p_items.append((now_ms, member))
        g_items.append((now_ms, member))
        if is_force == 1:
            self.kv[f_key] = (str(now_ms), now_ms + max(1000, force_min_ms + 5000))
        return [1, "ok", 0]


@pytest.mark.anyio
async def test_med04_shared_redis_multi_worker_concurrency_and_fallback(monkeypatch):
    fake_redis = _FakeAtomicAsyncRedis()
    worker_a = PollRateLimiter(redis_client=fake_redis, key_prefix="m402:test")
    worker_b = PollRateLimiter(redis_client=fake_redis, key_prefix="m402:test")

    monkeypatch.setattr(settings, "TRANSIT_POLL_RATE_LIMIT_MAX_REQUESTS", 3)
    monkeypatch.setattr(settings, "TRANSIT_POLL_RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "TRANSIT_FORCE_POLL_MIN_INTERVAL_SECONDS", 5.0)

    # Concurrent burst across two worker instances against shared Redis -> strictly 3 allowed, 7 rejected
    async def _try_worker(lim: PollRateLimiter) -> bool:
        try:
            await lim.acheck_and_record("shared-operator", force=False)
            return True
        except HTTPException as exc:
            assert exc.status_code == 429
            return False

    results = await asyncio.gather(
        *([_try_worker(worker_a) for _ in range(5)] + [_try_worker(worker_b) for _ in range(5)])
    )
    assert sum(1 for r in results if r) == 3
    assert worker_a.enforcement_mode == "shared_redis"
    assert worker_b.enforcement_mode == "shared_redis"

    # Cross-worker force-poll cooldown shared via Redis
    await worker_a.acheck_and_record("admin-a", force=True)
    with pytest.raises(HTTPException) as exc_wb:
        await worker_b.acheck_and_record("admin-b", force=True)
    assert exc_wb.value.status_code == 429

    # Fail-safe fallback when Redis becomes unavailable
    fake_redis.fail_with = ConnectionError("Redis connection lost")
    monkeypatch.setattr(settings, "TRANSIT_POLL_RATE_LIMIT_MAX_REQUESTS", 2)
    await worker_a.acheck_and_record("fallback-op", force=False)
    await worker_a.acheck_and_record("fallback-op", force=False)
    with pytest.raises(HTTPException) as exc_fb:
        await worker_a.acheck_and_record("fallback-op", force=False)
    assert exc_fb.value.status_code == 429
    assert worker_a.enforcement_mode == "process_local_fallback"
    assert worker_a.last_redis_error == "ConnectionError"


# ============================================================================
# LOW-02: Actual SecureGTFSFeedClient.fetch_feed() Mixed DNS SSRF Regression
# ============================================================================


@pytest.mark.anyio
async def test_low02_fetch_feed_mixed_public_and_private_dns_fails_closed():
    client = SecureGTFSFeedClient(allow_http=False, max_retries=0)
    mixed_gai = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.15", 443)),
    ]

    with (
        patch("socket.getaddrinfo", return_value=mixed_gai),
        patch.object(PinnedIPNetworkBackend, "connect_tcp", new_callable=AsyncMock) as mock_connect,
    ):
        with pytest.raises(GTFSFeedSecurityError) as exc_mixed:
            await client.fetch_feed(
                feed_id="low02_mixed_dns",
                feed_url="https://mixed-dns.example.gov/alerts.pb",
            )

    assert "non-public range" in str(exc_mixed.value).lower()
    assert "10.0.0.15" in str(exc_mixed.value)
    assert mock_connect.call_count == 0


@pytest.mark.anyio
async def test_low02_fetch_feed_redirect_hop2_mixed_dns_fails_closed():
    client = SecureGTFSFeedClient(allow_http=False, max_retries=0)

    def _dns_side_effect(host: str, *args, **kwargs):
        if host == "public-hop1.example.gov":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]

    class _FakeResp:
        status_code = 302
        headers = {"location": "https://mixed-hop2.example.net/feed.pb", "content-length": "0"}
        content = b""

    with (
        patch("socket.getaddrinfo", side_effect=_dns_side_effect),
        patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=_FakeResp()) as mock_get,
    ):
        with pytest.raises(GTFSFeedSecurityError) as exc_hop2:
            await client.fetch_feed(
                feed_id="low02_hop2_mixed",
                feed_url="https://public-hop1.example.gov/alerts.pb",
            )

    assert "non-public range" in str(exc_hop2.value).lower()
    assert "127.0.0.1" in str(exc_hop2.value)
    # Only Hop 1 executed HTTP GET; Hop 2 failed SSRF validation prior to transport request
    assert mock_get.call_count == 1


@pytest.mark.anyio
async def test_low02_fetch_feed_redirect_credential_stripping_and_hop_limit():
    client = SecureGTFSFeedClient(allow_http=False, max_retries=0)
    captured_requests = []

    class _FakeRedirectClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, headers=None):
            captured_requests.append({"url": url, "headers": dict(headers or {})})
            if len(captured_requests) == 1:
                return httpx.Response(
                    status_code=302,
                    headers={"location": "https://other-domain.example.org/alerts.pb"},
                )
            return httpx.Response(
                status_code=200,
                headers={"content-type": "application/x-protobuf"},
                content=b"",
            )

    def _dns_side_effect(host: str, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    # 1. Cross-origin redirect strips authorization header & query credential
    with (
        patch("socket.getaddrinfo", side_effect=_dns_side_effect),
        patch("httpx.AsyncClient", _FakeRedirectClient),
    ):
        await client.fetch_feed(
            feed_id="redir_strip_test",
            feed_url="https://initial.example.gov/alerts.pb",
            auth_header=("Authorization", "Bearer TOP_SECRET_BEARER"),
            auth_query_param=("key", "SECRET_QUERY_KEY"),
        )

    assert len(captured_requests) == 2
    assert "Authorization" in captured_requests[0]["headers"]
    assert "SECRET_QUERY_KEY" in captured_requests[0]["url"]
    assert "Authorization" not in captured_requests[1]["headers"]
    assert "SECRET_QUERY_KEY" not in captured_requests[1]["url"]

    # 2. Exceeding max redirect hops (4 consecutive 302s) raises GTFSFeedSecurityError
    class _InfiniteRedirectClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, headers=None):
            return httpx.Response(
                status_code=302,
                headers={"location": f"{url}/next"},
            )

    with (
        patch("socket.getaddrinfo", side_effect=_dns_side_effect),
        patch("httpx.AsyncClient", _InfiniteRedirectClient),
    ):
        with pytest.raises(GTFSFeedSecurityError) as exc_redir:
            await client.fetch_feed(
                feed_id="infinite_redir",
                feed_url="https://initial.example.gov/alerts.pb",
            )
        assert "too many redirect hops" in str(exc_redir.value).lower()


@pytest.mark.anyio
async def test_med04_live_redis_lua_multi_worker_enforcement(monkeypatch):
    """Verifies real Redis server-side Lua atomic sliding-window & force-cooldown across two worker instances."""
    import redis.asyncio as aioredis

    url = settings.REDIS_URL
    client = aioredis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5, decode_responses=True)
    try:
        await client.ping()
    except Exception as exc:
        await client.aclose()
        pytest.skip(f"Live Redis server unreachable on {url}: {type(exc).__name__}")

    prefix = f"kognisync:test_m402:{secrets.token_hex(4)}"
    w1 = PollRateLimiter(redis_url=url, key_prefix=prefix, use_redis=True)
    w2 = PollRateLimiter(redis_url=url, key_prefix=prefix, use_redis=True)
    monkeypatch.setattr(settings, "TRANSIT_POLL_RATE_LIMIT_MAX_REQUESTS", 2)
    monkeypatch.setattr(settings, "TRANSIT_POLL_RATE_LIMIT_WINDOW_SECONDS", 30)
    monkeypatch.setattr(settings, "TRANSIT_FORCE_POLL_MIN_INTERVAL_SECONDS", 5.0)
    try:
        await w1.areset()
        await w1.acheck_and_record("live-op", force=False)
        await w2.acheck_and_record("live-op", force=False)
        with pytest.raises(HTTPException) as exc_rl:
            await w1.acheck_and_record("live-op", force=False)
        assert exc_rl.value.status_code == 429
        assert w1.enforcement_mode == "shared_redis"
        assert w2.enforcement_mode == "shared_redis"

        await w1.acheck_and_record("live-admin-1", force=True)
        with pytest.raises(HTTPException) as exc_fc:
            await w2.acheck_and_record("live-admin-2", force=True)
        assert exc_fc.value.status_code == 429
    finally:
        await w1.areset()
        await client.aclose()
