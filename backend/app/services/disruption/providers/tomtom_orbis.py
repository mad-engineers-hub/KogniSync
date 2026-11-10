"""
backend/app/services/disruption/providers/tomtom_orbis.py

Production-oriented TomTom Orbis Traffic API v2 Adapter (Milestone M3.8).
Interacts with the documented Orbis Traffic Incidents endpoint:
GET https://api.tomtom.com/maps/orbis/traffic/incidents/details?apiVersion=2&bbox=minLon,minLat,maxLon,maxLat
Authenticates via 'TomTom-Api-Key' request header (never exposes keys in query strings or logs).
Validates GeoJSON geometries, extracts delay seconds where available without fabrication,
enforces TomTom's 10,000 km² bbox ceiling, and tracks provider reliability metrics.
"""
import math
import time
from datetime import datetime, timezone
from typing import Any, Sequence
import anyio
import httpx
from pydantic import BaseModel
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

TOMTOM_ORBIS_BASE_URL = "https://api.tomtom.com/maps/orbis/traffic/incidents/details"
DEFAULT_ATTRIBUTES_HEADER = (
    "incidents(type,geometry(type,coordinates),properties(id,iconCategory,magnitudeOfDelay,"
    "events(description,code),from,to,lengthInMeters,delayInSeconds,roadNumbers,timeValidity,"
    "probabilityOfOccurrence,numberOfReports,lastReportTime))"
)
MAX_BBOX_AREA_KM2 = 10000.0  # Documented TomTom Orbis maximum bbox area limit

ICON_CATEGORY_MAP: dict[int | str, DisruptionEventType] = {
    0: "unknown",
    1: "accident",
    2: "weather",
    3: "weather",
    4: "weather",
    5: "weather",
    6: "traffic_congestion",
    7: "road_closure",
    8: "road_construction",
    9: "transport_delay",
    10: "accident",
    11: "weather",
    14: "road_closure",
    # Orbis v2 string enum categories
    "unknown": "unknown",
    "accident": "accident",
    "fog": "weather",
    "dangerousConditions": "weather",
    "rain": "weather",
    "ice": "weather",
    "jam": "traffic_congestion",
    "laneClosed": "road_closure",
    "roadClosed": "road_closure",
    "roadWorks": "road_construction",
    "wind": "weather",
    "flooding": "weather",
    "brokenDownVehicle": "accident",
}

MAGNITUDE_MAP: dict[int | str, DisruptionSeverity] = {
    0: "low",
    1: "low",
    2: "moderate",
    3: "high",
    4: "critical",
    # Orbis v2 string enum magnitudes
    "minor": "low",
    "moderate": "moderate",
    "major": "high",
    "critical": "critical",
    "undefined": "moderate",
}


def sanitize_secret(secret: str | None) -> str:
    """Returns redacted indicator without leaking secret characters."""
    if not secret:
        return "<none>"
    return f"<configured:len={len(secret)}>"


def approx_bbox_area_km2(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> float:
    """Approximates surface area of a bounding box in square kilometers."""
    mid_lat = (min_lat + max_lat) / 2.0
    lat_dist_km = abs(max_lat - min_lat) * 110.574
    lon_dist_km = abs(max_lon - min_lon) * 111.320 * math.cos(math.radians(mid_lat))
    return lat_dist_km * lon_dist_km


def split_bounding_box(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    max_area_km2: float = MAX_BBOX_AREA_KM2,
    depth: int = 0,
    max_depth: int = 6,
) -> list[tuple[float, float, float, float]]:
    """
    Subdivides a bounding box recursively if it exceeds the maximum allowable area.
    Normalizes reversed coordinates, handles antimeridian crossing, limits recursion depth,
    and clamps subdivisions to a safe budget to avoid request storms.
    """
    # 1. Antimeridian crossing check (e.g. min_lon = 179.0, max_lon = -179.0)
    if min_lon > max_lon:
        if max_lon < 0 and min_lon > 0 and (180.0 - min_lon + max_lon + 180.0) < 180.0:
            box_east = (min_lon, min(min_lat, max_lat), 180.0, max(min_lat, max_lat))
            box_west = (-180.0, min(min_lat, max_lat), max_lon, max(min_lat, max_lat))
            return [box_east, box_west][: settings.TOMTOM_MAX_REQUESTS_PER_ASSESSMENT]
        else:
            # Reversed coordinates: normalize
            min_lon, max_lon = max_lon, min_lon

    if min_lat > max_lat:
        min_lat, max_lat = max_lat, min_lat

    area = approx_bbox_area_km2(min_lon, min_lat, max_lon, max_lat)
    if area <= max_area_km2 or depth >= max_depth:
        return [(min_lon, min_lat, max_lon, max_lat)]

    # Split along the longer dimension
    lat_span = abs(max_lat - min_lat)
    lon_span = abs(max_lon - min_lon)

    if lat_span >= lon_span:
        mid_lat = (min_lat + max_lat) / 2.0
        box1 = (min_lon, min_lat, max_lon, mid_lat)
        box2 = (min_lon, mid_lat, max_lon, max_lat)
    else:
        mid_lon = (min_lon + max_lon) / 2.0
        box1 = (min_lon, min_lat, mid_lon, max_lat)
        box2 = (mid_lon, min_lat, max_lon, max_lat)

    subboxes: list[tuple[float, float, float, float]] = []
    for b in [box1, box2]:
        subboxes.extend(
            split_bounding_box(
                b[0], b[1], b[2], b[3], max_area_km2, depth=depth + 1, max_depth=max_depth
            )
        )
    return subboxes[: settings.TOMTOM_MAX_REQUESTS_PER_ASSESSMENT]


class TomTomOrbisTrafficProvider(DisruptionProvider):
    """
    Adapter for TomTom Orbis Traffic API v2 (incident details).
    Enforces header-based authentication, area bounds, schema normalization,
    exponential backoff, and attribute-level provenance.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        connect_timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ):
        self._api_key = api_key or settings.TOMTOM_API_KEY
        self._base_url = base_url or settings.TOMTOM_BASE_URL
        self._timeout_seconds = timeout_seconds or settings.TOMTOM_TIMEOUT_SECONDS
        self._connect_timeout_seconds = (
            connect_timeout_seconds or settings.TOMTOM_CONNECT_TIMEOUT_SECONDS
        )
        self._max_retries = max_retries if max_retries is not None else settings.TOMTOM_MAX_RETRIES

        # Operational metrics
        self._last_successful_request: str | None = None
        self._last_failed_request: str | None = None
        self._last_observation_time: str | None = None
        self._last_response_latency_ms: float | None = None
        self._consecutive_failure_count: int = 0
        self._is_rate_limited: bool = False
        self._rate_limit_reset_time: float | None = None
        self._auth_blocked: bool = False
        self._last_status_reason: str = ""

    @property
    def name(self) -> str:
        return "tomtom_orbis_traffic"

    @property
    def display_name(self) -> str:
        return "TomTom Orbis Traffic Incidents v2"

    def is_configured(self) -> bool:
        return bool(self._api_key and len(self._api_key.strip()) > 8)

    def is_available(self) -> bool:
        """Returns True only when configured, enabled, unblocked, and not actively rate-limited."""
        if not settings.TOMTOM_TRAFFIC_ENABLED:
            return False
        if not self.is_configured():
            return False
        if self._auth_blocked:
            return False
        if self._is_rate_limited:
            if self._rate_limit_reset_time and time.time() < self._rate_limit_reset_time:
                return False
            # Rate limit cooldown passed
            self._is_rate_limited = False
        return True

    def get_connectivity_status(self) -> ProviderConnectivityStatus:
        if not settings.TOMTOM_TRAFFIC_ENABLED:
            return "unconfigured"
        if not self.is_configured():
            return "unconfigured"
        if self._auth_blocked:
            return "blocked"
        if self._is_rate_limited:
            return "rate_limited"
        if self._consecutive_failure_count >= 3:
            return "degraded"
        if self._last_successful_request:
            return "available"
        return "unknown"

    def get_capabilities(self) -> DisruptionProviderCapability:
        configured = self.is_configured()
        available = self.is_available()
        status = self.get_connectivity_status()

        if not configured:
            notice = "BLOCKED — credentials unavailable (commercial TOMTOM_API_KEY required). Simulation active."
            reason = "No valid TomTom API key in environment configuration."
        elif self._auth_blocked:
            notice = "BLOCKED — TomTom authentication failed (HTTP 401/403). Check API key validity."
            reason = self._last_status_reason or "Authentication rejected by TomTom API."
        elif self._is_rate_limited:
            notice = "DEGRADED — TomTom Orbis rate limit exceeded (HTTP 429). Backing off."
            reason = self._last_status_reason or "HTTP 429 Rate Limit."
        elif status == "degraded":
            notice = f"DEGRADED — provider experienced {self._consecutive_failure_count} consecutive network failures."
            reason = self._last_status_reason or "Consecutive request failures."
        elif not self._last_successful_request:
            notice = "Configured — awaiting initial live connection verification."
            reason = "API key configured; ready for initial live incident verification."
        else:
            notice = "Connected to TomTom Orbis Traffic API v2 (live road incidents)."
            reason = "Operational with valid credentials and reachable endpoints."

        return DisruptionProviderCapability(
            name=self.name,
            display_name=self.display_name,
            provider_type="traffic_incidents",
            is_available=available,
            is_configured=configured,
            credentials_present=configured,
            connectivity_status=status,
            last_successful_request=self._last_successful_request,
            last_failed_request=self._last_failed_request,
            last_observation_time=self._last_observation_time,
            last_response_latency_ms=self._last_response_latency_ms,
            consecutive_failure_count=self._consecutive_failure_count,
            is_rate_limited=self._is_rate_limited,
            supported_attributes=[
                "incident_geometry_geojson",
                "road_numbers",
                "delay_seconds",
                "icon_category",
                "magnitude_of_delay",
                "validity_time",
                "from_to_descriptions",
            ],
            supported_geographic_coverage="global",
            provenance_source="provider_live" if self._last_successful_request else "unknown",
            supported_modes=["cab", "bus", "auto", "rapido"],
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
        Fetches live incidents from TomTom Orbis Traffic v2 within the specified bounding box.
        If credentials are not configured or request fails, returns empty list without raising
        unhandled exceptions or spoofing live state.
        """
        if not self.is_available():
            logger.debug(
                "TomTomOrbisTrafficProvider: fetch skipped — provider unavailable or unconfigured."
            )
            return []

        if not bbox:
            # When no bbox is provided, live incident querying cannot proceed safely (avoids full-world query)
            logger.debug(
                "TomTomOrbisTrafficProvider: fetch skipped — no bounding box supplied for corridor."
            )
            return []

        min_lon, min_lat, max_lon, max_lat = bbox
        # Validate coordinates
        if not (-180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0 and -90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0):
            logger.warning(f"TomTomOrbisTrafficProvider: Invalid coordinates in bbox {bbox}")
            return []

        # Split bbox if exceeding TomTom 10,000 km² limit
        subboxes = split_bounding_box(min_lon, min_lat, max_lon, max_lat, MAX_BBOX_AREA_KM2)
        all_events: list[DisruptionEvent] = []
        seen_incident_ids: set[str] = set()

        for b in subboxes:
            box_events = await self._fetch_box_with_retries(b)
            for ev in box_events:
                if ev.source_id and ev.source_id not in seen_incident_ids:
                    seen_incident_ids.add(ev.source_id)
                    all_events.append(ev)

        # Transport mode filter if supplied
        if modes:
            modes_set = set(modes)
            all_events = [e for e in all_events if any(m in modes_set for m in e.affected_modes)]

        return all_events

    async def _fetch_box_with_retries(
        self, bbox: tuple[float, float, float, float]
    ) -> list[DisruptionEvent]:
        min_lon, min_lat, max_lon, max_lat = bbox
        bbox_str = f"{min_lon:.5f},{min_lat:.5f},{max_lon:.5f},{max_lat:.5f}"

        headers = {
            "TomTom-Api-Key": self._api_key or "",
            "Attributes": DEFAULT_ATTRIBUTES_HEADER,
            "Accept": "application/json",
        }
        params = {
            "apiVersion": "2",
            "bbox": bbox_str,
        }

        timeout = httpx.Timeout(self._timeout_seconds, connect=self._connect_timeout_seconds)

        for attempt in range(self._max_retries + 1):
            start_t = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.get(
                        self._base_url,
                        headers=headers,
                        params=params,
                    )
                latency_ms = (time.perf_counter() - start_t) * 1000.0

                if response.status_code == 200:
                    self._record_success(latency_ms)
                    return self._normalize_response(response.json())

                elif response.status_code in (401, 403):
                    self._auth_blocked = True
                    self._last_status_reason = f"Authentication error HTTP {response.status_code}"
                    self._record_failure(response.status_code, "Authentication rejected")
                    logger.warning("TomTom Orbis API: Authentication rejected. Failing closed.")
                    return []

                elif response.status_code == 429:
                    self._is_rate_limited = True
                    retry_after_hdr = response.headers.get("Retry-After")
                    delay_s = int(retry_after_hdr) if retry_after_hdr and retry_after_hdr.isdigit() else 30
                    self._rate_limit_reset_time = time.time() + min(delay_s, 120)
                    self._last_status_reason = f"HTTP 429 Rate limited (retry after {delay_s}s)"
                    self._record_failure(429, "Rate limit exceeded")
                    logger.warning(f"TomTom Orbis API: Rate limit exceeded. Backoff {delay_s}s.")
                    return []

                elif response.status_code >= 500:
                    self._last_status_reason = f"Server error HTTP {response.status_code}"
                    self._record_failure(response.status_code, "Server error")
                    if attempt < self._max_retries:
                        backoff = 0.5 * (2 ** attempt)
                        logger.warning(
                            f"TomTom Orbis API returned {response.status_code}. Retrying in {backoff}s..."
                        )
                        await anyio.sleep(backoff)
                        continue
                    return []

                else:
                    self._last_status_reason = f"HTTP {response.status_code}"
                    self._record_failure(response.status_code, "Client error")
                    logger.warning(
                        f"TomTom Orbis API: Unexpected HTTP {response.status_code}"
                    )
                    return []

            except httpx.ConnectTimeout:
                self._record_failure(0, "Connect timeout")
                self._last_status_reason = "Connect timeout"
                if attempt < self._max_retries:
                    await anyio.sleep(0.5)
                    continue
                return []
            except httpx.ReadTimeout:
                self._record_failure(0, "Read timeout")
                self._last_status_reason = "Read timeout"
                if attempt < self._max_retries:
                    await anyio.sleep(0.5)
                    continue
                return []
            except httpx.RequestError as req_err:
                # Sanitized error logging
                self._record_failure(0, "Network error")
                self._last_status_reason = "Network connection error"
                logger.warning(f"TomTom Orbis API network error: {type(req_err).__name__}")
                return []
            except Exception as e:
                self._record_failure(0, "Unexpected exception")
                self._last_status_reason = "Unexpected error"
                logger.error(f"TomTom Orbis API unexpected failure: {type(e).__name__}")
                return []

        return []

    def _record_success(self, latency_ms: float) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        self._last_successful_request = now_iso
        self._last_observation_time = now_iso
        self._last_response_latency_ms = round(latency_ms, 1)
        self._consecutive_failure_count = 0
        self._is_rate_limited = False
        self._last_status_reason = "Operational"

    def _record_failure(self, code: int, reason: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        self._last_failed_request = now_iso
        self._consecutive_failure_count += 1
        self._last_status_reason = f"{reason} ({code})" if code else reason

    def _normalize_response(self, data: dict[str, Any]) -> list[DisruptionEvent]:
        """
        Parses TomTom Orbis v2 incident GeoJSON / collection into DisruptionEvents.
        Ensures strict geometry extraction, attribute-level provenance, and zero fabricated delay.
        """
        events: list[DisruptionEvent] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        # Orbis incident details returns a list or 'incidents' array
        raw_incidents = data.get("incidents", [])
        if not isinstance(raw_incidents, list):
            # Also check if top-level features array exists (GeoJSON FeatureCollection)
            raw_incidents = data.get("features", [])
            if not isinstance(raw_incidents, list):
                return []

        for item in raw_incidents:
            try:
                event = self._normalize_single_incident(item, now_iso)
                if event:
                    events.append(event)
            except Exception as err:
                logger.debug(f"Failed to normalize TomTom incident: {err}")
                continue

        return events

    def _normalize_single_incident(
        self, inc: dict[str, Any], observation_iso: str
    ) -> DisruptionEvent | None:
        props = inc.get("properties", inc)
        inc_id = str(props.get("id") or inc.get("id") or f"tt-{time.time_ns()}")
        geometry = inc.get("geometry", {})

        coords_pt: CoordinatesSchema | None = None
        radius_meters = 1000.0

        # Validate GeoJSON geometry
        geom_type = geometry.get("type", "")
        raw_coords = geometry.get("coordinates")

        if geom_type == "Point" and isinstance(raw_coords, (list, tuple)) and len(raw_coords) >= 2:
            lng, lat = float(raw_coords[0]), float(raw_coords[1])
            coords_pt = CoordinatesSchema(lat=lat, lng=lng)
        elif geom_type == "LineString" and isinstance(raw_coords, list) and len(raw_coords) > 0:
            # LineString midpoint as representative point
            mid_idx = len(raw_coords) // 2
            mid_pt = raw_coords[mid_idx]
            if isinstance(mid_pt, (list, tuple)) and len(mid_pt) >= 2:
                lng, lat = float(mid_pt[0]), float(mid_pt[1])
                coords_pt = CoordinatesSchema(lat=lat, lng=lng)
            # Estimate radius from length or polyline span
            length_m = props.get("lengthInMeters") or props.get("length")
            if isinstance(length_m, (int, float)) and length_m > 0:
                radius_meters = max(500.0, float(length_m) / 2.0)
        elif geom_type == "MultiLineString" and isinstance(raw_coords, list) and len(raw_coords) > 0:
            first_line = raw_coords[0]
            if isinstance(first_line, list) and len(first_line) > 0:
                pt = first_line[0]
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    coords_pt = CoordinatesSchema(lat=float(pt[1]), lng=float(pt[0]))

        if not coords_pt:
            # Do not fabricate coordinates if geometry is missing or malformed
            return None

        # Icon Category -> Event Type
        icon_category = props.get("iconCategory", 0)
        event_type = ICON_CATEGORY_MAP.get(icon_category, "traffic_congestion")

        # Magnitude of delay -> Severity
        magnitude = props.get("magnitudeOfDelay", 2)
        severity = MAGNITUDE_MAP.get(magnitude, "moderate")
        if event_type == "road_closure" and severity in ("low", "moderate"):
            severity = "high"

        # Descriptions
        events_list = props.get("events", [])
        desc_parts: list[str] = []
        if isinstance(events_list, list):
            for ev in events_list:
                d = ev.get("description")
                if d:
                    desc_parts.append(str(d))
        description = "; ".join(desc_parts) if desc_parts else "Live traffic incident reported by TomTom"

        from_loc = props.get("from", "")
        to_loc = props.get("to", "")
        road_numbers = props.get("roadNumbers", [])
        if not isinstance(road_numbers, list):
            road_numbers = [str(road_numbers)] if road_numbers else []

        road_str = ", ".join(road_numbers) if road_numbers else "Corridor"
        title = f"{road_str}: {event_type.replace('_', ' ').title()}"
        if from_loc and to_loc:
            title += f" between {from_loc} and {to_loc}"
        elif from_loc:
            title += f" near {from_loc}"

        # Delay handling: ONLY use actual delay seconds supplied by response
        delay_sec = props.get("delayInSeconds") or props.get("delay")
        if isinstance(delay_sec, (int, float)) and delay_sec > 0:
            estimated_delay_min = int(delay_sec) // 60
            delay_sec_val = int(delay_sec)
        else:
            estimated_delay_min = 0
            delay_sec_val = None

        # Timestamps
        start_time = props.get("startTime") or observation_iso
        end_time = props.get("endTime")

        return DisruptionEvent(
            id=f"tt-inc-{inc_id}",
            source="tomtom_orbis_v2",
            source_id=inc_id,
            event_type=event_type,
            severity=severity,
            status="active",
            title=title,
            description=description,
            affected_modes=["cab", "bus", "auto", "rapido"],
            point=coords_pt,
            radius_meters=radius_meters,
            valid_from=start_time,
            valid_until=end_time,
            observed_at=observation_iso,
            last_verified_at=observation_iso,
            fetched_at=observation_iso,
            provenance="provider_live",
            confidence=0.95,
            estimated_delay_minutes=estimated_delay_min,
            delay_seconds=delay_sec_val,
            road_numbers=road_numbers,
        )
