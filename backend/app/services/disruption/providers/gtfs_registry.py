"""
backend/app/services/disruption/providers/gtfs_registry.py

Configuration-driven GTFS Realtime & Transit Feed Registry & Ingestion Coordinator (Milestones M3.9 & M4.0).
Manages multi-feed onboarding, server-side secret resolution (`bearer_token`, `api_key_header`,
`api_key_query`), IUDX NGSI-LD adaptation, controlled polling cadence, entity validation,
state machine transitions, lifecycle tracking, deduplication, and sanitized diagnostics export.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import time
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.logging import logger
from app.services.disruption.freshness import freshness_engine
from app.services.disruption.providers.gtfs_feed_client import (
    GTFSFeedFetchResult,
    GTFSFeedSecurityError,
    SecureGTFSFeedClient,
    sanitize_feed_url,
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
    parse_timestamp_to_epoch,
)
from app.services.disruption.schemas import (
    DisruptionEvent,
    DisruptionEventType,
    DisruptionSeverity,
    FeedAuthorizationStatus,
    FeedAvailabilityTransition,
    FeedConnectivityStatus,
    FeedProviderFormat,
    GTFSFeedConfig,
    GTFSFeedStatus,
)
from app.services.journey.schemas import CoordinatesSchema

MAX_TRANSITION_HISTORY = 20
MAX_FUTURE_CLOCK_SKEW_SECONDS = 120


def _resolve_secret_from_env_or_settings(env_var: str | None) -> str | None:
    """
    Resolves secret credential strictly server-side from OS environment first,
    then Pydantic Settings (`.env`). Returns None cleanly if unconfigured.
    """
    if not env_var:
        return None
    val = os.environ.get(env_var)
    if val:
        return val
    settings_val = getattr(settings, env_var, None)
    if isinstance(settings_val, str) and settings_val.strip():
        return settings_val.strip()
    return None


class GTFSFeedRegistry:
    """
    Authoritative registry and ingestion manager for GTFS Realtime and IUDX transit feeds.
    Maintains truthful connectivity state machines, bounded polling cadence, validation
    telemetry, and lifecycle persistence for transit disruption events.
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
        self._last_poll_epoch: dict[str, float] = {}
        self._cached_events: dict[str, list[DisruptionEvent]] = {}

        if initial_configs is not None:
            for cfg in initial_configs:
                self.register_feed(cfg)
        else:
            self._load_environment_configs()

    def _resolve_feed_token(self, config: GTFSFeedConfig) -> str | None:
        """Resolves credentials for a feed without mutating configs or exposing secrets."""
        token = _resolve_secret_from_env_or_settings(config.auth_token_env_var)
        if not token and config.auth_token_env_var == "BMTC_IUDX_AUTH_TOKEN":
            token = _resolve_secret_from_env_or_settings("IUDX_AUTH_TOKEN")
        if not token and config.feed_id == "gtfs_primary":
            token = settings.GTFS_REALTIME_API_KEY
        return token

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
                auth_token_env_var="GTFS_REALTIME_API_KEY" if settings.GTFS_REALTIME_API_KEY else None,
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

        # C. Documented Indian agency onboarding presets (activate only when legitimate credentials exist)
        bmtc_token = _resolve_secret_from_env_or_settings("BMTC_IUDX_AUTH_TOKEN") or _resolve_secret_from_env_or_settings(
            "IUDX_AUTH_TOKEN"
        )
        delhi_token = _resolve_secret_from_env_or_settings("DELHI_OTD_API_KEY")

        if "bmtc_iudx_vehicle_positions" not in self._configs and not settings.GTFS_FEEDS_CONFIG_JSON:
            self.register_feed(
                GTFSFeedConfig(
                    feed_id="bmtc_iudx_vehicle_positions",
                    operator_name="BMTC",
                    display_name="BMTC Bengaluru Live Bus Telemetry (IUDX cOS)",
                    geographic_coverage="Bengaluru Metropolitan Area",
                    feed_url="https://rs.cos.iudx.org.in/ngsi-ld/v1/entities?id=8a9c53c2-7291-454e-b173-2d9bfe893eb1",
                    auth_type="api_key_header",
                    auth_header_name="token",
                    auth_token_env_var="BMTC_IUDX_AUTH_TOKEN",
                    provider_format="iudx_ngsi_ld",
                    entity_types=["vehicle_positions"],
                    polling_interval_seconds=30,
                    documentation_url="https://cos.iudx.org.in/",
                    enabled=bool(bmtc_token),
                )
            )

        if "delhi_otd_vehicle_positions" not in self._configs and not settings.GTFS_FEEDS_CONFIG_JSON:
            self.register_feed(
                GTFSFeedConfig(
                    feed_id="delhi_otd_vehicle_positions",
                    operator_name="Delhi OTD (DIMTS/DTC)",
                    display_name="Delhi Open Transit Data Real-Time Vehicle Positions",
                    geographic_coverage="Delhi NCR",
                    feed_url="https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb",
                    auth_type="api_key_query",
                    auth_query_param_name="key",
                    auth_token_env_var="DELHI_OTD_API_KEY",
                    provider_format="gtfs_rt",
                    entity_types=["vehicle_positions"],
                    polling_interval_seconds=30,
                    documentation_url="https://otd.delhi.gov.in/",
                    enabled=bool(delhi_token),
                )
            )

    def register_feed(self, config: GTFSFeedConfig) -> None:
        """Registers or updates a GTFS Realtime or IUDX feed definition."""
        self._configs[config.feed_id] = config
        self._consecutive_failures[config.feed_id] = 0
        self._consecutive_successes[config.feed_id] = 0
        if config.feed_id not in self._active_events:
            self._active_events[config.feed_id] = {}
            self._absence_tracker[config.feed_id] = {}

        auth_status, connectivity_status, notice, blocker_reason = self._evaluate_initial_status(config)

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
            auth_type=config.auth_type,
            provider_format=config.provider_format,
            polling_interval_seconds=config.polling_interval_seconds,
            documentation_url=config.documentation_url,
            live_blocker_reason=blocker_reason,
            status_notice=notice,
        )

    def _evaluate_initial_status(
        self, config: GTFSFeedConfig
    ) -> tuple[FeedAuthorizationStatus, FeedConnectivityStatus, str, str | None]:
        if not config.enabled:
            env_hint = config.auth_token_env_var or "GTFS_REALTIME_API_KEY"
            blocker = (
                f"Agency access credentials not present in '{env_hint}'; "
                f"{config.operator_name} feed disabled pending consumer authorization."
                if config.auth_type != "none"
                else f"Feed '{config.feed_id}' disabled in configuration."
            )
            return "pending_credentials", "disabled", f"Feed '{config.feed_id}' is intentionally disabled.", blocker

        if not config.feed_url or len(config.feed_url.strip()) <= 8:
            return (
                "unauthorized",
                "unconfigured",
                "No valid feed endpoint URL configured.",
                "Missing or malformed feed endpoint URL.",
            )

        if config.auth_type in ("bearer_token", "api_key_header", "api_key_query"):
            token = self._resolve_feed_token(config)
            if not token:
                env_hint = config.auth_token_env_var or "GTFS_REALTIME_API_KEY"
                notice = (
                    f"Awaiting credentials in environment variable '{env_hint}'. "
                    f"Feed access requires official authorization from {config.operator_name}."
                )
                return "pending_credentials", "unconfigured", notice, notice

        return (
            "authorized",
            "configured",
            f"Configured; awaiting initial response verification from {sanitize_feed_url(config.feed_url)}.",
            None,
        )

    def _record_transition(
        self, feed_id: str, new_status: FeedConnectivityStatus, reason: str
    ) -> None:
        status = self._statuses.get(feed_id)
        if not status:
            return
        if status.connectivity_status != new_status:
            transition = FeedAvailabilityTransition(
                timestamp=datetime.now(timezone.utc).isoformat(),
                from_status=status.connectivity_status,
                to_status=new_status,
                reason=reason[:240],
            )
            history = list(status.availability_transitions)
            history.append(transition)
            if len(history) > MAX_TRANSITION_HISTORY:
                history = history[-MAX_TRANSITION_HISTORY:]
            status.availability_transitions = history
            status.connectivity_status = new_status

    def _increment_rejection(self, status: GTFSFeedStatus, reason_key: str) -> None:
        status.rejected_event_count += 1
        reasons = dict(status.rejected_reasons)
        reasons[reason_key] = reasons.get(reason_key, 0) + 1
        status.rejected_reasons = reasons

    def get_feed_statuses(self) -> list[GTFSFeedStatus]:
        """Returns sanitized status snapshots for all registered feeds."""
        return list(self._statuses.values())

    def get_feed_status(self, feed_id: str) -> GTFSFeedStatus | None:
        return self._statuses.get(feed_id)

    def get_enabled_feed_ids(self) -> list[str]:
        return [fid for fid, cfg in self._configs.items() if cfg.enabled]

    async def poll_all_enabled_feeds(self, force: bool = False) -> list[DisruptionEvent]:
        """
        Polls all enabled authorized feeds while respecting per-feed polling intervals.
        When within polling interval cooldown (and force=False), reuses cached events
        after re-evaluating freshness rules so stale cached events are never exposed.
        """
        enabled_ids = self.get_enabled_feed_ids()
        if not enabled_ids:
            return []

        now_mono = time.monotonic()
        aggregated: list[DisruptionEvent] = []
        fetch_tasks: list[tuple[str, Any]] = []

        for fid in enabled_ids:
            cfg = self._configs[fid]
            last_poll = self._last_poll_epoch.get(fid)
            within_cooldown = (
                not force
                and last_poll is not None
                and (now_mono - last_poll) < max(1, cfg.polling_interval_seconds)
                and fid in self._cached_events
            )
            if within_cooldown:
                for ev in self._cached_events[fid]:
                    data_type = (
                        "vehicle_position"
                        if ev.event_type == "traffic_congestion"
                        else ("trip_update" if ev.event_type in ("transport_delay", "service_cancellation") else "service_alert")
                    )
                    report = freshness_engine.evaluate_event_freshness(ev, data_type=data_type)
                    if not report.is_expired and report.status != "stale":
                        aggregated.append(ev)
            else:
                fetch_tasks.append((fid, self.fetch_feed_events(fid)))

        if fetch_tasks:
            results = await asyncio.gather(*(t[1] for t in fetch_tasks), return_exceptions=True)
            for idx, res in enumerate(results):
                fid = fetch_tasks[idx][0]
                if isinstance(res, list):
                    aggregated.extend(res)
                else:
                    logger.warning(f"GTFSFeedRegistry: polling error on feed '{fid}': {res}")

        return aggregated

    async def fetch_feed_events(self, feed_id: str) -> list[DisruptionEvent]:
        """
        Fetches, decodes, validates, deduplicates, and manages lifecycle of events for a feed.
        Enforces IP-pinned SSRF protection and strictly never fabricates live transit data.
        """
        config = self._configs.get(feed_id)
        if not config:
            logger.warning(f"GTFSFeedRegistry: unknown feed_id '{feed_id}'")
            return []

        status = self._statuses[feed_id]

        if not config.enabled:
            self._record_transition(feed_id, "disabled", "Feed is disabled in configuration.")
            status.status_notice = "Feed is disabled in configuration."
            return []

        now_iso = datetime.now(timezone.utc).isoformat()
        status.last_attempted_fetch = now_iso
        status.connection_attempts += 1

        # Resolve auth credentials strictly server-side
        auth_header: tuple[str, str] | None = None
        auth_query_param: tuple[str, str] | None = None

        if config.auth_type in ("bearer_token", "api_key_header", "api_key_query"):
            token = self._resolve_feed_token(config)
            if not token:
                env_hint = config.auth_token_env_var or "GTFS_REALTIME_API_KEY"
                status.authorization_status = "pending_credentials"
                status.auth_failures += 1
                msg = f"Missing required credentials in '{env_hint}'."
                status.live_blocker_reason = msg
                status.status_notice = msg
                self._record_transition(feed_id, "unconfigured", msg)
                return []

            if config.auth_type == "bearer_token":
                auth_header = (config.auth_header_name or "Authorization", f"Bearer {token}")
            elif config.auth_type == "api_key_header":
                auth_header = (config.auth_header_name or "x-api-key", token)
            elif config.auth_type == "api_key_query":
                auth_query_param = (config.auth_query_param_name or "key", token)

        try:
            result: GTFSFeedFetchResult = await self.client.fetch_feed(
                feed_id=feed_id,
                feed_url=config.feed_url,
                auth_header=auth_header,
                auth_query_param=auth_query_param,
                allow_http=config.allow_http,
            )
        except GTFSFeedSecurityError as sec_err:
            status.retrieval_failures += 1
            status.last_error_classification = "SSRF_BLOCKED"
            status.live_blocker_reason = f"Security validation failed: {sec_err}"
            status.status_notice = f"BLOCKED — security validation failed: {sec_err}"
            self._consecutive_failures[feed_id] += 1
            status.consecutive_failure_count = self._consecutive_failures[feed_id]
            self._record_transition(feed_id, "blocked", status.status_notice)
            return []
        except Exception as ex:
            status.retrieval_failures += 1
            status.last_error_classification = type(ex).__name__
            status.status_notice = f"Network fetch error: {type(ex).__name__}"
            self._consecutive_failures[feed_id] += 1
            status.consecutive_failure_count = self._consecutive_failures[feed_id]
            target_state: FeedConnectivityStatus = (
                "degraded"
                if self._consecutive_failures[feed_id] >= settings.GTFS_CIRCUIT_BREAKER_FAILURES
                else "unknown"
            )
            self._record_transition(feed_id, target_state, status.status_notice)
            return []

        status.last_response_latency_ms = round(result.latency_ms, 1)

        # HTTP Status Handling
        if result.status_code in (401, 403):
            status.authorization_status = "unauthorized" if result.status_code == 401 else "forbidden"
            status.auth_failures += 1
            status.last_error_classification = f"HTTP_{result.status_code}"
            status.live_blocker_reason = f"Authorization rejected by {config.operator_name} (HTTP {result.status_code})."
            status.status_notice = f"BLOCKED — authorization failed (HTTP {result.status_code})."
            self._consecutive_failures[feed_id] += 1
            status.consecutive_failure_count = self._consecutive_failures[feed_id]
            self._record_transition(feed_id, "blocked", status.status_notice)
            return []

        if result.status_code == 429:
            status.retrieval_failures += 1
            status.last_error_classification = "HTTP_429_RATE_LIMITED"
            status.status_notice = "Publisher rate limit encountered. Requests backed off."
            self._consecutive_failures[feed_id] += 1
            status.consecutive_failure_count = self._consecutive_failures[feed_id]
            self._record_transition(feed_id, "rate_limited", status.status_notice)
            return []

        if result.status_code != 200:
            status.retrieval_failures += 1
            err_type = result.headers.get("x-error-type") if result.status_code == 0 else None
            status.last_error_classification = err_type or f"HTTP_{result.status_code}"
            status.status_notice = f"Upstream retrieval failed ({status.last_error_classification})."
            self._consecutive_failures[feed_id] += 1
            status.consecutive_failure_count = self._consecutive_failures[feed_id]
            if self._consecutive_failures[feed_id] >= settings.GTFS_CIRCUIT_BREAKER_FAILURES:
                self._record_transition(feed_id, "degraded", status.status_notice)
            return []

        raw_bytes = result.content
        if not raw_bytes:
            status.decode_failures += 1
            status.last_error_classification = "EMPTY_PAYLOAD"
            status.status_notice = "Upstream returned empty response payload."
            self._consecutive_failures[feed_id] += 1
            status.consecutive_failure_count = self._consecutive_failures[feed_id]
            return []

        try:
            feed_dict = self._decode_feed_payload(
                raw_bytes,
                result.content_type,
                provider_format=config.provider_format,
            )
        except Exception as parse_err:
            status.decode_failures += 1
            status.last_error_classification = "PARSE_ERROR"
            status.status_notice = f"Failed to decode transit feed payload: {parse_err}"
            self._consecutive_failures[feed_id] += 1
            status.consecutive_failure_count = self._consecutive_failures[feed_id]
            if self._consecutive_failures[feed_id] >= settings.GTFS_CIRCUIT_BREAKER_FAILURES:
                self._record_transition(feed_id, "degraded", status.status_notice)
            return []

        # Validate FeedHeader timestamp freshness
        header = feed_dict.get("header", {}) if isinstance(feed_dict, dict) else {}
        feed_ts = parse_timestamp_to_epoch(header.get("timestamp"))
        now_ts = int(time.time())

        if feed_ts is not None:
            status.last_feed_header_timestamp = feed_ts
            age = now_ts - feed_ts
            if age > settings.GTFS_MAX_ENTITY_AGE_SECONDS:
                status.stale_rejections += 1
                status.freshness_status = "stale"
                status.last_error_classification = "STALE_FEED_HEADER"
                status.status_notice = (
                    f"Feed header is stale ({age}s old > {settings.GTFS_MAX_ENTITY_AGE_SECONDS}s threshold)."
                )
                self._record_transition(feed_id, "stale", status.status_notice)
                logger.warning(f"GTFSFeedRegistry: feed '{feed_id}' is stale (header age {age}s).")
                return []
            if feed_ts - now_ts > MAX_FUTURE_CLOCK_SKEW_SECONDS:
                status.stale_rejections += 1
                status.freshness_status = "stale"
                status.last_error_classification = "FUTURE_CLOCK_SKEW"
                status.status_notice = "Feed header timestamp exceeds allowed future clock skew."
                self._record_transition(feed_id, "stale", status.status_notice)
                return []
            status.freshness_status = "aging" if age > (settings.GTFS_MAX_ENTITY_AGE_SECONDS // 2) else "fresh"
        else:
            status.freshness_status = "fresh"

        # Reset acceptance/rejection stats for current poll cycle
        status.accepted_event_count = 0
        status.rejected_event_count = 0
        status.rejected_reasons = {}

        entities = feed_dict.get("entity", []) if isinstance(feed_dict, dict) else []
        if not isinstance(entities, list):
            status.decode_failures += 1
            status.last_error_classification = "INVALID_ENTITY_LIST"
            status.status_notice = "Decoded feed 'entity' field is not a list."
            self._consecutive_failures[feed_id] += 1
            status.consecutive_failure_count = self._consecutive_failures[feed_id]
            return []

        events, counts = self._process_entities(
            feed_id=feed_id,
            config=config,
            status=status,
            entities=entities,
            observation_time=now_iso,
            now_ts=now_ts,
        )

        # Success transition ONLY after decoded and validated payload
        self._consecutive_failures[feed_id] = 0
        status.consecutive_failure_count = 0
        self._consecutive_successes[feed_id] += 1
        status.authorization_status = "authorized"
        status.last_successful_fetch = now_iso
        status.last_verified_timestamp = now_iso
        status.last_error_classification = None
        status.live_blocker_reason = None
        self._record_transition(feed_id, "available", "Verified live transit feed response.")

        status.entity_counts = counts
        status.status_notice = (
            f"Operational: verified {len(events)} active transit disruption(s) across "
            f"{counts.get('alerts', 0)} alert(s), {counts.get('trip_updates', 0)} trip update(s), "
            f"and {counts.get('vehicle_positions', 0)} vehicle telemetry record(s)."
        )

        self._last_poll_epoch[feed_id] = time.monotonic()
        self._cached_events[feed_id] = events
        return events

    def _decode_feed_payload(
        self,
        raw_bytes: bytes,
        content_type: str,
        provider_format: FeedProviderFormat = "auto",
    ) -> dict[str, Any]:
        """Decodes raw feed bytes via IUDX NGSI-LD adapter, GTFS-RT JSON, or pure-Python Protobuf."""
        stripped = raw_bytes.strip()
        is_json = (
            provider_format == "iudx_ngsi_ld"
            or "json" in content_type.lower()
            or (len(stripped) > 0 and stripped[:1] in (b"{", b"["))
        )

        if is_json:
            data = json.loads(raw_bytes.decode("utf-8"))
            if provider_format == "iudx_ngsi_ld" or (provider_format == "auto" and is_iudx_payload(data)):
                return normalize_iudx_payload(data)
            if isinstance(data, dict):
                if "header" not in data and "entity" not in data:
                    raise ValueError("Invalid GTFS-RT JSON: missing both 'header' and 'entity'")
                return data
            if isinstance(data, list):
                return {"header": {}, "entity": data}
            raise ValueError("Invalid JSON feed structure")

        decoded = decode_gtfs_feed(raw_bytes)
        if not decoded.get("header") and not decoded.get("entity"):
            raise ValueError("Invalid GTFS-RT Protobuf: missing FeedHeader and FeedEntity")
        return decoded

    def _is_entity_fresh(
        self,
        raw_ts: Any,
        max_age_seconds: int,
        now_ts: int,
        status: GTFSFeedStatus,
        reason_key: str,
    ) -> tuple[bool, int | None]:
        """Validates optional entity-level timestamp against clock skew and age thresholds."""
        ent_ts = parse_timestamp_to_epoch(raw_ts)
        if ent_ts is None:
            return True, None
        if ent_ts - now_ts > MAX_FUTURE_CLOCK_SKEW_SECONDS:
            status.stale_rejections += 1
            self._increment_rejection(status, "future_timestamp")
            return False, ent_ts
        if (now_ts - ent_ts) > max_age_seconds:
            status.stale_rejections += 1
            self._increment_rejection(status, reason_key)
            return False, ent_ts
        return True, ent_ts

    def _process_entities(
        self,
        feed_id: str,
        config: GTFSFeedConfig,
        status: GTFSFeedStatus,
        entities: list[dict[str, Any]],
        observation_time: str,
        now_ts: int,
    ) -> tuple[list[DisruptionEvent], dict[str, int]]:
        """
        Normalizes GTFS-RT / IUDX entities into DisruptionEvents with validation,
        lifecycle tracking, absence grace periods, and explicit accepted/rejected counts.
        """
        current_cycle_ids: set[str] = set()
        active_map = self._active_events[feed_id]
        absence_map = self._absence_tracker[feed_id]

        new_events: list[DisruptionEvent] = []
        counts: dict[str, int] = {"alerts": 0, "trip_updates": 0, "vehicle_positions": 0}
        seen_cycle_event_ids: set[str] = set()
        now_sec = time.time()

        for ent in entities:
            if not isinstance(ent, dict):
                self._increment_rejection(status, "malformed_entity")
                continue
            if ent.get("is_deleted"):
                continue

            try:
                ent_id = str(ent.get("id") or f"{feed_id}-{time.time_ns()}")
                if ent_id in current_cycle_ids:
                    self._increment_rejection(status, "duplicate_entity_id")
                    continue
                current_cycle_ids.add(ent_id)

                ev: DisruptionEvent | None = None
                if "alert" in ent:
                    counts["alerts"] += 1
                    ev = self._normalize_alert(feed_id, config, status, ent, ent_id, observation_time, now_ts)
                elif "trip_update" in ent or "tripUpdate" in ent:
                    counts["trip_updates"] += 1
                    ev = self._normalize_trip_update(feed_id, config, status, ent, ent_id, observation_time, now_ts)
                elif "vehicle" in ent:
                    counts["vehicle_positions"] += 1
                    ev = self._normalize_vehicle(feed_id, config, status, ent, ent_id, observation_time, now_ts)

                if ev and ev.id not in seen_cycle_event_ids:
                    seen_cycle_event_ids.add(ev.id)
                    active_map[ent_id] = ev
                    new_events.append(ev)
                    status.accepted_event_count += 1
                    if ent_id in absence_map:
                        del absence_map[ent_id]

            except Exception as e:
                self._increment_rejection(status, "normalization_error")
                logger.debug(f"GTFSFeedRegistry: error normalizing entity {ent.get('id')}: {e}")
                continue

        # Lifecycle Management: temporary absence grace period
        grace_period = settings.GTFS_ABSENCE_GRACE_PERIOD_SECONDS
        resolved_ids: list[str] = []

        for existing_id in list(active_map.keys()):
            if existing_id not in current_cycle_ids:
                if existing_id not in absence_map:
                    absence_map[existing_id] = now_sec
                    new_events.append(active_map[existing_id])
                else:
                    if (now_sec - absence_map[existing_id]) >= grace_period:
                        resolved_ids.append(existing_id)
                    else:
                        new_events.append(active_map[existing_id])

        for rid in resolved_ids:
            active_map[rid].status = "resolved"
            del active_map[rid]
            del absence_map[rid]

        return new_events, counts

    def _normalize_alert(
        self,
        feed_id: str,
        config: GTFSFeedConfig,
        status: GTFSFeedStatus,
        ent: dict[str, Any],
        entity_id: str,
        observation_time: str,
        now_ts: int,
    ) -> DisruptionEvent | None:
        alert = ent.get("alert", {})
        if not isinstance(alert, dict):
            self._increment_rejection(status, "invalid_alert_object")
            return None

        fresh_ok, ent_ts = self._is_entity_fresh(
            alert.get("timestamp") or ent.get("timestamp"),
            settings.GTFS_MAX_ENTITY_AGE_SECONDS,
            now_ts,
            status,
            "stale_alert_timestamp",
        )
        if not fresh_ok:
            return None

        active_periods = alert.get("active_period") or alert.get("activePeriod") or []
        start_iso = observation_time
        end_iso: str | None = None
        if isinstance(active_periods, list) and len(active_periods) > 0:
            # Reject alert if all defined active periods have already ended
            has_unexpired = False
            selected_period: dict[str, Any] | None = None
            for period in active_periods:
                if not isinstance(period, dict):
                    continue
                p_end = parse_timestamp_to_epoch(period.get("end"))
                if p_end is None or p_end >= now_ts:
                    has_unexpired = True
                    selected_period = period
                    break
            if not has_unexpired:
                self._increment_rejection(status, "expired_active_period")
                return None
            if selected_period:
                p_start = parse_timestamp_to_epoch(selected_period.get("start"))
                p_end = parse_timestamp_to_epoch(selected_period.get("end"))
                if p_start is not None:
                    start_iso = datetime.fromtimestamp(p_start, tz=timezone.utc).isoformat()
                if p_end is not None:
                    end_iso = datetime.fromtimestamp(p_end, tz=timezone.utc).isoformat()

        header_text = self._extract_text(alert.get("header_text") or alert.get("headerText"))
        desc_text = self._extract_text(alert.get("description_text") or alert.get("descriptionText"))

        cause_raw = alert.get("cause", "UNKNOWN_CAUSE")
        cause = CAUSE_MAP.get(cause_raw, "UNKNOWN_CAUSE") if isinstance(cause_raw, int) else str(cause_raw)

        effect_raw = alert.get("effect", "UNKNOWN_EFFECT")
        effect = EFFECT_MAP.get(effect_raw, "UNKNOWN_EFFECT") if isinstance(effect_raw, int) else str(effect_raw)

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

        informed = alert.get("informed_entity") or alert.get("informedEntity") or []
        route_ids: list[str] = []
        stop_ids: list[str] = []
        trip_ids: list[str] = []
        agency_ids: list[str] = []

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
                trip_obj = inf.get("trip")
                if isinstance(trip_obj, dict) and (trip_obj.get("trip_id") or trip_obj.get("tripId")):
                    trip_ids.append(str(trip_obj.get("trip_id") or trip_obj.get("tripId")))
                if isinstance(trip_obj, dict) and (trip_obj.get("route_id") or trip_obj.get("routeId")):
                    route_ids.append(str(trip_obj.get("route_id") or trip_obj.get("routeId")))
                if inf.get("trip_id") or inf.get("tripId"):
                    trip_ids.append(str(inf.get("trip_id") or inf.get("tripId")))

        obs_iso = (
            datetime.fromtimestamp(ent_ts, tz=timezone.utc).isoformat()
            if ent_ts is not None
            else observation_time
        )
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
            observed_at=obs_iso,
            last_verified_at=observation_time,
            fetched_at=observation_time,
            provenance="provider_live",
            confidence=0.95,
            estimated_delay_minutes=25 if severity == "critical" else 10,
            route_ids=sorted(set(route_ids)),
            stop_ids=sorted(set(stop_ids)),
            trip_ids=sorted(set(trip_ids)),
            corridor_name=config.geographic_coverage,
            correlation_metadata={
                "feedId": feed_id,
                "operatorName": config.operator_name,
                "providerFormat": config.provider_format,
                "cause": cause,
                "effect": effect,
                **({"agencyIds": sorted(set(agency_ids))} if agency_ids else {}),
            },
        )

    def _normalize_trip_update(
        self,
        feed_id: str,
        config: GTFSFeedConfig,
        status: GTFSFeedStatus,
        ent: dict[str, Any],
        entity_id: str,
        observation_time: str,
        now_ts: int,
    ) -> DisruptionEvent | None:
        tu = ent.get("trip_update") or ent.get("tripUpdate") or {}
        if not isinstance(tu, dict):
            self._increment_rejection(status, "invalid_trip_update_object")
            return None

        fresh_ok, ent_ts = self._is_entity_fresh(
            tu.get("timestamp") or ent.get("timestamp"),
            settings.GTFS_MAX_ENTITY_AGE_SECONDS,
            now_ts,
            status,
            "stale_trip_update_timestamp",
        )
        if not fresh_ok:
            return None

        trip = tu.get("trip", {}) if isinstance(tu.get("trip"), dict) else {}
        trip_id = str(trip.get("trip_id") or trip.get("tripId") or "")
        route_id = str(trip.get("route_id") or trip.get("routeId") or "")
        sched_raw = trip.get("schedule_relationship") or trip.get("scheduleRelationship") or "SCHEDULED"
        sched_rel = (
            SCHEDULE_RELATIONSHIP_MAP.get(sched_raw, "SCHEDULED")
            if isinstance(sched_raw, int)
            else str(sched_raw).upper()
        )

        raw_top_delay = tu.get("delay")
        max_delay_sec: int | None = int(raw_top_delay) if isinstance(raw_top_delay, (int, float)) else None
        stop_time_updates = tu.get("stop_time_update") or tu.get("stopTimeUpdate") or []
        stop_ids: list[str] = []
        skipped_stops: list[str] = []

        if isinstance(stop_time_updates, list):
            for stu in stop_time_updates:
                if not isinstance(stu, dict):
                    continue
                sid = stu.get("stop_id") or stu.get("stopId")
                if sid:
                    stop_ids.append(str(sid))
                stu_rel = str(stu.get("schedule_relationship") or stu.get("scheduleRelationship") or "").upper()
                if stu_rel == "SKIPPED" and sid:
                    skipped_stops.append(str(sid))
                arr = stu.get("arrival") if isinstance(stu.get("arrival"), dict) else {}
                dep = stu.get("departure") if isinstance(stu.get("departure"), dict) else {}
                for cand in (arr.get("delay"), dep.get("delay")):
                    if isinstance(cand, (int, float)) and not isinstance(cand, bool):
                        c_int = int(cand)
                        if max_delay_sec is None or c_int > max_delay_sec:
                            max_delay_sec = c_int

        delay_sec_val = max_delay_sec if max_delay_sec is not None else 0
        delay_minutes = max(0, round(delay_sec_val / 60))

        if sched_rel in ("CANCELED", "NO_SERVICE"):
            event_type: DisruptionEventType = "service_cancellation"
            severity: DisruptionSeverity = "critical"
            title = f"{config.operator_name} Trip Cancellation: Route {route_id or trip_id}"
            desc = f"Scheduled transit trip {trip_id} on route {route_id} was canceled by transit dispatch."
            est_delay = 45
        elif skipped_stops and delay_sec_val < settings.GTFS_MIN_DELAY_SECONDS:
            event_type = "station_disruption"
            severity = "high"
            title = f"{config.operator_name} Stop(s) Skipped: Route {route_id or trip_id}"
            desc = f"Live trip update indicates skipped stop(s): {', '.join(skipped_stops)}."
            est_delay = 15
        elif delay_sec_val >= settings.GTFS_MIN_DELAY_SECONDS:
            event_type = "transport_delay"
            severity = "critical" if delay_minutes >= 45 else ("high" if delay_minutes >= 20 else "moderate")
            title = f"{config.operator_name} Delay ({delay_minutes}m): Route {route_id or trip_id}"
            desc = f"Live trip update reports an accumulated transit delay of {delay_minutes} minutes."
            est_delay = delay_minutes
        else:
            # On-time or minor (< 5 min) schedule variation is normal telemetry, not a disruption
            return None

        obs_iso = (
            datetime.fromtimestamp(ent_ts, tz=timezone.utc).isoformat()
            if ent_ts is not None
            else observation_time
        )

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
            valid_from=obs_iso,
            valid_until=None,
            observed_at=obs_iso,
            last_verified_at=observation_time,
            fetched_at=observation_time,
            provenance="provider_live",
            confidence=0.98,
            estimated_delay_minutes=est_delay,
            delay_seconds=max_delay_sec,
            route_ids=[route_id] if route_id else [],
            stop_ids=sorted(set(stop_ids)),
            trip_ids=[trip_id] if trip_id else [],
            corridor_name=config.geographic_coverage,
            correlation_metadata={
                "feedId": feed_id,
                "operatorName": config.operator_name,
                "providerFormat": config.provider_format,
                "scheduleRelationship": sched_rel,
                **({"skippedStops": skipped_stops} if skipped_stops else {}),
            },
        )

    def _normalize_vehicle(
        self,
        feed_id: str,
        config: GTFSFeedConfig,
        status: GTFSFeedStatus,
        ent: dict[str, Any],
        entity_id: str,
        observation_time: str,
        now_ts: int,
    ) -> DisruptionEvent | None:
        veh = ent.get("vehicle", {})
        if not isinstance(veh, dict):
            self._increment_rejection(status, "invalid_vehicle_object")
            return None

        fresh_ok, ent_ts = self._is_entity_fresh(
            veh.get("timestamp") or ent.get("timestamp"),
            settings.GTFS_VEHICLE_MAX_AGE_SECONDS,
            now_ts,
            status,
            "stale_vehicle_timestamp",
        )
        if not fresh_ok:
            return None

        pos = veh.get("position", {}) if isinstance(veh.get("position"), dict) else {}
        raw_lat = pos.get("latitude")
        raw_lng = pos.get("longitude")
        if raw_lat is None or raw_lng is None:
            self._increment_rejection(status, "missing_coordinates")
            return None

        try:
            lat = float(raw_lat)
            lng = float(raw_lng)
        except (TypeError, ValueError):
            self._increment_rejection(status, "invalid_coordinates")
            return None

        if (
            not math.isfinite(lat)
            or not math.isfinite(lng)
            or not (-90.0 <= lat <= 90.0)
            or not (-180.0 <= lng <= 180.0)
            or (abs(lat) < 1e-6 and abs(lng) < 1e-6)
        ):
            self._increment_rejection(status, "invalid_coordinates")
            return None

        cong_raw = veh.get("congestion_level") or veh.get("congestionLevel") or "UNKNOWN_CONGESTION_LEVEL"
        congestion = (
            CONGESTION_LEVEL_MAP.get(cong_raw, "UNKNOWN_CONGESTION_LEVEL")
            if isinstance(cong_raw, int)
            else str(cong_raw).upper()
        )
        if congestion not in ("CONGESTION", "SEVERE_CONGESTION", "STOP_AND_GO"):
            # Normal running vehicle telemetry is counted in entity_counts without fabricating congestion
            return None

        trip = veh.get("trip", {}) if isinstance(veh.get("trip"), dict) else {}
        route_id = str(trip.get("route_id") or trip.get("routeId") or "")
        trip_id = str(trip.get("trip_id") or trip.get("tripId") or "")
        stop_id = str(veh.get("stop_id") or veh.get("stopId") or "")
        veh_desc = veh.get("vehicle") if isinstance(veh.get("vehicle"), dict) else {}

        severity: DisruptionSeverity = "critical" if congestion == "SEVERE_CONGESTION" else "high"
        title = f"{config.operator_name} Vehicle Congestion: Route {route_id or trip_id or entity_id}"
        desc = f"Live vehicle telemetry reports {congestion.replace('_', ' ').lower()} affecting transit corridor."

        obs_iso = (
            datetime.fromtimestamp(ent_ts, tz=timezone.utc).isoformat()
            if ent_ts is not None
            else observation_time
        )

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
            point=CoordinatesSchema(lat=round(lat, 6), lng=round(lng, 6)),
            radius_meters=1500.0,
            valid_from=obs_iso,
            valid_until=None,
            observed_at=obs_iso,
            last_verified_at=observation_time,
            fetched_at=observation_time,
            provenance="provider_live",
            confidence=0.92,
            estimated_delay_minutes=15 if severity == "critical" else 8,
            route_ids=[route_id] if route_id else [],
            stop_ids=[stop_id] if stop_id else [],
            trip_ids=[trip_id] if trip_id else [],
            corridor_name=config.geographic_coverage,
            correlation_metadata={
                "feedId": feed_id,
                "operatorName": config.operator_name,
                "providerFormat": config.provider_format,
                "congestionLevel": congestion,
                **({"speedMps": pos["speed"]} if isinstance(pos.get("speed"), (int, float)) else {}),
                **({"vehicleId": str(veh_desc["id"])} if veh_desc.get("id") else {}),
            },
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
