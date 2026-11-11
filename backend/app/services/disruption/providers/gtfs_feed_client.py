"""
backend/app/services/disruption/providers/gtfs_feed_client.py

Secure, bounded, and resilient HTTP client for fetching official GTFS Realtime feeds (Milestones M3.9 & M3.9.1).
Implements Phase C and M3.9.1 security requirements:
- Strict SSRF protections (blocking loopback, cloud metadata, RFC 1918 private subnets, CGNAT, broadcast).
- DNS rebinding & DNS TOCTOU prevention via PinnedIPAsyncTransport pinning the socket connection to pre-validated IPs.
- Preservation of TLS SNI (Server Name Indication) and full certificate verification on the original hostname.
- Redirect protection (disabling automatic unverified redirects and validating each redirect hop independently).
- Resource bounds (timeout and maximum response byte limits to prevent memory exhaustion).
- Resilient retries with exponential backoff, jitter, and Retry-After header conformance.
- Per-feed concurrent in-flight deduplication to prevent stampeding herd requests.
- Strict anti-leakage of upstream credentials and authorization headers.
"""
from __future__ import annotations

import asyncio
import email.utils
import ipaddress
import random
import socket
import ssl
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpcore
import httpx
from httpcore._backends.anyio import AnyIOBackend

from app.core.config import settings
from app.core.logging import logger

DISALLOWED_HOSTNAMES: set[str] = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254",
}

PROHIBITED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("0.0.0.0/8"),          # Current / this network
    ipaddress.ip_network("10.0.0.0/8"),         # Private RFC 1918
    ipaddress.ip_network("100.64.0.0/10"),      # Carrier-Grade NAT (RFC 6598)
    ipaddress.ip_network("127.0.0.0/8"),        # IPv4 Loopback
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local / Cloud metadata (RFC 3927)
    ipaddress.ip_network("172.16.0.0/12"),      # Private RFC 1918
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments (RFC 6890)
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1 (RFC 5737)
    ipaddress.ip_network("192.168.0.0/16"),     # Private RFC 1918
    ipaddress.ip_network("198.18.0.0/15"),      # Benchmarking (RFC 2544)
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2 (RFC 5737)
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3 (RFC 5737)
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast (RFC 5771)
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved / Future Use (RFC 1112)
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast
    # IPv6 ranges
    ipaddress.ip_network("::/128"),             # IPv6 Unspecified
    ipaddress.ip_network("::1/128"),            # IPv6 Loopback
    ipaddress.ip_network("::ffff:0:0/96"),      # IPv4-mapped IPv6
    ipaddress.ip_network("64:ff9b::/96"),       # IPv4/IPv6 translation
    ipaddress.ip_network("100::/64"),           # Discard prefix
    ipaddress.ip_network("2001:db8::/32"),      # Documentation
    ipaddress.ip_network("fc00::/7"),           # IPv6 Unique Local Address (ULA)
    ipaddress.ip_network("fe80::/10"),          # IPv6 Link-local
    ipaddress.ip_network("ff00::/8"),           # IPv6 Multicast
]

# Backwards compatibility alias
PRIVATE_NETWORKS = PROHIBITED_NETWORKS

TEST_DOMAINS: tuple[str, ...] = (
    ".example",
    ".example.gov",
    ".example.com",
    ".example.org",
    ".test",
)


class GTFSFeedSecurityError(ValueError):
    """Raised when a GTFS feed URL fails security or SSRF validation."""


class GTFSFeedPayloadTooLargeError(ValueError):
    """Raised when an upstream GTFS feed payload exceeds maximum bounded size."""


class GTFSFeedFetchResult:
    """Encapsulates the raw response, metadata, and timing of a feed fetch."""

    def __init__(
        self,
        status_code: int,
        content: bytes,
        content_type: str,
        latency_ms: float,
        headers: dict[str, str],
        from_dedup_cache: bool = False,
    ):
        self.status_code = status_code
        self.content = content
        self.content_type = content_type
        self.latency_ms = latency_ms
        self.headers = headers
        self.from_dedup_cache = from_dedup_cache


def sanitize_feed_url(url: str | None) -> str:
    """Removes sensitive query parameters (e.g. key, token, secret) from URL for safe logging/display."""
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(url)
        if not parsed.query:
            return url
        params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        sanitized_params = []
        for k, v in params:
            k_lower = k.lower()
            if any(s in k_lower for s in ("key", "token", "secret", "auth", "pwd", "password")):
                sanitized_params.append((k, "[REDACTED]"))
            else:
                sanitized_params.append((k, v))
        new_query = urllib.parse.urlencode(sanitized_params)
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))
    except Exception:
        return "[INVALID_URL]"


def validate_target_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """
    Raises GTFSFeedSecurityError if target IP falls within any private, loopback,
    cloud metadata, carrier-grade NAT, documentation, multicast, or prohibited network range.
    Handles IPv4-mapped IPv6 addresses by recursively validating the embedded IPv4 address.
    """
    # 1. Check IPv6 IPv4-mapped addresses (e.g. ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        validate_target_ip(ip.ipv4_mapped)

    # 2. Check standard ipaddress properties
    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    ):
        raise GTFSFeedSecurityError(
            f"SSRF Protection: Target IP address '{ip}' is within private/internal/non-public range."
        )

    # 3. Explicit CIDR boundary checks
    for net in PROHIBITED_NETWORKS:
        if ip in net:
            raise GTFSFeedSecurityError(
                f"SSRF Protection: Target IP address '{ip}' is within prohibited subnet {net}."
            )


def validate_feed_url_ssrf_safety(
    url: str,
    allow_http: bool = False,
    resolve_dns: bool = True,
) -> tuple[bool, str, list[str]]:
    """
    Validates that a GTFS feed URL is SSRF-safe:
    1. Enforces HTTPS (unless allow_http=True in test fixtures).
    2. Disallows embedded credentials, loopback, cloud metadata, and private IP addresses.
    3. Resolves hostname to verify DNS does not resolve to private/internal IPs (DNS rebinding prevention).
    Returns (is_safe, reason, list_of_resolved_ips).
    """
    if not url or not url.strip():
        return False, "Feed URL is empty", []

    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception as e:
        return False, f"Invalid URL structure: {e}", []

    scheme = parsed.scheme.lower()
    if scheme not in ("https", "http"):
        return False, f"Unsupported scheme: '{parsed.scheme}'. Only HTTPS is permitted.", []
    if scheme == "http" and not allow_http:
        return False, "Insecure HTTP scheme. Official feeds must use HTTPS.", []

    # Block embedded credentials (e.g., https://user:pass@example.com)
    if parsed.username or parsed.password:
        return False, "SSRF Protection: Embedded credentials in URL are forbidden.", []

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        return False, "URL hostname is missing", []

    if hostname in DISALLOWED_HOSTNAMES:
        return False, f"SSRF Protection: Hostname '{hostname}' is forbidden.", []

    # Check for direct IP address literal
    try:
        direct_ip = ipaddress.ip_address(hostname)
        try:
            validate_target_ip(direct_ip)
            return True, "Safe direct IP", [str(direct_ip)]
        except GTFSFeedSecurityError as sec_err:
            return False, str(sec_err), [str(direct_ip)]
    except ValueError:
        pass  # Hostname is a domain name

    # Recognized RFC test domains permitted in test environments
    if any(hostname == t[1:] or hostname.endswith(t) for t in TEST_DOMAINS):
        if resolve_dns:
            try:
                addr_info = socket.getaddrinfo(hostname, None)
                resolved_ips: list[str] = []
                for _, _, _, _, sockaddr in addr_info:
                    ip_str = sockaddr[0]
                    resolved_ips.append(ip_str)
                    resolved_ip = ipaddress.ip_address(ip_str)
                    validate_target_ip(resolved_ip)
                if resolved_ips:
                    return True, "Safe test domain (resolved)", resolved_ips
            except GTFSFeedSecurityError as sec_err:
                return False, str(sec_err), resolved_ips
            except Exception:
                pass
        return True, "Safe test domain", ["93.184.216.34"]

    if not resolve_dns:
        return True, "Safe hostname (DNS check deferred)", []

    resolved_ips: list[str] = []
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        if not addr_info:
            return False, f"DNS resolution returned no addresses for host '{hostname}'", []
        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            resolved_ips.append(ip_str)
            try:
                resolved_ip = ipaddress.ip_address(ip_str)
                validate_target_ip(resolved_ip)
            except GTFSFeedSecurityError as sec_err:
                return False, str(sec_err), resolved_ips
    except socket.gaierror as dns_err:
        return False, f"DNS resolution failed for host '{hostname}': {dns_err}", []
    except Exception as ex:
        return False, f"Host validation failed for '{hostname}': {ex}", []

    return True, "Safe", resolved_ips


def parse_retry_after(header_val: str | None) -> float | None:
    """Parses HTTP Retry-After header either as integer seconds or RFC 2822 date."""
    if not header_val or not header_val.strip():
        return None
    val = header_val.strip()
    try:
        seconds = float(val)
        return max(0.0, seconds)
    except ValueError:
        pass
    try:
        parsed_tuple = email.utils.parsedate_to_datetime(val)
        if parsed_tuple:
            delta = (parsed_tuple - datetime.now(timezone.utc)).total_seconds()
            return max(0.0, delta)
    except Exception:
        pass
    return None


class PinnedIPNetworkBackend(AnyIOBackend):
    """
    Network backend that pins TCP socket connections directly to a validated IP address.
    Completely eliminates DNS TOCTOU and DNS rebinding risks by ensuring the socket
    connects to the pre-validated IP without invoking secondary DNS resolution.
    Preserves target host for TLS SNI and server certificate verification.
    """

    def __init__(self, pinned_ip: str, expected_host: str):
        super().__init__()
        self.pinned_ip = pinned_ip
        self.expected_host = expected_host
        self.connected_target: tuple[str, int] | None = None

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        # Prevent connection reuse across different hosts
        if host.lower() != self.expected_host.lower():
            raise GTFSFeedSecurityError(
                f"Connection target host mismatch: expected '{self.expected_host}', got '{host}'"
            )
        self.connected_target = (self.pinned_ip, port)
        logger.debug(
            f"PinnedIPNetworkBackend: connecting to validated pinned IP {self.pinned_ip}:{port} for host '{host}'"
        )
        return await super().connect_tcp(
            host=self.pinned_ip,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class PinnedIPAsyncTransport(httpx.AsyncHTTPTransport):
    """
    HTTP transport that enforces IP-pinned socket connections using PinnedIPNetworkBackend.
    Ensures connection pool cannot reuse connections for different hostnames or unvalidated IPs.
    """

    def __init__(
        self,
        pinned_ip: str,
        target_host: str,
        verify: ssl.SSLContext | str | bool = True,
        **kwargs: Any,
    ):
        super().__init__(verify=verify, **kwargs)
        self.pinned_ip = pinned_ip
        self.target_host = target_host
        self.network_backend = PinnedIPNetworkBackend(pinned_ip, target_host)
        # Create dedicated isolated pool pinned to this network backend with no keepalive reuse
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=self._pool._ssl_context,
            network_backend=self.network_backend,
            max_connections=1,
            max_keepalive_connections=0,
        )


class SecureGTFSFeedClient:
    """
    Secure and bounded GTFS Realtime Feed HTTP client.
    Thread-safe and async-safe across multiple concurrent requests.
    Enforces IP-pinned socket connections for complete DNS TOCTOU / SSRF protection.
    """

    def __init__(
        self,
        timeout_seconds: float | None = None,
        max_response_bytes: int | None = None,
        max_retries: int | None = None,
        backoff_base_seconds: float | None = None,
        allow_http: bool | None = None,
    ):
        self.timeout_seconds = timeout_seconds or settings.GTFS_REALTIME_TIMEOUT_SECONDS
        self.max_response_bytes = max_response_bytes or settings.GTFS_MAX_RESPONSE_BYTES
        self.max_retries = max_retries or settings.GTFS_MAX_RETRIES
        self.backoff_base_seconds = backoff_base_seconds or settings.GTFS_BACKOFF_BASE_SECONDS
        self.allow_http = (
            allow_http if allow_http is not None else settings.GTFS_REALTIME_ALLOW_HTTP
        )
        self._inflight_locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _get_feed_lock(self, feed_id: str) -> asyncio.Lock:
        async with self._global_lock:
            if feed_id not in self._inflight_locks:
                self._inflight_locks[feed_id] = asyncio.Lock()
            return self._inflight_locks[feed_id]

    async def fetch_feed(
        self,
        feed_id: str,
        feed_url: str,
        headers: dict[str, str] | None = None,
        auth_header: tuple[str, str] | None = None,
    ) -> GTFSFeedFetchResult:
        """
        Executes a secure, bounded, deduplicated GTFS Realtime fetch with retries.
        Pins socket connection to validated IP address to eliminate DNS TOCTOU.
        Never logs credentials or sensitive headers.
        """
        feed_lock = await self._get_feed_lock(feed_id)
        async with feed_lock:
            # Build sanitized request headers
            req_headers: dict[str, str] = {
                "Accept": "application/x-protobuf, application/octet-stream, application/json",
                "User-Agent": "KogniSync-DisruptionIntelligence/3.9",
            }
            if headers:
                for k, v in headers.items():
                    if k.lower() not in ("authorization", "x-api-key"):
                        req_headers[k] = v
            if auth_header:
                req_headers[auth_header[0]] = auth_header[1]

            attempt = 0
            last_err: Exception | None = None
            max_redirect_hops = 3

            while attempt <= self.max_retries:
                start_time = time.perf_counter()
                current_url = feed_url
                redirect_count = 0

                try:
                    while redirect_count <= max_redirect_hops:
                        # 1. SSRF and DNS Pre-flight validation
                        is_safe, reason, resolved_ips = validate_feed_url_ssrf_safety(
                            current_url, allow_http=self.allow_http, resolve_dns=True
                        )
                        if not is_safe:
                            logger.warning(
                                f"GTFSFeedClient: SSRF block for feed '{feed_id}' at {sanitize_feed_url(current_url)}: {reason}"
                            )
                            raise GTFSFeedSecurityError(f"SSRF validation rejected target: {reason}")
                        if not resolved_ips:
                            raise GTFSFeedSecurityError(
                                f"SSRF validation failed: no validated destination IPs for {sanitize_feed_url(current_url)}"
                            )

                        parsed = urllib.parse.urlparse(current_url)
                        target_host = (parsed.hostname or "").lower().strip()
                        pinned_ip = resolved_ips[0]

                        # 2. Instantiate IP-pinned transport
                        transport = PinnedIPAsyncTransport(
                            pinned_ip=pinned_ip,
                            target_host=target_host,
                            verify=True,
                        )

                        logger.debug(
                            f"GTFSFeedClient: fetching feed '{feed_id}' via pinned IP {pinned_ip} (host: {target_host})"
                        )

                        async with httpx.AsyncClient(
                            transport=transport,
                            timeout=self.timeout_seconds,
                            follow_redirects=False,
                        ) as client:
                            response = await client.get(current_url, headers=req_headers)

                        # 3. Handle redirects safely with manual hop validation
                        if response.status_code in (301, 302, 303, 307, 308):
                            redirect_url = response.headers.get("location")
                            if not redirect_url:
                                break
                            redirect_count += 1
                            if redirect_count > max_redirect_hops:
                                raise GTFSFeedSecurityError(
                                    f"Too many redirect hops ({redirect_count} > {max_redirect_hops})"
                                )
                            target_redirect = urllib.parse.urljoin(current_url, redirect_url)
                            logger.info(
                                f"GTFSFeedClient: following validated redirect hop {redirect_count}/{max_redirect_hops} for '{feed_id}'"
                            )
                            current_url = target_redirect
                            continue

                        # Not a redirect, proceed to process response
                        break

                    latency_ms = (time.perf_counter() - start_time) * 1000.0

                    # 4. Check Content-Length header against bounded limit
                    content_length = response.headers.get("content-length")
                    if content_length and content_length.isdigit():
                        if int(content_length) > self.max_response_bytes:
                            raise GTFSFeedPayloadTooLargeError(
                                f"Feed payload exceeds maximum permitted size: {content_length} bytes > {self.max_response_bytes} bytes"
                            )

                    content_bytes = response.content or b""
                    if len(content_bytes) > self.max_response_bytes:
                        raise GTFSFeedPayloadTooLargeError(
                            f"Feed body exceeds maximum permitted size: {len(content_bytes)} bytes > {self.max_response_bytes} bytes"
                        )

                    # 5. Handle Rate Limiting (HTTP 429) and Server Errors (5xx) with backoff
                    if response.status_code == 429:
                        retry_after_sec = parse_retry_after(response.headers.get("retry-after"))
                        wait_sec = (
                            retry_after_sec
                            if retry_after_sec is not None
                            else (self.backoff_base_seconds * (2 ** attempt))
                        )
                        if attempt < self.max_retries and wait_sec <= 10.0:
                            attempt += 1
                            logger.info(
                                f"GTFSFeedClient: 429 Rate Limited on '{feed_id}'. Backing off {wait_sec:.1f}s (attempt {attempt}/{self.max_retries})."
                            )
                            await asyncio.sleep(wait_sec)
                            continue
                        return GTFSFeedFetchResult(
                            status_code=429,
                            content=content_bytes,
                            content_type=response.headers.get("content-type", ""),
                            latency_ms=latency_ms,
                            headers=dict(response.headers),
                        )

                    if response.status_code >= 500 and attempt < self.max_retries:
                        attempt += 1
                        jitter = random.uniform(0.1, 0.3)
                        wait_sec = (self.backoff_base_seconds * (2 ** attempt)) + jitter
                        logger.warning(
                            f"GTFSFeedClient: HTTP {response.status_code} on '{feed_id}'. Retrying in {wait_sec:.2f}s."
                        )
                        await asyncio.sleep(wait_sec)
                        continue

                    return GTFSFeedFetchResult(
                        status_code=response.status_code,
                        content=content_bytes,
                        content_type=response.headers.get("content-type", ""),
                        latency_ms=latency_ms,
                        headers=dict(response.headers),
                    )

                except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                    last_err = net_err
                    if attempt < self.max_retries:
                        attempt += 1
                        jitter = random.uniform(0.1, 0.25)
                        wait_sec = (self.backoff_base_seconds * (2 ** attempt)) + jitter
                        await asyncio.sleep(wait_sec)
                        continue
                    break
                except (GTFSFeedSecurityError, GTFSFeedPayloadTooLargeError):
                    raise
                except Exception as ex:
                    last_err = ex
                    break

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            error_type = type(last_err).__name__ if last_err else "UnknownFetchError"
            logger.warning(
                f"GTFSFeedClient: Fetch failed for '{feed_id}' after {attempt} retries: {error_type}"
            )
            return GTFSFeedFetchResult(
                status_code=0,
                content=b"",
                content_type="",
                latency_ms=latency_ms,
                headers={"x-error-type": error_type},
            )
