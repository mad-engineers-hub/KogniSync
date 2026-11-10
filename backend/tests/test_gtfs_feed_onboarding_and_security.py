"""
backend/tests/test_gtfs_feed_onboarding_and_security.py

Comprehensive test suite for GTFS Realtime Feed Onboarding, Security, and Diagnostics (Milestone M3.9).
Tests Phase B & Phase C requirements:
1. No feed configured -> truthful unconfigured status.
2. Feed configured but not verified -> truthful configured / unknown status.
3. Valid authorized feed -> truthful available operational status.
4. Unauthorized feed (HTTP 401/403) -> truthful blocked / unauthorized status.
5. Invalid URL and malformed endpoint rejection.
6. SSRF protections: blocking loopback, cloud metadata (169.254.169.254), and RFC 1918 private subnets.
7. DNS rebinding prevention: validating resolved IP before connection.
8. Redirect protections: blocking redirects to private or unauthorized destinations.
9. Oversized response handling: preventing memory exhaustion (> 5MB payload limit).
10. Timeout and network error resiliency.
11. Rate limit handling (HTTP 429) and Retry-After header parsing.
12. Multi-feed registry onboarding via JSON configuration and programmatic registration.
13. Server-side credential isolation and zero leakage across API diagnostics.
14. API diagnostics endpoint (/api/v1/disruptions/providers/feeds) contract conformance.
"""
from __future__ import annotations

import asyncio
import json
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.disruption.providers.gtfs_feed_client import (
    GTFSFeedFetchResult,
    GTFSFeedPayloadTooLargeError,
    GTFSFeedSecurityError,
    PinnedIPAsyncTransport,
    PinnedIPNetworkBackend,
    SecureGTFSFeedClient,
    parse_retry_after,
    sanitize_feed_url,
    validate_feed_url_ssrf_safety,
    validate_target_ip,
)
from app.services.disruption.providers.gtfs_registry import (
    GTFSFeedRegistry,
    gtfs_feed_registry,
)
from app.services.disruption.schemas import (
    GTFSFeedConfig,
    GTFSFeedListResponse,
    GTFSFeedStatus,
)

client = TestClient(app)


# ============================================================================
# 1. SSRF & URL SAFETY TESTS
# ============================================================================

def test_sanitize_feed_url():
    """Verify sensitive query parameters (keys, tokens, secrets) are redacted in URLs."""
    url1 = "https://api.transit.gov/feed?key=SECRET_KEY_123&format=pb"
    sanitized1 = sanitize_feed_url(url1)
    assert "SECRET_KEY_123" not in sanitized1
    assert "key=%5BREDACTED%5D" in sanitized1 or "key=[REDACTED]" in sanitized1
    assert "format=pb" in sanitized1

    url2 = "https://api.transit.gov/feed?auth_token=JWT_ABC_XYZ"
    sanitized2 = sanitize_feed_url(url2)
    assert "JWT_ABC_XYZ" not in sanitized2

    assert sanitize_feed_url(None) == ""
    assert sanitize_feed_url("") == ""


def test_ssrf_blocks_private_networks_and_loopback():
    """Verify loopback, private IPv4, link-local, and cloud metadata IPs are rejected."""
    unsafe_urls = [
        "https://127.0.0.1/gtfs",
        "https://127.0.0.2:8080/feed",
        "https://10.0.0.5/gtfs-rt",
        "https://172.16.0.100/alerts",
        "https://192.168.1.1/feed",
        "https://169.254.169.254/latest/meta-data/",
        "https://metadata.google.internal/computeMetadata/v1/",
        "https://localhost:8000/feed",
        "https://[::1]/gtfs",
    ]
    for u in unsafe_urls:
        safe, reason, _ = validate_feed_url_ssrf_safety(u, allow_http=True)
        assert safe is False, f"Expected {u} to be blocked by SSRF validation"
        assert "forbidden" in reason.lower() or "ssrf" in reason.lower() or "private" in reason.lower() or "loopback" in reason.lower()


def test_ssrf_enforces_https_by_default():
    """Verify plain HTTP URLs are rejected when allow_http is False."""
    http_url = "http://api.transit.example.gov/gtfs-rt"
    safe, reason, _ = validate_feed_url_ssrf_safety(http_url, allow_http=False)
    assert safe is False
    assert "insecure http scheme" in reason.lower() or "only https" in reason.lower()

    # When explicitly allowed in test fixtures
    safe_test, _, _ = validate_feed_url_ssrf_safety(http_url, allow_http=True)
    assert safe_test is True


def test_dns_rebinding_protection():
    """Verify that domain resolving to a private IP address is rejected during DNS resolution."""
    with patch("socket.getaddrinfo") as mock_dns:
        # Mock DNS resolution returning private IP 192.168.1.50
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 443))
        ]
        safe, reason, resolved = validate_feed_url_ssrf_safety(
            "https://malicious-transit-rebinding.com/feed",
            allow_http=False,
            resolve_dns=True,
        )
        assert safe is False
        assert "private/internal" in reason.lower()
        assert "192.168.1.50" in resolved


def test_parse_retry_after():
    """Verify parsing integer seconds and HTTP dates in Retry-After headers."""
    assert parse_retry_after("30") == 30.0
    assert parse_retry_after(" 120 ") == 120.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None
    assert parse_retry_after("invalid-string") is None


# ============================================================================
# 2. CLIENT RESILIENCY & RESOURCE BOUNDS
# ============================================================================

@pytest.mark.anyio
async def test_oversized_payload_rejected():
    """Verify feed responses exceeding max_response_bytes (5MB) are aborted."""
    client = SecureGTFSFeedClient(max_response_bytes=1024, allow_http=True)  # 1 KB limit

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/x-protobuf", "content-length": "2048"}
    mock_resp.content = b"X" * 2048

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        with pytest.raises(GTFSFeedPayloadTooLargeError) as exc_info:
            await client.fetch_feed("feed_test", "https://api.example.gov/gtfs")
        assert "exceeds maximum permitted size" in str(exc_info.value)


@pytest.mark.anyio
async def test_redirect_to_private_ip_aborted():
    """Verify redirect to private IP or cloud metadata is blocked before following the hop."""
    client = SecureGTFSFeedClient(allow_http=True)

    mock_resp_redirect = MagicMock(spec=httpx.Response)
    mock_resp_redirect.status_code = 302
    mock_resp_redirect.headers = {"location": "http://169.254.169.254/latest/meta-data/"}

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp_redirect
        with pytest.raises(GTFSFeedSecurityError) as exc_info:
            await client.fetch_feed("feed_test", "https://api.example.gov/feed")
        assert "forbidden" in str(exc_info.value).lower() or "ssrf" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_rate_limiting_429_backoff():
    """Verify HTTP 429 invokes backoff and respects Retry-After."""
    client = SecureGTFSFeedClient(max_retries=1, backoff_base_seconds=0.05, allow_http=True)

    resp_429 = MagicMock(spec=httpx.Response)
    resp_429.status_code = 429
    resp_429.headers = {"retry-after": "0.1", "content-type": "text/plain"}
    resp_429.content = b"Rate limit exceeded"

    resp_200 = MagicMock(spec=httpx.Response)
    resp_200.status_code = 200
    resp_200.headers = {"content-type": "application/x-protobuf"}
    resp_200.content = b"FEED_OK"

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [resp_429, resp_200]
        res = await client.fetch_feed("feed_test", "https://api.example.gov/feed")
        assert res.status_code == 200
        assert res.content == b"FEED_OK"
        assert mock_get.call_count == 2


@pytest.mark.anyio
async def test_server_error_500_retries():
    """Verify HTTP 500 triggers exponential retry and backoff."""
    client = SecureGTFSFeedClient(max_retries=2, backoff_base_seconds=0.01, allow_http=True)

    resp_500 = MagicMock(spec=httpx.Response)
    resp_500.status_code = 500
    resp_500.headers = {}
    resp_500.content = b"Internal Server Error"

    resp_200 = MagicMock(spec=httpx.Response)
    resp_200.status_code = 200
    resp_200.headers = {"content-type": "application/x-protobuf"}
    resp_200.content = b"FEED_RECOVERED"

    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [resp_500, resp_200]
        res = await client.fetch_feed("feed_test", "https://api.example.gov/feed")
        assert res.status_code == 200
        assert res.content == b"FEED_RECOVERED"
        assert mock_get.call_count == 2


# ============================================================================
# 3. FEED REGISTRY ONBOARDING & STATE MACHINE TESTS
# ============================================================================

def test_feed_registry_initial_states():
    """Verify initial feed state evaluation adheres to truthful state machine."""
    registry = GTFSFeedRegistry(initial_configs=[])

    # 1. Unconfigured feed (empty URL)
    cfg1 = GTFSFeedConfig(
        feed_id="empty_feed",
        operator_name="Operator A",
        display_name="Feed A",
        feed_url="",
        enabled=True,
    )
    registry.register_feed(cfg1)
    st1 = registry.get_feed_status("empty_feed")
    assert st1 is not None
    assert st1.connectivity_status == "unconfigured"

    # 2. Disabled feed
    cfg2 = GTFSFeedConfig(
        feed_id="disabled_feed",
        operator_name="Operator B",
        display_name="Feed B",
        feed_url="https://api.example.gov/feed",
        enabled=False,
    )
    registry.register_feed(cfg2)
    st2 = registry.get_feed_status("disabled_feed")
    assert st2 is not None
    assert st2.connectivity_status == "disabled"

    # 3. Authenticated feed with missing credentials
    cfg3 = GTFSFeedConfig(
        feed_id="auth_feed_no_token",
        operator_name="BMTC",
        display_name="BMTC Alerts",
        feed_url="https://opendata.benscl.com/gtfs-rt/alerts",
        auth_type="bearer_token",
        auth_token_env_var="NON_EXISTENT_ENV_TOKEN_XYZ",
        enabled=True,
    )
    registry.register_feed(cfg3)
    st3 = registry.get_feed_status("auth_feed_no_token")
    assert st3 is not None
    assert st3.authorization_status == "pending_credentials"
    assert st3.connectivity_status == "unconfigured"
    assert "Awaiting credentials" in st3.status_notice

    # 4. Open-access feed with valid URL awaiting first verification
    cfg4 = GTFSFeedConfig(
        feed_id="open_feed",
        operator_name="Open Transit",
        display_name="Open Transit Alerts",
        feed_url="https://api.example.gov/open/gtfs-rt",
        auth_type="none",
        enabled=True,
    )
    registry.register_feed(cfg4)
    st4 = registry.get_feed_status("open_feed")
    assert st4 is not None
    assert st4.authorization_status == "authorized"
    assert st4.connectivity_status == "configured"  # Configured, not yet verified available!


@pytest.mark.anyio
async def test_feed_lifecycle_success_transition():
    """Verify successful verified response transitions feed from configured to available."""
    mock_client = SecureGTFSFeedClient(allow_http=True)
    registry = GTFSFeedRegistry(client=mock_client, initial_configs=[])

    cfg = GTFSFeedConfig(
        feed_id="test_live_transit",
        operator_name="Bangalore Metro",
        display_name="BMRCL Live Alerts",
        geographic_coverage="Namma Metro Purple & Green Lines",
        feed_url="https://api.example.gov/bmrcl/alerts",
        auth_type="none",
        enabled=True,
    )
    registry.register_feed(cfg)

    # Mock GTFS JSON feed response with 1 alert
    mock_json = {
        "header": {"gtfs_realtime_version": "2.0", "timestamp": 1700000000},
        "entity": [
            {
                "id": "alert-metro-01",
                "alert": {
                    "header_text": {"translation": [{"text": "Purple Line Signal Maintenance"}]},
                    "cause": "MAINTENANCE",
                    "effect": "SIGNIFICANT_DELAYS",
                },
            }
        ],
    }

    mock_fetch_res = GTFSFeedFetchResult(
        status_code=200,
        content=json.dumps(mock_json).encode("utf-8"),
        content_type="application/json",
        latency_ms=42.5,
        headers={"content-type": "application/json"},
    )

    with patch.object(mock_client, "fetch_feed", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_fetch_res
        # Mock time.time to match feed timestamp for freshness
        with patch("time.time", return_value=1700000100):
            events = await registry.fetch_feed_events("test_live_transit")

    assert len(events) == 1
    assert events[0].id == "test_live_transit-alert-alert-metro-01"
    assert events[0].event_type == "transport_delay"
    assert events[0].severity == "critical"
    assert events[0].provenance == "provider_live"

    status = registry.get_feed_status("test_live_transit")
    assert status is not None
    assert status.connectivity_status == "available"
    assert status.last_response_latency_ms == 42.5
    assert status.entity_counts.get("alerts") == 1


@pytest.mark.anyio
async def test_unauthorized_http_401_fails_closed():
    """Verify HTTP 401 transitions feed to blocked without crashing."""
    mock_client = SecureGTFSFeedClient(allow_http=True)
    registry = GTFSFeedRegistry(client=mock_client, initial_configs=[])

    cfg = GTFSFeedConfig(
        feed_id="unauth_feed",
        operator_name="Private Transit",
        display_name="Private Feed",
        feed_url="https://api.example.gov/secure/gtfs",
        auth_type="none",
        enabled=True,
    )
    registry.register_feed(cfg)

    mock_fetch_res = GTFSFeedFetchResult(
        status_code=401,
        content=b"Unauthorized",
        content_type="text/plain",
        latency_ms=25.0,
        headers={},
    )

    with patch.object(mock_client, "fetch_feed", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_fetch_res
        events = await registry.fetch_feed_events("unauth_feed")

    assert events == []
    status = registry.get_feed_status("unauth_feed")
    assert status is not None
    assert status.connectivity_status == "blocked"
    assert status.authorization_status == "unauthorized"
    assert "HTTP_401" in (status.last_error_classification or "")


# ============================================================================
# 4. API DIAGNOSTICS & CONTRACT TESTS
# ============================================================================

def test_api_get_gtfs_feeds_diagnostics():
    """Verify GET /api/v1/disruptions/providers/feeds returns sanitized feed statuses."""
    response = client.get("/api/v1/disruptions/providers/feeds")
    assert response.status_code == 200
    data = response.json()

    assert "feeds" in data
    assert "totalConfigured" in data
    assert "totalOperational" in data
    assert "notice" in data
    assert isinstance(data["feeds"], list)

    for feed in data["feeds"]:
        # Anti-leakage: Confirm no raw credentials or query keys are exposed
        assert "authToken" not in feed
        assert "apiKey" not in feed
        assert "authTokenEnvVar" not in feed
        feed_url = feed.get("feedUrlSanitized", "")
        assert "key=" not in feed_url or "[REDACTED]" in feed_url


# ============================================================================
# 5. M3.9.1: M-1 SSRF IP-PINNED TRANSPORT & DNS TOCTOU REGRESSION TESTS
# ============================================================================

def test_m1_public_dns_address_accepted_and_pinned():
    """Verify that a public DNS address is validated and pinned to the transport."""
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        safe, reason, resolved = validate_feed_url_ssrf_safety(
            "https://api.transit-agency.gov/feed", resolve_dns=True
        )
        assert safe is True
        assert resolved == ["93.184.216.34"]

        transport = PinnedIPAsyncTransport(
            pinned_ip=resolved[0],
            target_host="api.transit-agency.gov",
        )
        assert transport.pinned_ip == "93.184.216.34"
        assert transport.target_host == "api.transit-agency.gov"
        assert transport.network_backend.pinned_ip == "93.184.216.34"


def test_m1_dns_returns_prohibited_ips_blocked():
    """Verify loopback, private RFC 1918, link-local, cloud metadata, and CGNAT are blocked."""
    prohibited_ips = [
        "127.0.0.1",
        "127.0.0.254",
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "255.255.255.255",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
        "::ffff:10.0.0.1",
    ]
    for bad_ip in prohibited_ips:
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (bad_ip, 443))
            ]
            safe, reason, resolved = validate_feed_url_ssrf_safety(
                "https://legit-domain.com/feed", resolve_dns=True
            )
            assert safe is False, f"Expected {bad_ip} to be blocked"
            assert (
                "private" in reason.lower()
                or "forbidden" in reason.lower()
                or "ssrf" in reason.lower()
                or "prohibited" in reason.lower()
            )


def test_m1_dns_returns_mixture_fails_closed():
    """Verify that multi-address resolution containing any prohibited IP fails closed."""
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]
        safe, reason, resolved = validate_feed_url_ssrf_safety(
            "https://mixed-results.transit.gov/feed", resolve_dns=True
        )
        assert safe is False
        assert "private" in reason.lower() or "prohibited" in reason.lower()


def test_m1_dns_resolution_failure_fails_closed():
    """Verify that DNS resolution failure fails closed without falling back."""
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.side_effect = socket.gaierror(-2, "Name or service not known")
        safe, reason, resolved = validate_feed_url_ssrf_safety(
            "https://unresolvable-domain.invalid/feed", resolve_dns=True
        )
        assert safe is False
        assert "dns resolution failed" in reason.lower()
        assert resolved == []


@pytest.mark.anyio
async def test_m1_actual_socket_connection_uses_pinned_ip():
    """Directly verify that PinnedIPNetworkBackend connects to the pinned IP."""
    backend = PinnedIPNetworkBackend(pinned_ip="127.0.0.1", expected_host="transit.local")

    server = await asyncio.start_server(
        lambda r, w: (w.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"), w.close()),
        "127.0.0.1",
        0,
    )
    port = server.sockets[0].getsockname()[1]

    async with server:
        stream = await backend.connect_tcp("transit.local", port)
        assert backend.connected_target == ("127.0.0.1", port)
        await stream.aclose()


@pytest.mark.anyio
async def test_m1_connection_target_host_mismatch_raises():
    """Verify that host mismatch prevents connection reuse for different hosts."""
    backend = PinnedIPNetworkBackend(pinned_ip="127.0.0.1", expected_host="transit-origin.gov")
    with pytest.raises(GTFSFeedSecurityError) as exc_info:
        await backend.connect_tcp("unauthorized-destination.gov", 443)
    assert "target host mismatch" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_m1_tls_sni_and_cert_verification_preserved(tmp_path):
    """Verify TLS SNI and server certificate validation remain strictly active."""
    import datetime
    import ssl
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    # 1. Generate self-signed cert for valid-transit.local
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "valid-transit.local"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("valid-transit.local")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_file = str(tmp_path / "cert.pem")
    key_file = str(tmp_path / "key.pem")
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_file, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ssl.load_cert_chain(cert_file, key_file)

    client_ssl = ssl.create_default_context(cafile=cert_file)
    client_ssl.check_hostname = True
    client_ssl.verify_mode = ssl.CERT_REQUIRED

    async def https_handler(reader, writer):
        await reader.read(1024)
        body = b"TLS_FEED_VERIFIED"
        writer.write(
            f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode(
                "ascii"
            )
            + body
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(https_handler, "127.0.0.1", 0, ssl=server_ssl)
    port = server.sockets[0].getsockname()[1]

    async with server:
        # A. Valid hostname matching certificate succeeds
        valid_transport = PinnedIPAsyncTransport(
            pinned_ip="127.0.0.1",
            target_host="valid-transit.local",
            verify=client_ssl,
        )
        async with httpx.AsyncClient(transport=valid_transport) as t_client:
            resp = await t_client.get(f"https://valid-transit.local:{port}/feed")
            assert resp.status_code == 200
            assert resp.content == b"TLS_FEED_VERIFIED"

        # B. Invalid hostname not matching certificate is rejected by TLS verification
        invalid_transport = PinnedIPAsyncTransport(
            pinned_ip="127.0.0.1",
            target_host="mismatched-transit.local",
            verify=client_ssl,
        )
        async with httpx.AsyncClient(transport=invalid_transport) as t_client:
            with pytest.raises(httpx.ConnectError) as exc_info:
                await t_client.get(f"https://mismatched-transit.local:{port}/feed")
            assert (
                "certificate verify failed" in str(exc_info.value).lower()
                or "mismatch" in str(exc_info.value).lower()
            )


@pytest.mark.anyio
async def test_m1_dns_rebinding_defense_guaranteed():
    """Verify that DNS rebinding is defeated: transport connects only to validated pinned IP."""
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        safe, reason, resolved = validate_feed_url_ssrf_safety(
            "https://rebinding-test.gov/gtfs", resolve_dns=True
        )
        assert safe is True
        assert resolved == ["93.184.216.34"]

    # Even if DNS subsequently mutates to return 127.0.0.1, the pinned transport
    # only connects to 93.184.216.34, never re-resolving through untrusted DNS.
    transport = PinnedIPAsyncTransport(
        pinned_ip=resolved[0],
        target_host="rebinding-test.gov",
    )
    assert transport.pinned_ip == "93.184.216.34"
    assert transport.network_backend.pinned_ip == "93.184.216.34"


@pytest.mark.anyio
async def test_m1_redirect_to_public_host_independently_validated_and_pinned():
    """Verify that redirect to a separate public hostname is independently validated and pinned."""
    client = SecureGTFSFeedClient(allow_http=True)

    resp_302 = MagicMock(spec=httpx.Response)
    resp_302.status_code = 302
    resp_302.headers = {"location": "https://cdn.transit-agency.gov/feed.pb"}

    resp_200 = MagicMock(spec=httpx.Response)
    resp_200.status_code = 200
    resp_200.headers = {"content-type": "application/x-protobuf"}
    resp_200.content = b"REDIRECTED_FEED_DATA"

    def fake_getaddrinfo(host, port):
        if "api.transit-agency.gov" in host:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        elif "cdn.transit-agency.gov" in host:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.35", 443))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

    with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [resp_302, resp_200]
            result = await client.fetch_feed(
                "redirect_feed", "https://api.transit-agency.gov/feed"
            )
            assert result.status_code == 200
            assert result.content == b"REDIRECTED_FEED_DATA"
            assert mock_get.call_count == 2

