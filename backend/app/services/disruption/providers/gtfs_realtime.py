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
import json
import socket
import time
import urllib.parse
from datetime import datetime, timezone
import math
from typing import Any, Sequence
from app.core.config import settings
from app.core.logging import logger
from app.services.disruption.providers.base import DisruptionProvider
from app.services.disruption.providers.gtfs_feed_client import (
    GTFSFeedPayloadTooLargeError,
    GTFSFeedSecurityError,
    SecureGTFSFeedClient,
    sanitize_feed_url,
    validate_feed_url_ssrf_safety,
)
from app.services.disruption.providers.gtfs_protobuf import (
    CAUSE_MAP,
    CONGESTION_LEVEL_MAP,
    EFFECT_MAP,
    SCHEDULE_RELATIONSHIP_MAP,
    decode_gtfs_feed,
)
from app.services.disruption.providers.iudx_adapter import (
    is_iudx_payload,
    normalize_iudx_payload,
)
from app.services.disruption.schemas import (
    DisruptionEvent,
    DisruptionEventType,
    DisruptionProviderCapability,
    DisruptionSeverity,
    ProviderConnectivityStatus,
)
from app.services.journey.schemas import CoordinatesSchema, TransportMode

MAX_GTFS_FEED_AGE_SECONDS = 600  # 10 minutes maximum acceptable feed age


def is_ssrf_safe_url(url: str, allow_http: bool = False) -> tuple[bool, str]:
    """
    Validates that a GTFS feed URL is SSRF-safe:
    1. Enforces HTTPS (unless allow_http=True in test environments).
    2. Disallows loopback, cloud metadata, and private IP addresses.
    3. Resolves hostname to ensure DNS does not resolve to private/internal IPs (DNS rebinding prevention).
    """
    is_safe, reason, _ = validate_feed_url_ssrf_safety(url, allow_http=allow_http, resolve_dns=True)
    return is_safe, reason


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
        registry: Any | None = None,
    ):
        self._explicit_feed_url = feed_url
        self._feed_url = feed_url or settings.GTFS_REALTIME_FEED_URL
        self._api_key = api_key or settings.GTFS_REALTIME_API_KEY
        self._timeout_seconds = timeout_seconds or settings.GTFS_REALTIME_TIMEOUT_SECONDS
        self._allow_http = (
            allow_http if allow_http is not None else settings.GTFS_REALTIME_ALLOW_HTTP
        )
        self._direct_client = SecureGTFSFeedClient(
            timeout_seconds=self._timeout_seconds,
            allow_http=self._allow_http,
            max_retries=0,
        )
        if registry is not None:
            self.registry = registry
        else:
            from app.services.disruption.providers.gtfs_registry import gtfs_feed_registry
            self.registry = gtfs_feed_registry

        # Operational metrics
        self._last_successful_request: str | None = None
        self._last_failed_request: str | None = None
        self._last_feed_timestamp: int | None = None
        self._last_observation_time: str | None = None
        self._last_response_latency_ms: float | None = None
        self._consecutive_failure_count: int = 0
        self._last_status_reason: str = ""
        self._ssrf_blocked: bool = False

    def _has_active_registry_mode(self) -> bool:
        """Uses unified GTFSFeedRegistry multi-feed mode unless explicit direct URL override is active."""
        if self._explicit_feed_url is not None:
            return False
        enabled_ids = self.registry.get_enabled_feed_ids() if hasattr(self.registry, "get_enabled_feed_ids") else []
        return len(enabled_ids) > 0

    def _enabled_registry_statuses(self) -> list[Any]:
        if not hasattr(self.registry, "get_enabled_feed_ids"):
            return []
        statuses = []
        for fid in self.registry.get_enabled_feed_ids():
            st = self.registry.get_feed_status(fid)
            if st is not None:
                statuses.append(st)
        return statuses

    @property
    def name(self) -> str:
        return "gtfs_realtime_feed"

    @property
    def display_name(self) -> str:
        return "Official GTFS Realtime Transit Feed"

    def is_configured(self) -> bool:
        if self._has_active_registry_mode():
            statuses = self._enabled_registry_statuses()
            return any(
                s.connectivity_status not in ("unconfigured", "disabled")
                for s in statuses
            )

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
        """Returns True only when an authorized feed URL is configured and healthy."""
        if self._has_active_registry_mode():
            if not self.is_configured():
                return False
            return self.get_connectivity_status() not in ("blocked", "degraded", "unconfigured", "disabled")
        return self.is_configured() and self._consecutive_failure_count < 3

    def get_connectivity_status(self) -> ProviderConnectivityStatus:
        if self._has_active_registry_mode():
            statuses = self._enabled_registry_statuses()
            if not statuses or not self.is_configured():
                return "unconfigured"
            conn_states = {s.connectivity_status for s in statuses}
            if "available" in conn_states:
                return "available"
            if conn_states == {"blocked"}:
                return "blocked"
            if "degraded" in conn_states:
                return "degraded"
            if "rate_limited" in conn_states:
                return "rate_limited"
            return "unknown"

        if not settings.GTFS_REALTIME_ENABLED or not self._feed_url:
            return "unconfigured"
        if self._ssrf_blocked:
            return "blocked"
        if self._consecutive_failure_count >= 3:
            return "degraded"
        if self._last_successful_request:
            return "available"
        return "unknown"

    def get_capabilities(self) -> DisruptionProviderCapability:
        configured = self.is_configured()
        available = self.is_available()
        status = self.get_connectivity_status()

        if self._has_active_registry_mode():
            statuses = self._enabled_registry_statuses()
            verified_timestamps = [s.last_successful_fetch for s in statuses if s.last_successful_fetch]
            latest_verified = max(verified_timestamps) if verified_timestamps else self._last_successful_request
            latencies = [s.last_response_latency_ms for s in statuses if s.last_response_latency_ms is not None]
            avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else self._last_response_latency_ms
            max_failures = max((s.consecutive_failure_count for s in statuses), default=self._consecutive_failure_count)
            has_creds = any(s.authorization_status == "authorized" for s in statuses)

            if not configured:
                notice = "BLOCKED — authorized GTFS Realtime feed unavailable."
                reason = "Registered feeds are awaiting authorized agency credentials."
            elif status == "blocked":
                blockers = [s.live_blocker_reason or s.status_notice for s in statuses if s.connectivity_status == "blocked"]
                notice = "BLOCKED — transit feed authorization or security check failed."
                reason = "; ".join(blockers[:2]) or "Upstream authorization rejected."
            elif status == "degraded":
                notice = "DEGRADED — registered transit feeds experiencing upstream errors."
                reason = "; ".join(s.status_notice for s in statuses[:2])
            elif not latest_verified:
                notice = "Configured — awaiting initial live connection verification."
                reason = ", ".join(f"{s.operator_name} ({s.feed_url_sanitized})" for s in statuses)
            else:
                op_names = [s.operator_name for s in statuses if s.connectivity_status == "available"]
                notice = f"Connected to {len(op_names)} verified live transit feed(s)."
                reason = f"Operational feeds: {', '.join(op_names)}"

            return DisruptionProviderCapability(
                name=self.name,
                display_name=self.display_name,
                provider_type="gtfs_realtime",
                is_available=available,
                is_configured=configured,
                credentials_present=has_creds,
                connectivity_status=status,
                last_successful_request=latest_verified,
                last_failed_request=self._last_failed_request,
                last_observation_time=latest_verified or self._last_observation_time,
                last_response_latency_ms=avg_latency,
                consecutive_failure_count=max_failures,
                is_rate_limited=("rate_limited" in {s.connectivity_status for s in statuses}),
                supported_attributes=[
                    "trip_updates_delay",
                    "trip_cancellations",
                    "service_alerts",
                    "vehicle_positions",
                ],
                supported_geographic_coverage=", ".join(s.geographic_coverage for s in statuses[:3]) or "configured_feed_boundary",
                provenance_source="provider_live" if latest_verified else "unknown",
                supported_modes=["bus", "train", "metro"],
                status_notice=notice,
                status_reason=reason,
            )

        if self._ssrf_blocked:
            notice = "BLOCKED — GTFS feed endpoint failed SSRF security validation."
            reason = self._last_status_reason or "Private or unapproved network target."
        elif not configured:
            notice = "BLOCKED — authorized GTFS Realtime feed unavailable."
            reason = "No authorized regional transit GTFS-RT endpoint configured in environment."
        elif status == "degraded":
            notice = f"DEGRADED — GTFS feed experienced {self._consecutive_failure_count} consecutive network errors."
            reason = self._last_status_reason or "Network connection errors."
        elif not self._last_successful_request:
            notice = "Configured — awaiting initial live connection verification."
            reason = f"Feed endpoint configured; awaiting initial response verification from {sanitize_feed_url(self._feed_url)}."
        else:
            notice = "Connected to authorized GTFS Realtime transit feed."
            reason = f"Active feed endpoint: {sanitize_feed_url(self._feed_url)}"

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
            provenance_source="provider_live" if self._last_successful_request else "unknown",
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
        Fetches and normalizes trip updates, service alerts, and vehicle telemetry from
        authorized transit feeds using M3.9.1 IP-pinned SSRF transport.
        Fails closed when unconfigured or unauthorized; never fabricates live transit data.
        """
        if self._has_active_registry_mode():
            start_t = time.perf_counter()
            events = await self.registry.poll_all_enabled_feeds(force=False)
            latency_ms = (time.perf_counter() - start_t) * 1000.0
            statuses = self._enabled_registry_statuses()
            if any(s.connectivity_status == "available" for s in statuses):
                self._record_success(latency_ms)
            elif any(s.last_error_classification for s in statuses):
                first_err = next((s.last_error_classification for s in statuses if s.last_error_classification), "UPSTREAM_ERROR")
                self._record_failure(0, first_err)
            if modes:
                mode_set = set(modes)
                events = [e for e in events if not e.affected_modes or any(m in mode_set for m in e.affected_modes)]
            return events

        if not self.is_available():
            logger.debug(
                "GTFSRealtimeProvider: fetch skipped — authorized feed unavailable or unconfigured."
            )
            return []

        auth_header = ("Authorization", f"Bearer {self._api_key}") if self._api_key else None

        try:
            assert self._feed_url is not None
            result = await self._direct_client.fetch_feed(
                feed_id="gtfs_direct",
                feed_url=self._feed_url,
                auth_header=auth_header,
                allow_http=self._allow_http,
            )

            if result.status_code == 200:
                if not result.content:
                    self._record_failure(200, "Empty payload received from GTFS feed")
                    return []

                try:
                    events = self.decode_and_parse_feed(
                        result.content, content_type=result.content_type, raise_on_error=True
                    )
                except ValueError as parse_err:
                    self._record_failure(200, f"Malformed feed payload: {parse_err}")
                    return []

                self._record_success(result.latency_ms)
                if modes:
                    mode_set = set(modes)
                    events = [e for e in events if not e.affected_modes or any(m in mode_set for m in e.affected_modes)]
                return events

            err_reason = result.headers.get("x-error-type") if result.status_code == 0 else None
            self._record_failure(result.status_code, err_reason or f"HTTP {result.status_code}")
            return []
        except (GTFSFeedSecurityError, GTFSFeedPayloadTooLargeError) as sec_err:
            self._record_failure(0, str(sec_err))
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

    def decode_and_parse_feed(
        self,
        raw_bytes: bytes,
        content_type: str = "",
        raise_on_error: bool = False,
    ) -> list[DisruptionEvent]:
        """
        Decodes raw bytes from GTFS Realtime feed into standardized disruption events.
        Seamlessly handles:
        1. JSON-encoded GTFS-RT (application/json or payloads starting with '{' or '[')
        2. Binary Protocol Buffers (application/x-protobuf, octet-stream, or binary payloads)
        """
        if not raw_bytes:
            if raise_on_error:
                raise ValueError("Empty payload received from GTFS feed")
            return []

        stripped = raw_bytes.strip()
        is_json = (
            "json" in content_type.lower()
            or (len(stripped) > 0 and stripped[:1] in (b"{", b"["))
        )

        if is_json:
            try:
                payload = json.loads(raw_bytes.decode("utf-8"))
            except Exception as json_err:
                logger.warning(f"Failed to decode GTFS Realtime JSON: {json_err}")
                if raise_on_error:
                    raise ValueError(f"Corrupt GTFS Realtime JSON: {json_err}") from json_err
                return []

            if isinstance(payload, dict):
                if is_iudx_payload(payload):
                    return self.parse_gtfs_payload(normalize_iudx_payload(payload))
                if "header" not in payload and "entity" not in payload:
                    if raise_on_error:
                        raise ValueError("Invalid GTFS Realtime JSON: missing header and entity")
                    return []
                return self.parse_gtfs_payload(payload)
            elif isinstance(payload, list):
                if is_iudx_payload(payload):
                    return self.parse_gtfs_payload(normalize_iudx_payload(payload))
                return self.parse_gtfs_payload({"header": {}, "entity": payload})
            else:
                logger.warning("GTFS Realtime JSON payload is neither object nor array.")
                if raise_on_error:
                    raise ValueError("GTFS Realtime JSON payload is neither object nor array.")
                return []

        # Attempt Protocol Buffers decoding
        try:
            feed_dict = decode_gtfs_feed(raw_bytes)
        except Exception as pb_err:
            logger.warning(f"Failed to decode GTFS Realtime Protobuf payload: {pb_err}")
            if raise_on_error:
                raise ValueError(f"Corrupt GTFS Realtime Protobuf: {pb_err}") from pb_err
            return []

        if not feed_dict.get("header") and not feed_dict.get("entity"):
            if raise_on_error:
                raise ValueError("Invalid GTFS Realtime Protobuf: missing header and entity")
            return []

        return self.parse_gtfs_payload(feed_dict)

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

        cause_raw = alert.get("cause", "UNKNOWN_CAUSE")
        if isinstance(cause_raw, int):
            cause = CAUSE_MAP.get(cause_raw, "UNKNOWN_CAUSE")
        else:
            cause = str(cause_raw)

        effect_raw = alert.get("effect", "UNKNOWN_EFFECT")
        if isinstance(effect_raw, int):
            effect = EFFECT_MAP.get(effect_raw, "UNKNOWN_EFFECT")
        else:
            effect = str(effect_raw)

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

        # Extract informed entities (routes, stops, trips, agencies, route_types, directions)
        informed = alert.get("informed_entity") or alert.get("informedEntity") or []
        route_ids: list[str] = []
        stop_ids: list[str] = []
        trip_ids: list[str] = []
        agency_ids: list[str] = []
        route_types: list[int] = []
        direction_ids: list[int] = []
        if isinstance(informed, list):
            for inf in informed:
                if not isinstance(inf, dict):
                    continue
                if inf.get("route_id") or inf.get("routeId"):
                    route_ids.append(str(inf.get("route_id") or inf.get("routeId")))
                if inf.get("stop_id") or inf.get("stopId"):
                    stop_ids.append(str(inf.get("stop_id") or inf.get("stopId")))
                if inf.get("agency_id") or inf.get("agencyId"):
                    agency_ids.append(str(inf.get("agency_id") or inf.get("agencyId")))
                if inf.get("route_type") is not None:
                    try:
                        route_types.append(int(inf["route_type"]))
                    except (TypeError, ValueError):
                        pass
                if inf.get("direction_id") is not None:
                    try:
                        direction_ids.append(int(inf["direction_id"]))
                    except (TypeError, ValueError):
                        pass
                trip_obj = inf.get("trip")
                if isinstance(trip_obj, dict):
                    if trip_obj.get("trip_id") or trip_obj.get("tripId"):
                        trip_ids.append(str(trip_obj.get("trip_id") or trip_obj.get("tripId")))
                    if trip_obj.get("route_id") or trip_obj.get("routeId"):
                        route_ids.append(str(trip_obj.get("route_id") or trip_obj.get("routeId")))
                    if trip_obj.get("direction_id") is not None:
                        try:
                            direction_ids.append(int(trip_obj["direction_id"]))
                        except (TypeError, ValueError):
                            pass
                if inf.get("trip_id") or inf.get("tripId"):
                    trip_ids.append(str(inf.get("trip_id") or inf.get("tripId")))

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
            route_ids=sorted(set(route_ids)),
            stop_ids=sorted(set(stop_ids)),
            trip_ids=sorted(set(trip_ids)),
            correlation_metadata={
                **({"agencyIds": sorted(set(agency_ids))} if agency_ids else {}),
                **({"routeTypes": sorted(set(route_types))} if route_types else {}),
                **({"directionIds": sorted(set(direction_ids))} if direction_ids else {}),
            },
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
        if sched_rel in ("CANCELED", 3):
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
                route_ids=[route_id] if route_id else [],
                trip_ids=[trip_id] if trip_id else [],
            )

        # Stop time updates
        stop_updates = tu.get("stop_time_update") or tu.get("stopTimeUpdate") or []
        max_delay_sec = 0
        stop_ids: list[str] = []
        if isinstance(stop_updates, list):
            for stu in stop_updates:
                sid = stu.get("stop_id") or stu.get("stopId")
                if sid:
                    stop_ids.append(str(sid))
                arr = stu.get("arrival", {})
                dep = stu.get("departure", {})
                d = arr.get("delay") or dep.get("delay")
                if isinstance(d, (int, float)) and d > max_delay_sec:
                    max_delay_sec = int(d)

        # Top-level delay field (GTFS-RT protobuf TripUpdate field 5)
        tu_delay = tu.get("delay")
        if isinstance(tu_delay, (int, float)) and int(tu_delay) > max_delay_sec:
            max_delay_sec = int(tu_delay)

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
            route_ids=[route_id] if route_id else [],
            stop_ids=list(set(stop_ids)),
            trip_ids=[trip_id] if trip_id else [],
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
                if (
                    math.isfinite(lat)
                    and math.isfinite(lng)
                    and -90.0 <= lat <= 90.0
                    and -180.0 <= lng <= 180.0
                    and not (abs(lat) < 1e-6 and abs(lng) < 1e-6)
                ):
                    coords_pt = CoordinatesSchema(lat=lat, lng=lng)
                else:
                    return None
            except (ValueError, TypeError):
                return None

        congestion_raw = veh.get("congestion_level") or veh.get("congestionLevel")
        congestion_level = (
            CONGESTION_LEVEL_MAP.get(congestion_raw, congestion_raw)
            if isinstance(congestion_raw, int)
            else congestion_raw
        )
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
            route_ids=[route_id] if route_id else [],
            trip_ids=[trip_id] if trip_id else [],
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
