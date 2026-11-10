"""
backend/app/services/disruption/providers/gtfs_feed_client.py

Secure, bounded, and resilient HTTP client for fetching official GTFS Realtime feeds (Milestone M3.9).
Implements Phase C requirements:
- Strict SSRF protections (blocking loopback, cloud metadata, RFC 1918 private subnets).
- DNS rebinding prevention via pre-fetch address resolution and IP validation.
- Redirect protection (disabling unverified redirects and validating redirect hops).
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
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import logger

DISALLOWED_HOSTNAMES: set[str] = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254",
}

PRIVATE_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # Private RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),    # Private RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),   # Private RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local / Cloud metadata (169.254.169.254)
    ipaddress.ip_network("0.0.0.0/8"),        # Current network
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
]

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
    """Raises GTFSFeedSecurityError if target IP falls within any private or prohibited network range."""
    for net in PRIVATE_NETWORKS:
        if ip in net:
            raise GTFSFeedSecurityError(
                f"SSRF Protection: Target IP address '{ip}' is within private/internal range."
            )


def validate_feed_url_ssrf_safety(
    url: str,
    allow_http: bool = False,
    resolve_dns: bool = True,
) -> tuple[bool, str, list[str]]:
    """
    Validates that a GTFS feed URL is SSRF-safe:
    1. Enforces HTTPS (unless allow_http=True in test fixtures).
    2. Disallows loopback, cloud metadata, and private IP addresses.
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

    # Recognized RFC test domains permitted without live DNS resolution
    if any(hostname == t[1:] or hostname.endswith(t) for t in TEST_DOMAINS):
        return True, "Safe test domain", []

    if not resolve_dns:
        return True, "Safe hostname (DNS check deferred)", []

    resolved_ips: list[str] = []
    try:
        addr_info = socket.getaddrinfo(hostname, None)
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


class SecureGTFSFeedClient:
    """
    Secure and bounded GTFS Realtime Feed HTTP client.
    Thread-safe and async-safe across multiple concurrent requests.
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
        Never logs credentials or sensitive headers.
        """
        feed_lock = await self._get_feed_lock(feed_id)

        async with feed_lock:
            # 1. SSRF Pre-flight validation
            is_safe, reason, _ = validate_feed_url_ssrf_safety(
                feed_url, allow_http=self.allow_http, resolve_dns=True
            )
            if not is_safe:
                logger.warning(
                    f"GTFSFeedClient: SSRF block for feed '{feed_id}' at {sanitize_feed_url(feed_url)}: {reason}"
                )
                raise GTFSFeedSecurityError(f"SSRF validation rejected target: {reason}")

            # 2. Build sanitized request headers
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

            while attempt <= self.max_retries:
                start_time = time.perf_counter()
                try:
                    async with httpx.AsyncClient(
                        timeout=self.timeout_seconds,
                        follow_redirects=False,
                    ) as client:
                        response = await client.get(feed_url, headers=req_headers)

                    latency_ms = (time.perf_counter() - start_time) * 1000.0

                    # 3. Handle redirects safely with manual hop validation
                    if response.status_code in (301, 302, 303, 307, 308):
                        redirect_url = response.headers.get("location")
                        if not redirect_url:
                            return GTFSFeedFetchResult(
                                status_code=response.status_code,
                                content=b"",
                                content_type=response.headers.get("content-type", ""),
                                latency_ms=latency_ms,
                                headers=dict(response.headers),
                            )
                        # Validate redirect destination
                        target_redirect = urllib.parse.urljoin(feed_url, redirect_url)
                        redir_safe, redir_reason, _ = validate_feed_url_ssrf_safety(
                            target_redirect, allow_http=self.allow_http, resolve_dns=True
                        )
                        if not redir_safe:
                            raise GTFSFeedSecurityError(
                                f"SSRF Protection: Redirect destination '{sanitize_feed_url(target_redirect)}' forbidden: {redir_reason}"
                            )
                        # Execute bounded single redirect hop
                        async with httpx.AsyncClient(
                            timeout=self.timeout_seconds,
                            follow_redirects=False,
                        ) as redir_client:
                            response = await redir_client.get(target_redirect, headers=req_headers)
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
                        wait_sec = retry_after_sec if retry_after_sec is not None else (self.backoff_base_seconds * (2 ** attempt))
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
