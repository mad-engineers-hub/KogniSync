"""
backend/app/services/disruption/providers/gtfs_realtime.py

GTFS Realtime Provider Foundation (Milestone M3.8).
Implements Trip Updates, Service Alerts, and Vehicle Positions entities adhering to
the GTFS Realtime specification (https://gtfs.org/documentation/realtime/reference/).
Enforces feed header validation, entity timestamp verification, feed freshness evaluation,
and transparent capability discovery.
If no authorized feed is configured, reports honestly as BLOCKED (never fabricates live transit data).
"""
import ipaddress
import socket
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Sequence
import httpx
from app.core.config import settings
from app.core.logging import logger
from app.services.disruption.providers.base import DisruptionProvider
from app.services.disruption.schemas import (
    DisruptionEvent,
    DisruptionEventType,
    DisruptionProviderCapability,
    DisruptionSeverity,
    ProviderConnectivityStatus,
)
from app.services.journey.schemas import CoordinatesSchema, TransportMode

MAX_GTFS_FEED_AGE_SECONDS = 600  # 10 minutes maximum acceptable feed age

DISALLOWED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
}

PRIVATE_NETWORKS = [
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


def is_ssrf_safe_url(url: str, allow_http: bool = False) -> tuple[bool, str]:
    """
    Validates that a GTFS feed URL is SSRF-safe:
    1. Enforces HTTPS (unless allow_http=True in test environments).
    2. Disallows loopback, cloud metadata, and private IP addresses.
    3. Resolves hostname to ensure DNS does not resolve to private/internal IPs.
    """
    if not url:
        return False, "Feed URL is empty"
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as e:
        return False, f"Invalid URL structure: {e}"

    if parsed.scheme.lower() not in ("https", "http"):
        return False, f"Unsupported scheme: '{parsed.scheme}'. Only HTTPS is permitted."
    if parsed.scheme.lower() == "http" and not allow_http:
        return False, "Insecure HTTP scheme. Official feeds must use HTTPS."

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        return False, "URL hostname is missing"

    if hostname in DISALLOWED_HOSTNAMES:
        return False, f"SSRF Protection: Hostname '{hostname}' is forbidden."

    # Reserved test domains (RFC 2606 / RFC 6761) permitted for testing without public DNS
    test_domains = (".example", ".example.gov", ".example.com", ".example.org", ".test")
    if any(hostname == t[1:] or hostname.endswith(t) for t in test_domains):
        return True, "Safe test domain"

    try:
        direct_ip = ipaddress.ip_address(hostname)
        for net in PRIVATE_NETWORKS:
            if direct_ip in net:
                return False, f"SSRF Protection: IP address '{hostname}' is within private/internal range."
    except ValueError:
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for _, _, _, _, sockaddr in addr_info:
                ip_str = sockaddr[0]
                resolved_ip = ipaddress.ip_address(ip_str)
                for net in PRIVATE_NETWORKS:
                    if resolved_ip in net:
                        return False, f"SSRF Protection: Host '{hostname}' resolves to private/internal IP {ip_str}."
        except socket.gaierror as dns_err:
            return False, f"DNS resolution failed for host '{hostname}': {dns_err}"
        except Exception:
            return False, f"Host validation failed for '{hostname}'"

    return True, "Safe"


class GTFSRealtimeProvider(DisruptionProvider):
    """
    Standard GTFS Realtime feed consumer.
    Supports JSON representation of GTFS-RT feeds where authorized.
    Enforces SSRF prevention, feed header validation, and entity freshness.
    """

    def __init__(
        self,
        feed_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        allow_http: bool | None = None,
    ):
        self._feed_url = feed_url or settings.GTFS_REALTIME_FEED_URL
        self._api_key = api_key or settings.GTFS_REALTIME_API_KEY
        self._timeout_seconds = timeout_seconds or settings.GTFS_REALTIME_TIMEOUT_SECONDS
        self._allow_http = (
            allow_http if allow_http is not None else settings.GTFS_REALTIME_ALLOW_HTTP
        )

        # Operational metrics
        self._last_successful_request: str | None = None
        self._last_failed_request: str | None = None
        self._last_feed_timestamp: int | None = None
        self._last_observation_time: str | None = None
        self._last_response_latency_ms: float | None = None
        self._consecutive_failure_count: int = 0
        self._last_status_reason: str = ""
        self._ssrf_blocked: bool = False

    @property
    def name(self) -> str:
        return "gtfs_realtime_feed"

    @property
    def display_name(self) -> str:
        return "Official GTFS Realtime Transit Feed"

    def is_configured(self) -> bool:
        if not settings.GTFS_REALTIME_ENABLED or not self._feed_url:
            return False
        if len(self._feed_url.strip()) <= 8:
            return False

        safe, reason = is_ssrf_safe_url(self._feed_url, allow_http=self._allow_http)
        if not safe:
            self._ssrf_blocked = True
            self._last_status_reason = reason
            return False
        return True

    def is_available(self) -> bool:
        """Returns True only when an authorized feed URL is configured and enabled."""
        return self.is_configured() and self._consecutive_failure_count < 3

    def get_connectivity_status(self) -> ProviderConnectivityStatus:
        if not settings.GTFS_REALTIME_ENABLED or not self._feed_url:
            return "unconfigured"
        if self._ssrf_blocked:
            return "blocked"
        if self._consecutive_failure_count >= 3:
            return "degraded"
        if self._last_successful_request:
            return "available"
        return "available"

    def get_capabilities(self) -> DisruptionProviderCapability:
        configured = self.is_configured()
        available = self.is_available()
        status = self.get_connectivity_status()

        if self._ssrf_blocked:
            notice = "BLOCKED — GTFS feed endpoint failed SSRF security validation."
            reason = self._last_status_reason or "Private or unapproved network target."
        elif not configured:
            notice = "BLOCKED — authorized GTFS Realtime feed unavailable."
            reason = "No authorized regional transit GTFS-RT endpoint configured in environment."
        elif status == "degraded":
            notice = f"DEGRADED — GTFS feed experienced {self._consecutive_failure_count} consecutive network errors."
            reason = self._last_status_reason or "Network connection errors."
        else:
            notice = "Connected to authorized GTFS Realtime transit feed."
            reason = f"Active feed endpoint: {self._feed_url}"

        return DisruptionProviderCapability(
            name=self.name,
            display_name=self.display_name,
            provider_type="gtfs_realtime",
            is_available=available,
            is_configured=configured,
            credentials_present=bool(self._api_key),
            connectivity_status=status,
            last_successful_request=self._last_successful_request,
            last_failed_request=self._last_failed_request,
            last_observation_time=self._last_observation_time,
            last_response_latency_ms=self._last_response_latency_ms,
            consecutive_failure_count=self._consecutive_failure_count,
            is_rate_limited=False,
            supported_attributes=[
                "trip_updates_delay",
                "trip_cancellations",
                "service_alerts",
                "vehicle_positions",
            ],
            supported_geographic_coverage="configured_feed_boundary",
            provenance_source="provider_live" if available else "unknown",
            supported_modes=["bus", "train", "metro"],
            status_notice=notice,
            status_reason=reason,
        )

    async def fetch_disruptions(
        self,
        corridor: str | None = None,
        modes: Sequence[TransportMode] | None = None,
        scenario: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> list[DisruptionEvent]:
        """
        Fetches and normalizes trip updates and service alerts from the GTFS Realtime feed.
        Fails safely if unconfigured or unreachable. Enforces SSRF and redirect limits.
        """
        if not self.is_available():
            logger.debug(
                "GTFSRealtimeProvider: fetch skipped — authorized feed unavailable or unconfigured."
            )
            return []

        headers: dict[str, str] = {"Accept": "application/x-protobuf, application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        start_t = time.perf_counter()
        try:
            assert self._feed_url is not None
            async with httpx.AsyncClient(timeout=self._timeout_seconds, follow_redirects=False) as client:
                response = await client.get(self._feed_url, headers=headers)
            latency_ms = (time.perf_counter() - start_t) * 1000.0

            if response.status_code == 200:
                self._record_success(latency_ms)
                # Attempt JSON decoding (or JSON-serialized GTFS-RT)
                try:
                    payload = response.json()
                    return self.parse_gtfs_payload(payload)
                except Exception as json_err:
                    logger.warning(f"GTFS Realtime non-JSON payload: {json_err}")
                    return []
            else:
                self._record_failure(response.status_code, f"HTTP {response.status_code}")
                return []
        except Exception as e:
            self._record_failure(0, type(e).__name__)
            logger.warning(f"GTFS Realtime fetch error: {type(e).__name__}")
            return []

    def _record_success(self, latency_ms: float) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        self._last_successful_request = now_iso
        self._last_observation_time = now_iso
        self._last_response_latency_ms = round(latency_ms, 1)
        self._consecutive_failure_count = 0
        self._last_status_reason = "Feed parsed successfully"

    def _record_failure(self, code: int, reason: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        self._last_failed_request = now_iso
        self._consecutive_failure_count += 1
        self._last_status_reason = f"{reason} ({code})" if code else reason

    def parse_gtfs_payload(self, data: dict[str, Any]) -> list[DisruptionEvent]:
        """
        Parses standardized GTFS Realtime entity dictionaries.
        Supports:
        - header timestamp freshness validation
        - trip_update entities
        - alert entities
        - vehicle entities (positions)
        """
        events: list[DisruptionEvent] = []
        now = datetime.now(timezone.utc)
        now_ts = int(now.timestamp())
        now_iso = now.isoformat()

        header = data.get("header", {})
        feed_ts = header.get("timestamp")
        if isinstance(feed_ts, (int, float)):
            self._last_feed_timestamp = int(feed_ts)
            # Freshness check: reject feed if older than 10 minutes
            feed_age = now_ts - int(feed_ts)
            if feed_age > MAX_GTFS_FEED_AGE_SECONDS:
                logger.warning(
                    f"GTFS Realtime feed is stale (header age: {feed_age}s > {MAX_GTFS_FEED_AGE_SECONDS}s)."
                )
                return []

        feed_observation_iso = (
            datetime.fromtimestamp(int(feed_ts), tz=timezone.utc).isoformat()
            if isinstance(feed_ts, (int, float))
            else now_iso
        )

        entities = data.get("entity", [])
        if not isinstance(entities, list):
            return []

        for entity in entities:
            try:
                # 1. Parse Alert Entity
                if "alert" in entity:
                    alert_ev = self._parse_alert_entity(entity, feed_observation_iso, now_iso)
                    if alert_ev:
                        events.append(alert_ev)

                # 2. Parse Trip Update Entity
                elif "trip_update" in entity or "tripUpdate" in entity:
                    tu_ev = self._parse_trip_update_entity(entity, feed_observation_iso, now_iso)
                    if tu_ev:
                        events.append(tu_ev)

                # 3. Parse Vehicle Entity (Positions & Congestion)
                elif "vehicle" in entity:
                    veh_ev = self._parse_vehicle_entity(entity, feed_observation_iso, now_iso)
                    if veh_ev:
                        events.append(veh_ev)

            except Exception as ent_err:
                logger.debug(f"Failed to parse GTFS-RT entity {entity.get('id')}: {ent_err}")
                continue

        return events

    def _parse_alert_entity(
        self, entity: dict[str, Any], observation_iso: str, fetched_iso: str
    ) -> DisruptionEvent | None:
        alert = entity.get("alert", {})
        entity_id = str(entity.get("id", f"alert-{time.time_ns()}"))

        header_text = self._extract_translated_string(alert.get("header_text") or alert.get("headerText"))
        desc_text = self._extract_translated_string(alert.get("description_text") or alert.get("descriptionText"))

        cause = alert.get("cause", "UNKNOWN_CAUSE")
        effect = alert.get("effect", "UNKNOWN_EFFECT")

        # Map effect to DisruptionEventType and severity
        if effect in ("NO_SERVICE", "SIGNIFICANT_DELAYS"):
            event_type: DisruptionEventType = "service_cancellation" if effect == "NO_SERVICE" else "transport_delay"
            severity: DisruptionSeverity = "critical"
        elif effect in ("REDUCED_SERVICE", "MODIFIED_SERVICE"):
            event_type = "transport_delay"
            severity = "high"
        elif effect in ("STOP_MOVED", "ADDITIONAL_SERVICE"):
            event_type = "station_disruption"
            severity = "moderate"
        else:
            event_type = "transport_delay"
            severity = "moderate"

        # Validity interval
        active_periods = alert.get("active_period") or alert.get("activePeriod") or []
        start_iso = observation_iso
        end_iso: str | None = None
        if isinstance(active_periods, list) and len(active_periods) > 0:
            first_p = active_periods[0]
            if first_p.get("start"):
                start_iso = datetime.fromtimestamp(int(first_p["start"]), tz=timezone.utc).isoformat()
            if first_p.get("end"):
                end_iso = datetime.fromtimestamp(int(first_p["end"]), tz=timezone.utc).isoformat()

        # Entity-specific timestamp if present
        alert_ts = alert.get("timestamp") or entity.get("timestamp")
        alert_obs_iso = (
            datetime.fromtimestamp(int(alert_ts), tz=timezone.utc).isoformat()
            if isinstance(alert_ts, (int, float))
            else observation_iso
        )

        title = header_text or f"Transit Alert: {event_type.replace('_', ' ').title()}"
        description = desc_text or f"Cause: {cause}; Effect: {effect}"

        return DisruptionEvent(
            id=f"gtfs-alert-{entity_id}",
            source="gtfs_realtime",
            source_id=entity_id,
            event_type=event_type,
            severity=severity,
            status="active",
            title=title,
            description=description,
            affected_modes=["bus", "train", "metro"],
            point=None,
            radius_meters=3000.0,
            valid_from=start_iso,
            valid_until=end_iso,
            observed_at=alert_obs_iso,
            last_verified_at=fetched_iso,
            fetched_at=fetched_iso,
            provenance="provider_live",
            confidence=0.95,
            estimated_delay_minutes=20 if severity in ("high", "critical") else 5,
        )

    def _parse_trip_update_entity(
        self, entity: dict[str, Any], observation_iso: str, fetched_iso: str
    ) -> DisruptionEvent | None:
        tu = entity.get("trip_update") or entity.get("tripUpdate") or {}
        trip = tu.get("trip", {})
        trip_id = str(trip.get("trip_id") or trip.get("tripId") or "")
        route_id = str(trip.get("route_id") or trip.get("routeId") or "")

        tu_ts = tu.get("timestamp") or entity.get("timestamp")
        tu_obs_iso = (
            datetime.fromtimestamp(int(tu_ts), tz=timezone.utc).isoformat()
            if isinstance(tu_ts, (int, float))
            else observation_iso
        )

        sched_rel = trip.get("schedule_relationship") or trip.get("scheduleRelationship")
        if sched_rel == "CANCELED":
            return DisruptionEvent(
                id=f"gtfs-cancel-{entity.get('id', trip_id)}",
                source="gtfs_realtime",
                source_id=trip_id,
                event_type="service_cancellation",
                severity="critical",
                status="active",
                title=f"Transit Trip {trip_id or route_id or 'Scheduled'} Canceled",
                description=f"Trip {trip_id} on route {route_id} reported canceled by official transit agency.",
                affected_modes=["bus", "train", "metro"],
                point=None,
                valid_from=tu_obs_iso,
                valid_until=None,
                observed_at=tu_obs_iso,
                last_verified_at=fetched_iso,
                fetched_at=fetched_iso,
                provenance="provider_live",
                confidence=0.99,
                estimated_delay_minutes=60,
            )

        # Stop time updates
        stop_updates = tu.get("stop_time_update") or tu.get("stopTimeUpdate") or []
        max_delay_sec = 0
        if isinstance(stop_updates, list):
            for stu in stop_updates:
                arr = stu.get("arrival", {})
                dep = stu.get("departure", {})
                d = arr.get("delay") or dep.get("delay")
                if isinstance(d, (int, float)) and d > max_delay_sec:
                    max_delay_sec = int(d)

        # Only create event if delay is meaningful (>= 5 minutes)
        if max_delay_sec < 300:
            return None

        delay_minutes = max_delay_sec // 60
        severity: DisruptionSeverity = "critical" if delay_minutes >= 45 else ("high" if delay_minutes >= 20 else "moderate")

        return DisruptionEvent(
            id=f"gtfs-delay-{entity.get('id', trip_id)}",
            source="gtfs_realtime",
            source_id=trip_id,
            event_type="transport_delay",
            severity=severity,
            status="active",
            title=f"Trip Delay (+{delay_minutes} min): Route {route_id or 'Corridor'}",
            description=f"Official agency reported {delay_minutes}-minute delay on trip {trip_id or route_id}.",
            affected_modes=["bus", "train", "metro"],
            point=None,
            valid_from=tu_obs_iso,
            valid_until=None,
            observed_at=tu_obs_iso,
            last_verified_at=fetched_iso,
            fetched_at=fetched_iso,
            provenance="provider_live",
            confidence=0.95,
            estimated_delay_minutes=delay_minutes,
            delay_seconds=max_delay_sec,
        )

    def _parse_vehicle_entity(
        self, entity: dict[str, Any], observation_iso: str, fetched_iso: str
    ) -> DisruptionEvent | None:
        veh = entity.get("vehicle", {})
        entity_id = str(entity.get("id", f"veh-{time.time_ns()}"))
        trip = veh.get("trip", {})
        trip_id = str(trip.get("trip_id") or trip.get("tripId") or "")
        route_id = str(trip.get("route_id") or trip.get("routeId") or "")
        position = veh.get("position", {})

        coords_pt: CoordinatesSchema | None = None
        if "latitude" in position and "longitude" in position:
            try:
                lat = float(position["latitude"])
                lng = float(position["longitude"])
                coords_pt = CoordinatesSchema(lat=lat, lng=lng)
            except (ValueError, TypeError):
                coords_pt = None

        congestion_level = veh.get("congestion_level") or veh.get("congestionLevel")
        if congestion_level in ("CONGESTION", "SEVERE_CONGESTION", "STOP_AND_GO", 2, 3, 4):
            severity: DisruptionSeverity = "critical" if congestion_level in ("SEVERE_CONGESTION", 4) else "high"
            event_type: DisruptionEventType = "traffic_congestion"
            desc = f"Transit vehicle on route {route_id or trip_id or 'transit'} reported {congestion_level} congestion."
        else:
            return None

        veh_ts = veh.get("timestamp") or entity.get("timestamp")
        veh_obs_iso = (
            datetime.fromtimestamp(int(veh_ts), tz=timezone.utc).isoformat()
            if isinstance(veh_ts, (int, float))
            else observation_iso
        )

        return DisruptionEvent(
            id=f"gtfs-veh-{entity_id}",
            source="gtfs_realtime",
            source_id=entity_id,
            event_type=event_type,
            severity=severity,
            status="active",
            title=f"Transit Congestion: Route {route_id or trip_id or 'Line'}",
            description=desc,
            affected_modes=["bus", "metro"],
            point=coords_pt,
            radius_meters=1500.0,
            valid_from=veh_obs_iso,
            valid_until=None,
            observed_at=veh_obs_iso,
            last_verified_at=fetched_iso,
            fetched_at=fetched_iso,
            provenance="provider_live",
            confidence=0.95,
            estimated_delay_minutes=15 if severity == "critical" else 8,
        )

    def _extract_translated_string(self, obj: Any) -> str:
        if not obj:
            return ""
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            trans = obj.get("translation", [])
            if isinstance(trans, list) and len(trans) > 0:
                first = trans[0]
                if isinstance(first, dict):
                    return str(first.get("text", ""))
        return ""
