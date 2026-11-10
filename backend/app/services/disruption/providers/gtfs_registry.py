"""
backend/app/services/disruption/providers/gtfs_registry.py

Configuration-driven GTFS Realtime Feed Registry & Ingestion Coordinator (Milestone M3.9).
Manages multi-feed onboarding, server-side secret resolution, state machine transitions,
lifecycle tracking, entity deduplication, and sanitized diagnostics export.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Sequence

from app.core.config import settings
from app.core.logging import logger
from app.services.disruption.freshness import freshness_engine
from app.services.disruption.providers.gtfs_feed_client import (
    GTFSFeedFetchResult,
    GTFSFeedSecurityError,
    SecureGTFSFeedClient,
    sanitize_feed_url,
)
from app.services.disruption.providers.gtfs_protobuf import decode_gtfs_feed
from app.services.disruption.schemas import (
    DisruptionEvent,
    FeedAuthorizationStatus,
    FeedConnectivityStatus,
    GTFSFeedConfig,
    GTFSFeedStatus,
)
from app.services.journey.schemas import CoordinatesSchema, TransportMode


class GTFSFeedRegistry:
    """
    Authoritative registry and ingestion manager for GTFS Realtime feeds.
    Maintains truthful connectivity state machines and lifecycle persistence for transit events.
    """

    def __init__(
        self,
        client: SecureGTFSFeedClient | None = None,
        initial_configs: list[GTFSFeedConfig] | None = None,
    ):
        self.client = client or SecureGTFSFeedClient()
        self._configs: dict[str, GTFSFeedConfig] = {}
        self._statuses: dict[str, GTFSFeedStatus] = {}
        self._active_events: dict[str, dict[str, DisruptionEvent]] = {}  # feed_id -> {entity_id: event}
        self._absence_tracker: dict[str, dict[str, float]] = {}          # feed_id -> {entity_id: first_absent_ts}
        self._consecutive_failures: dict[str, int] = {}
        self._consecutive_successes: dict[str, int] = {}

        # 1. Register explicitly passed initial configs or load default templates
        if initial_configs:
            for cfg in initial_configs:
                self.register_feed(cfg)
        else:
            self._load_environment_configs()

    def _load_environment_configs(self) -> None:
        """Loads feed configurations from environment variables safely."""
        # A. Primary feed configured via GTFS_REALTIME_FEED_URL
        if settings.GTFS_REALTIME_FEED_URL:
            primary_cfg = GTFSFeedConfig(
                feed_id="gtfs_primary",
                operator_name="Configured Transit Operator",
                display_name="Primary GTFS Realtime Feed",
                geographic_coverage="Configured Corridor",
                feed_url=settings.GTFS_REALTIME_FEED_URL,
                auth_type="bearer_token" if settings.GTFS_REALTIME_API_KEY else "none",
                enabled=settings.GTFS_REALTIME_ENABLED,
                allow_http=settings.GTFS_REALTIME_ALLOW_HTTP,
            )
            self.register_feed(primary_cfg)

        # B. Multi-feed JSON configuration if provided
        if settings.GTFS_FEEDS_CONFIG_JSON:
            try:
                raw_json = json.loads(settings.GTFS_FEEDS_CONFIG_JSON)
                if isinstance(raw_json, list):
                    for item in raw_json:
                        if isinstance(item, dict):
                            cfg = GTFSFeedConfig.model_validate(item)
                            self.register_feed(cfg)
            except Exception as e:
                logger.error(f"Failed to parse GTFS_FEEDS_CONFIG_JSON: {e}")

        # C. Default official reference feed templates (Bengaluru & National)
        # Marked as pending_credentials or unconfigured until legitimate tokens/URLs are provided
        if not self._configs:
            bmtc_template = GTFSFeedConfig(
                feed_id="bmtc_iudx_alerts",
                operator_name="BMTC",
                display_name="Bengaluru Metropolitan Transport Corporation (IUDX)",
                geographic_coverage="Bengaluru Metropolitan Area",
                feed_url="https://opendata.benscl.com/gtfs-rt/alerts",
                auth_type="bearer_token",
                auth_header_name="Authorization",
                auth_token_env_var="BMTC_IUDX_AUTH_TOKEN",
                entity_types=["service_alerts", "trip_updates"],
                enabled=False,  # Unconfigured until credentials supplied
            )
            self.register_feed(bmtc_template)

    def register_feed(self, config: GTFSFeedConfig) -> None:
        """Registers or updates a GTFS Realtime feed definition."""
        self._configs[config.feed_id] = config
        self._consecutive_failures[config.feed_id] = 0
        self._consecutive_successes[config.feed_id] = 0
        if config.feed_id not in self._active_events:
            self._active_events[config.feed_id] = {}
            self._absence_tracker[config.feed_id] = {}

        # Determine initial authorization and connectivity statuses
        auth_status, connectivity_status, notice = self._evaluate_initial_status(config)

        self._statuses[config.feed_id] = GTFSFeedStatus(
            feed_id=config.feed_id,
            operator_name=config.operator_name,
            display_name=config.display_name,
            geographic_coverage=config.geographic_coverage,
            feed_url_sanitized=sanitize_feed_url(config.feed_url),
            entity_types=config.entity_types,
            enabled=config.enabled,
            authorization_status=auth_status,
            connectivity_status=connectivity_status,
            freshness_status="unknown",
            status_notice=notice,
        )

    def _evaluate_initial_status(
        self, config: GTFSFeedConfig
    ) -> tuple[FeedAuthorizationStatus, FeedConnectivityStatus, str]:
        if not config.enabled:
            return "pending_credentials", "disabled", f"Feed '{config.feed_id}' is intentionally disabled."

        if not config.feed_url or len(config.feed_url.strip()) <= 8:
            return "unauthorized", "unconfigured", "No valid feed endpoint URL configured."

        # Check authentication requirements
        if config.auth_type in ("bearer_token", "api_key_header", "api_key_query"):
            env_var = config.auth_token_env_var
            token = os.environ.get(env_var) if env_var else None
            # Also fall back to legacy GTFS_REALTIME_API_KEY for primary feed
            if not token and config.feed_id == "gtfs_primary":
                token = settings.GTFS_REALTIME_API_KEY

            if not token:
                notice = (
                    f"Awaiting credentials in environment variable '{env_var or 'GTFS_REALTIME_API_KEY'}'. "
                    f"Feed access requires official authorization from {config.operator_name}."
                )
                return "pending_credentials", "unconfigured", notice

        return "authorized", "configured", f"Configured; awaiting initial response verification from {sanitize_feed_url(config.feed_url)}."

    def get_feed_statuses(self) -> list[GTFSFeedStatus]:
        """Returns sanitized status snapshots for all registered feeds."""
        return list(self._statuses.values())

    def get_feed_status(self, feed_id: str) -> GTFSFeedStatus | None:
        return self._statuses.get(feed_id)

    async def fetch_feed_events(self, feed_id: str) -> list[DisruptionEvent]:
        """
        Fetches, parses, deduplicates, and manages the lifecycle of events for a specific feed.
        Updates feed connectivity status and operational diagnostics truthfully.
        """
        config = self._configs.get(feed_id)
        if not config:
            logger.warning(f"GTFSFeedRegistry: unknown feed_id '{feed_id}'")
            return []

        status = self._statuses[feed_id]

        if not config.enabled:
            status.connectivity_status = "disabled"
            status.status_notice = "Feed is disabled in configuration."
            return []

        # Resolve auth credentials strictly server-side
        auth_header: tuple[str, str] | None = None
        if config.auth_type == "bearer_token":
            token = (
                os.environ.get(config.auth_token_env_var)
                if config.auth_token_env_var
                else (settings.GTFS_REALTIME_API_KEY if config.feed_id == "gtfs_primary" else None)
            )
            if not token:
                status.authorization_status = "pending_credentials"
                status.connectivity_status = "unconfigured"
                status.status_notice = f"Missing authorization token in '{config.auth_token_env_var}'."
                return []
            auth_header = (config.auth_header_name or "Authorization", f"Bearer {token}")
        elif config.auth_type == "api_key_header":
            token = (
                os.environ.get(config.auth_token_env_var)
                if config.auth_token_env_var
                else (settings.GTFS_REALTIME_API_KEY if config.feed_id == "gtfs_primary" else None)
            )
            if not token:
                status.authorization_status = "pending_credentials"
                status.connectivity_status = "unconfigured"
                status.status_notice = f"Missing API key in '{config.auth_token_env_var}'."
                return []
            auth_header = (config.auth_header_name or "x-api-key", token)

        # Execute safe fetch
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            result: GTFSFeedFetchResult = await self.client.fetch_feed(
                feed_id=feed_id,
                feed_url=config.feed_url,
                auth_header=auth_header,
            )
        except GTFSFeedSecurityError as sec_err:
            status.connectivity_status = "blocked"
            status.last_error_classification = "SSRF_BLOCKED"
            status.status_notice = f"BLOCKED — security validation failed: {sec_err}"
            self._consecutive_failures[feed_id] += 1
            return []
        except Exception as ex:
            status.last_error_classification = type(ex).__name__
            status.connectivity_status = (
                "degraded" if self._consecutive_failures[feed_id] >= settings.GTFS_CIRCUIT_BREAKER_FAILURES else "unknown"
            )
            status.status_notice = f"Network fetch error: {type(ex).__name__}"
            self._consecutive_failures[feed_id] += 1
            return []

        status.last_response_latency_ms = result.latency_ms

        # Handle HTTP Status
        if result.status_code == 401 or result.status_code == 403:
            status.authorization_status = "unauthorized" if result.status_code == 401 else "forbidden"
            status.connectivity_status = "blocked"
            status.last_error_classification = f"HTTP_{result.status_code}"
            status.status_notice = f"BLOCKED — authorization failed (HTTP {result.status_code})."
            self._consecutive_failures[feed_id] += 1
            return []

        if result.status_code == 429:
            status.connectivity_status = "rate_limited"
            status.last_error_classification = "HTTP_429_RATE_LIMITED"
            status.status_notice = "Publisher rate limit encountered. Requests backed off."
            self._consecutive_failures[feed_id] += 1
            return []

        if result.status_code != 200:
            status.last_error_classification = f"HTTP_{result.status_code}"
            self._consecutive_failures[feed_id] += 1
            if self._consecutive_failures[feed_id] >= settings.GTFS_CIRCUIT_BREAKER_FAILURES:
                status.connectivity_status = "degraded"
            status.status_notice = f"Upstream error (HTTP {result.status_code})."
            return []

        # Parse payload
        raw_bytes = result.content
        if not raw_bytes:
            status.last_error_classification = "EMPTY_PAYLOAD"
            status.status_notice = "Upstream returned empty response payload."
            self._consecutive_failures[feed_id] += 1
            return []

        try:
            feed_dict = self._decode_feed_payload(raw_bytes, result.content_type)
        except Exception as parse_err:
            status.last_error_classification = "PARSE_ERROR"
            status.status_notice = f"Failed to parse GTFS-RT feed: {parse_err}"
            self._consecutive_failures[feed_id] += 1
            if self._consecutive_failures[feed_id] >= settings.GTFS_CIRCUIT_BREAKER_FAILURES:
                status.connectivity_status = "degraded"
            return []

        # Validate FeedHeader
        header = feed_dict.get("header", {})
        feed_ts = header.get("timestamp")
        now_ts = int(time.time())

        if isinstance(feed_ts, (int, float)):
            status.last_feed_header_timestamp = int(feed_ts)
            age = now_ts - int(feed_ts)
            if age > 600:  # 10 minutes maximum age
                status.freshness_status = "stale"
                status.connectivity_status = "stale"
                status.status_notice = f"Feed header is stale ({age}s old > 600s threshold)."
                logger.warning(f"GTFSFeedRegistry: feed '{feed_id}' is stale (header age {age}s).")
                return []
            elif age > 300:
                status.freshness_status = "aging"
            else:
                status.freshness_status = "fresh"
        else:
            status.freshness_status = "fresh"

        # Success transition
        self._consecutive_failures[feed_id] = 0
        self._consecutive_successes[feed_id] += 1
        status.connectivity_status = "available"
        status.last_successful_fetch = now_iso
        status.last_verified_timestamp = now_iso
        status.last_error_classification = None

        # Process and normalize entities
        entities = feed_dict.get("entity", [])
        events, counts = self._process_entities(
            feed_id=feed_id,
            config=config,
            entities=entities,
            observation_time=now_iso,
        )

        status.entity_counts = counts
        status.status_notice = (
            f"Operational: verified {len(events)} active transit events "
            f"({counts.get('alerts', 0)} alerts, {counts.get('trip_updates', 0)} delays, {counts.get('vehicle_positions', 0)} vehicles)."
        )

        return events

    def _decode_feed_payload(self, raw_bytes: bytes, content_type: str) -> dict[str, Any]:
        """Decodes raw feed bytes via pure-Python GTFS Protobuf decoder or JSON."""
        stripped = raw_bytes.strip()
        is_json = "json" in content_type.lower() or (len(stripped) > 0 and stripped[:1] in (b"{", b"["))

        if is_json:
            data = json.loads(raw_bytes.decode("utf-8"))
            if isinstance(data, dict):
                return data
            elif isinstance(data, list):
                return {"header": {}, "entity": data}
            raise ValueError("Invalid JSON feed structure")

        # Binary Protocol Buffers
        return decode_gtfs_feed(raw_bytes)

    def _process_entities(
        self,
        feed_id: str,
        config: GTFSFeedConfig,
        entities: list[dict[str, Any]],
        observation_time: str,
    ) -> tuple[list[DisruptionEvent], dict[str, int]]:
        """
        Normalizes GTFS-RT entities into DisruptionEvents with lifecycle tracking.
        Handles temporary absence grace periods and event resolution.
        """
        current_cycle_ids: set[str] = set()
        active_map = self._active_events[feed_id]
        absence_map = self._absence_tracker[feed_id]

        new_events: list[DisruptionEvent] = []
        counts: dict[str, int] = {"alerts": 0, "trip_updates": 0, "vehicle_positions": 0}

        now_sec = time.time()

        for ent in entities:
            try:
                ent_id = str(ent.get("id", f"{feed_id}-{time.time_ns()}"))
                current_cycle_ids.add(ent_id)

                # 1. Alert Entity
                if "alert" in ent:
                    counts["alerts"] += 1
                    ev = self._normalize_alert(feed_id, config, ent, ent_id, observation_time)
                    if ev:
                        active_map[ent_id] = ev
                        new_events.append(ev)
                        if ent_id in absence_map:
                            del absence_map[ent_id]

                # 2. Trip Update Entity
                elif "trip_update" in ent or "tripUpdate" in ent:
                    counts["trip_updates"] += 1
                    ev = self._normalize_trip_update(feed_id, config, ent, ent_id, observation_time)
                    if ev:
                        active_map[ent_id] = ev
                        new_events.append(ev)
                        if ent_id in absence_map:
                            del absence_map[ent_id]

                # 3. Vehicle Position Entity
                elif "vehicle" in ent:
                    counts["vehicle_positions"] += 1
                    ev = self._normalize_vehicle(feed_id, config, ent, ent_id, observation_time)
                    if ev:
                        active_map[ent_id] = ev
                        new_events.append(ev)
                        if ent_id in absence_map:
                            del absence_map[ent_id]

            except Exception as e:
                logger.debug(f"GTFSFeedRegistry: error normalizing entity {ent.get('id')}: {e}")
                continue

        # Lifecycle Management: Check absent entities
        grace_period = settings.GTFS_ABSENCE_GRACE_PERIOD_SECONDS
        resolved_ids: list[str] = []

        for existing_id in list(active_map.keys()):
            if existing_id not in current_cycle_ids:
                if existing_id not in absence_map:
                    # First time absent in this cycle: start grace timer
                    absence_map[existing_id] = now_sec
                    # Keep existing event active during grace period
                    new_events.append(active_map[existing_id])
                else:
                    first_absent = absence_map[existing_id]
                    if (now_sec - first_absent) >= grace_period:
                        # Grace period expired: mark event resolved
                        resolved_ids.append(existing_id)
                    else:
                        # Still within grace period: maintain active state
                        new_events.append(active_map[existing_id])

        for rid in resolved_ids:
            ev = active_map[rid]
            ev.status = "resolved"
            del active_map[rid]
            del absence_map[rid]

        return new_events, counts

    def _normalize_alert(
        self,
        feed_id: str,
        config: GTFSFeedConfig,
        ent: dict[str, Any],
        entity_id: str,
        observation_time: str,
    ) -> DisruptionEvent | None:
        alert = ent.get("alert", {})
        header_text = self._extract_text(alert.get("header_text") or alert.get("headerText"))
        desc_text = self._extract_text(alert.get("description_text") or alert.get("descriptionText"))

        cause = str(alert.get("cause", "UNKNOWN_CAUSE"))
        effect = str(alert.get("effect", "UNKNOWN_EFFECT"))

        # Map effect to DisruptionEventType and severity
        if effect in ("NO_SERVICE", "SIGNIFICANT_DELAYS"):
            event_type = "service_cancellation" if effect == "NO_SERVICE" else "transport_delay"
            severity = "critical"
        elif effect in ("REDUCED_SERVICE", "MODIFIED_SERVICE"):
            event_type = "transport_delay"
            severity = "high"
        elif effect in ("STOP_MOVED", "ADDITIONAL_SERVICE"):
            event_type = "station_disruption"
            severity = "moderate"
        else:
            event_type = "transport_delay"
            severity = "moderate"

        # Informed entities (route, stop, trip references)
        informed = alert.get("informed_entity") or alert.get("informedEntity") or []
        route_ids: list[str] = []
        stop_ids: list[str] = []
        trip_ids: list[str] = []

        if isinstance(informed, list):
            for inf in informed:
                if isinstance(inf, dict):
                    if inf.get("route_id") or inf.get("routeId"):
                        route_ids.append(str(inf.get("route_id") or inf.get("routeId")))
                    if inf.get("stop_id") or inf.get("stopId"):
                        stop_ids.append(str(inf.get("stop_id") or inf.get("stopId")))
                    if inf.get("trip_id") or inf.get("tripId"):
                        trip_ids.append(str(inf.get("trip_id") or inf.get("tripId")))

        active_periods = alert.get("active_period") or alert.get("activePeriod") or []
        start_iso = observation_time
        end_iso: str | None = None
        if isinstance(active_periods, list) and len(active_periods) > 0:
            first_p = active_periods[0]
            if first_p.get("start"):
                start_iso = datetime.fromtimestamp(int(first_p["start"]), tz=timezone.utc).isoformat()
            if first_p.get("end"):
                end_iso = datetime.fromtimestamp(int(first_p["end"]), tz=timezone.utc).isoformat()

        title = header_text or f"{config.operator_name} Service Alert: {effect.replace('_', ' ').title()}"
        description = desc_text or f"Cause: {cause}; Effect: {effect}"

        return DisruptionEvent(
            id=f"{feed_id}-alert-{entity_id}",
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
            observed_at=observation_time,
            last_verified_at=observation_time,
            fetched_at=observation_time,
            provenance="provider_live",
            confidence=0.95,
            estimated_delay_minutes=25 if severity == "critical" else 10,
            route_ids=list(set(route_ids)),
            stop_ids=list(set(stop_ids)),
            trip_ids=list(set(trip_ids)),
            corridor_name=config.geographic_coverage,
        )

    def _normalize_trip_update(
        self,
        feed_id: str,
        config: GTFSFeedConfig,
        ent: dict[str, Any],
        entity_id: str,
        observation_time: str,
    ) -> DisruptionEvent | None:
        tu = ent.get("trip_update") or ent.get("tripUpdate") or {}
        trip = tu.get("trip", {})
        trip_id = str(trip.get("trip_id") or trip.get("tripId") or "")
        route_id = str(trip.get("route_id") or trip.get("routeId") or "")
        sched_rel = str(trip.get("schedule_relationship") or trip.get("scheduleRelationship") or "SCHEDULED")

        # Determine delay from trip update or stop time updates
        delay_sec = tu.get("delay")
        stop_time_updates = tu.get("stop_time_update") or tu.get("stopTimeUpdate") or []
        stop_ids: list[str] = []

        if isinstance(stop_time_updates, list):
            for stu in stop_time_updates:
                if isinstance(stu, dict):
                    sid = stu.get("stop_id") or stu.get("stopId")
                    if sid:
                        stop_ids.append(str(sid))
                    if delay_sec is None:
                        arr = stu.get("arrival", {})
                        dep = stu.get("departure", {})
                        if arr.get("delay") is not None:
                            delay_sec = arr["delay"]
                        elif dep.get("delay") is not None:
                            delay_sec = dep["delay"]

        delay_minutes = max(0, round((delay_sec or 0) / 60))

        if sched_rel == "CANCELED":
            event_type = "service_cancellation"
            severity = "critical"
            title = f"{config.operator_name} Trip Cancellation: Route {route_id or trip_id}"
            desc = f"Scheduled transit trip {trip_id} on route {route_id} was cancelled by transit dispatch."
        elif delay_minutes >= 10:
            event_type = "transport_delay"
            severity = "high" if delay_minutes >= 30 else "moderate"
            title = f"{config.operator_name} Delay ({delay_minutes}m): Route {route_id or trip_id}"
            desc = f"Live trip update reports an accumulated transit delay of {delay_minutes} minutes."
        else:
            return None  # Minor delay (<10m) does not warrant journey disruption event

        return DisruptionEvent(
            id=f"{feed_id}-tu-{entity_id}",
            source="gtfs_realtime",
            source_id=entity_id,
            event_type=event_type,
            severity=severity,
            status="active",
            title=title,
            description=desc,
            affected_modes=["bus", "train", "metro"],
            point=None,
            radius_meters=2000.0,
            valid_from=observation_time,
            valid_until=None,
            observed_at=observation_time,
            last_verified_at=observation_time,
            fetched_at=observation_time,
            provenance="provider_live",
            confidence=0.98,
            estimated_delay_minutes=delay_minutes if sched_rel != "CANCELED" else 45,
            delay_seconds=delay_sec,
            route_ids=[route_id] if route_id else [],
            stop_ids=list(set(stop_ids)),
            trip_ids=[trip_id] if trip_id else [],
            corridor_name=config.geographic_coverage,
        )

    def _normalize_vehicle(
        self,
        feed_id: str,
        config: GTFSFeedConfig,
        ent: dict[str, Any],
        entity_id: str,
        observation_time: str,
    ) -> DisruptionEvent | None:
        veh = ent.get("vehicle", {})
        pos = veh.get("position", {})
        lat = pos.get("latitude")
        lng = pos.get("longitude")
        if lat is None or lng is None:
            return None

        congestion = veh.get("congestion_level") or veh.get("congestionLevel") or "UNKNOWN_CONGESTION_LEVEL"
        if congestion not in ("CONGESTION", "SEVERE_CONGESTION", "STOP_AND_GO"):
            return None  # Only convert anomalous congestion into disruption events

        trip = veh.get("trip", {})
        route_id = str(trip.get("route_id") or trip.get("routeId") or "")
        trip_id = str(trip.get("trip_id") or trip.get("tripId") or "")

        severity = "high" if congestion == "SEVERE_CONGESTION" else "moderate"
        title = f"{config.operator_name} Vehicle Congestion: Route {route_id or trip_id}"
        desc = f"Transit telemetry reports severe corridor congestion ({congestion}) affecting transit movement."

        return DisruptionEvent(
            id=f"{feed_id}-veh-{entity_id}",
            source="gtfs_realtime",
            source_id=entity_id,
            event_type="traffic_congestion",
            severity=severity,
            status="active",
            title=title,
            description=desc,
            affected_modes=["bus", "metro"],
            point=CoordinatesSchema(lat=round(float(lat), 6), lng=round(float(lng), 6)),
            radius_meters=1500.0,
            valid_from=observation_time,
            valid_until=None,
            observed_at=observation_time,
            last_verified_at=observation_time,
            fetched_at=observation_time,
            provenance="provider_live",
            confidence=0.90,
            estimated_delay_minutes=15 if severity == "high" else 8,
            route_ids=[route_id] if route_id else [],
            trip_ids=[trip_id] if trip_id else [],
            corridor_name=config.geographic_coverage,
        )

    def _extract_text(self, val: Any) -> str:
        """Safely extracts string from translated string structure or plain string."""
        if not val:
            return ""
        if isinstance(val, str):
            return val
        if isinstance(val, dict):
            trans = val.get("translation")
            if isinstance(trans, list) and len(trans) > 0:
                first = trans[0]
                if isinstance(first, dict):
                    return str(first.get("text", ""))
            if "text" in val:
                return str(val["text"])
        return str(val)


# Global singleton feed registry
gtfs_feed_registry = GTFSFeedRegistry()
