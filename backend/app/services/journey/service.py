"""
backend/app/services/journey/service.py

Authoritative JourneyOrchestrationService for KogniSync backend.
Coordinates request validation, hub resolution, multimodal corridor composition,
first/last mile integration, deterministic Pareto multi-objective optimization,
and explicit attribute-level data provenance & credibility tracking (Milestone M2.1).
"""
import asyncio
import inspect
from datetime import timedelta
from typing import Any, Callable
from app.core.logging import logger
from app.services.optimizer.schemas import (
    JourneyCandidateInput,
    OptimizationRequest,
    OptimizationWeightsInput,
)
from app.services.optimizer.service import JourneyOptimizerService, optimizer_service
from app.services.journey.schemas import (
    AIExplanationSchema,
    AttributeProvenanceSchema,
    BookingFeasibilitySchema,
    JourneyProvenanceSchema,
    JourneySchema,
    JourneySearchRequest,
    JourneySearchResponse,
    JourneySegmentSchema,
    LocationSchema,
    ProvenanceSourceType,
    RecommendationCategory,
    SegmentAvailabilitySchema,
    SegmentProvenanceSchema,
    TransportMode,
)
from app.services.journey.provider import (
    NormalizedTransportSegmentResponse,
    ProviderErrorCode,
    TransportProvider,
    TransportProviderError,
    TransportSegmentSearchRequest,
)
from app.services.journey.google_routes_adapter import GoogleRoutesTransportAdapter
from app.services.journey.hubs import (
    build_iso_date,
    estimate_corridor_distance_km,
    get_local_transit_operators,
    parse_target_arrival,
    resolve_hub_context,
    slugify,
)


def build_default_segment_provenance(
    provider: str,
    mode: str,
    attribute_overrides: dict[str, AttributeProvenanceSchema] | None = None,
) -> SegmentProvenanceSchema:
    """
    Constructs comprehensive attribute-level provenance for a journey segment.
    Explicitly distinguishes deterministic estimates from simulated availability and live data.
    """
    overrides = attribute_overrides or {}

    default_attrs: dict[str, AttributeProvenanceSchema] = {
        "fare": AttributeProvenanceSchema(
            source_type="deterministic_estimate",
            provider_name=f"KogniSync Corridor Fare Model ({provider})",
            is_estimate=True,
            notes="Calculated proportionally from corridor distance baseline; subject to live fare rules.",
        ),
        "duration": AttributeProvenanceSchema(
            source_type="deterministic_estimate",
            provider_name=f"KogniSync Transit Speed Model ({provider})",
            is_estimate=True,
            notes="Estimated from corridor distance, typical operating speeds, and connection buffers.",
        ),
        "distance": AttributeProvenanceSchema(
            source_type="deterministic_estimate",
            provider_name="KogniSync Geo-Engine",
            is_estimate=True,
            notes="Calculated from geographic coordinates and corridor network topology.",
        ),
        "departure_time": AttributeProvenanceSchema(
            source_type="deterministic_estimate",
            provider_name="KogniSync Timetable Synthesizer",
            is_estimate=True,
            notes="Estimated backward from arrival deadline; not a confirmed booking schedule.",
        ),
        "arrival_time": AttributeProvenanceSchema(
            source_type="deterministic_estimate",
            provider_name="KogniSync Timetable Synthesizer",
            is_estimate=True,
            notes="Estimated arrival anchored to user deadline; subject to real-world delays.",
        ),
        "carbon": AttributeProvenanceSchema(
            source_type="deterministic_estimate",
            provider_name="KogniSync Multi-Modal Emission Factors",
            is_estimate=True,
            notes="Calculated using mode-specific emission factors (kg CO2 / passenger-km).",
        ),
        "availability": AttributeProvenanceSchema(
            source_type="simulated",
            provider_name="KogniSync Demo Fleet Simulator",
            is_estimate=True,
            notes="Simulated capacity for demonstration; unverified live inventory.",
        ),
    }

    # Ensure aliases "departure" and "arrival" are also mapped for unified provenance access
    default_attrs["departure"] = default_attrs["departure_time"]
    default_attrs["arrival"] = default_attrs["arrival_time"]

    # Apply any attribute-level overrides (e.g. from live external provider)
    for attr_key, attr_prov in overrides.items():
        default_attrs[attr_key] = attr_prov
        if attr_key == "departure":
            default_attrs["departure_time"] = attr_prov
        elif attr_key == "departure_time":
            default_attrs["departure"] = attr_prov
        elif attr_key == "arrival":
            default_attrs["arrival_time"] = attr_prov
        elif attr_key == "arrival_time":
            default_attrs["arrival"] = attr_prov

    has_live = any(attr.source_type == "provider_live" for attr in default_attrs.values())
    all_live = all(attr.source_type == "provider_live" for attr in default_attrs.values())
    has_unknown = any(attr.source_type == "unknown" for attr in default_attrs.values())

    # Segment-level source type: never label entire leg as live if only partial attributes are live
    if all_live:
        seg_source: ProvenanceSourceType = "provider_live"
    elif has_unknown and not has_live:
        seg_source = "unknown"
    else:
        seg_source = "deterministic_estimate"

    return SegmentProvenanceSchema(
        source_type=seg_source,
        provider_name=provider,
        is_estimate=not all_live,
        has_live_provider=has_live,
        attributes=default_attrs,
    )


def build_journey_provenance(segments: list[JourneySegmentSchema]) -> JourneyProvenanceSchema:
    """Aggregates leg-level provenance into overall journey provenance and credibility summary."""
    has_live = any(s.provenance.has_live_provider for s in segments if s.provenance)
    has_simulated = any(
        s.provenance and any(a.source_type == "simulated" for a in s.provenance.attributes.values())
        for s in segments
    )
    has_unknown = any(
        s.provenance and any(a.source_type == "unknown" for a in s.provenance.attributes.values())
        for s in segments
    )

    if has_live and (has_simulated or not all(s.provenance and s.provenance.source_type == "provider_live" for s in segments)):
        overall = "mixed"
        summary = "Contains both provider-backed attributes and deterministic estimates. Availability is unverified."
    elif has_unknown and not has_live:
        overall = "unknown"
        summary = "Contains unverified attributes with unknown provenance. Live verification required."
    else:
        overall = "deterministic_estimate"
        summary = "Composed of deterministic estimates and simulated availability; real-world booking requires provider verification."

    # Strict invariant: A journey must never be represented as fully confirmed
    # when critical attributes remain estimated, simulated, or unknown.
    has_estimated_attributes = any(
        s.provenance and any(a.is_estimate or a.source_type != "provider_live" for a in s.provenance.attributes.values())
        for s in segments
    )
    all_segments_live = (
        bool(segments)
        and all(
            s.provenance is not None
            and s.provenance.source_type == "provider_live"
            and not s.provenance.is_estimate
            for s in segments
        )
    )
    is_fully_confirmed = all_segments_live and not has_estimated_attributes and not has_simulated and not has_unknown

    return JourneyProvenanceSchema(
        overall_source_type=overall,
        is_fully_confirmed=is_fully_confirmed,
        has_live_attributes=has_live,
        has_simulated_attributes=has_simulated,
        summary=summary,
    )


def calculate_calibrated_segment_carbon(
    mode: TransportMode,
    resolved_distance_km: float,
    baseline_distance_km: float,
    baseline_carbon_kg: float,
) -> float:
    """
    Computes mode-aware, calibrated carbon emissions for a journey segment (Milestone M2.5).
    - Pedestrian legs ('walk') emit 0.0 kg CO2.
    - Road vehicles ('cab', 'rapido', 'bus', 'auto'):
      Emissions scale proportionally with actual road distance driven:
      carbon = baseline_carbon * (resolved_distance / baseline_distance)
    - Dedicated transit corridors ('flight', 'train', 'metro'):
      Road network variations must NOT distort aviation takeoff/cruise fuel burn
      or electrified railway / metro grid models. Preserves calibrated corridor emissions.
    """
    if mode == "walk":
        return 0.0

    if mode in ("flight", "train", "metro"):
        return round(baseline_carbon_kg, 1)

    # Road transport modes
    if baseline_distance_km > 0 and resolved_distance_km > 0:
        return round(baseline_carbon_kg * (resolved_distance_km / baseline_distance_km), 1)

    return round(baseline_carbon_kg, 1)


class JourneyOrchestrationService:
    """Authoritative multimodal journey orchestration and data credibility service."""

    def __init__(
        self,
        optimizer: JourneyOptimizerService | None = None,
        provider_registry: dict[str, Callable] | None = None,
        transport_providers: list[TransportProvider] | None = None,
    ):
        self.optimizer = optimizer or optimizer_service
        self.legacy_provider_registry = provider_registry or {}
        if transport_providers is not None:
            self.transport_providers = transport_providers
        else:
            self.transport_providers = self._init_default_providers()

    def _init_default_providers(self) -> list[TransportProvider]:
        """Initializes default production transport provider adapters from settings."""
        providers: list[TransportProvider] = []
        try:
            from app.core.config import settings
            # 1. Google Routes Cloud API
            providers.append(
                GoogleRoutesTransportAdapter(
                    api_key=settings.GOOGLE_MAPS_API_KEY,
                    enabled=settings.GOOGLE_ROUTES_ENABLED,
                )
            )
            # 2. Valhalla OpenStreetMap Self-Hosted Local Engine
            from app.services.journey.valhalla_adapter import ValhallaTransportAdapter
            providers.append(
                ValhallaTransportAdapter(
                    base_url=settings.VALHALLA_BASE_URL,
                    timeout_seconds=settings.VALHALLA_TIMEOUT_SECONDS,
                    enabled=settings.VALHALLA_ENABLED,
                )
            )
        except Exception as e:
            logger.warning(f"Could not initialize default transport providers: {e}")
        return providers

    async def _query_legacy_provider(
        self,
        provider_key: str,
        context: dict[str, Any],
        provider_status: dict[str, str],
    ) -> dict[str, AttributeProvenanceSchema] | None:
        """
        Safely invokes registered legacy external provider callables with timeout and error boundaries.
        Preserves backwards compatibility with M2.1 test mock registries.
        """
        provider_fn = self.legacy_provider_registry.get(provider_key)
        if not provider_fn:
            return None

        try:
            if inspect.iscoroutinefunction(provider_fn):
                result = await asyncio.wait_for(provider_fn(context), timeout=3.0)
            else:
                result = provider_fn(context)

            if result is None or (isinstance(result, dict) and len(result) == 0):
                provider_status[provider_key] = "empty_fallback_deterministic"
                return None

            provider_status[provider_key] = "active_live"
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Transport provider '{provider_key}' timed out during journey search")
            provider_status[provider_key] = "timeout_fallback_deterministic"
            return None
        except Exception as e:
            logger.error(f"Transport provider '{provider_key}' encountered an error: {type(e).__name__}")
            provider_status[provider_key] = "error_fallback_deterministic"
            return None

    # Keep _query_provider as alias to _query_legacy_provider for existing callers
    _query_provider = _query_legacy_provider

    async def _query_transport_providers(
        self,
        request: TransportSegmentSearchRequest,
        provider_status: dict[str, str],
    ) -> tuple[dict[str, AttributeProvenanceSchema], dict[str, Any]]:
        """
        Queries registered TransportProvider adapters matching the segment mode.
        Returns attribute provenance overrides and normalized metric overrides (duration, distance).
        Safely catches TransportProviderError, applies error classification, and falls back cleanly.
        """
        overrides: dict[str, AttributeProvenanceSchema] = {}
        metric_overrides: dict[str, Any] = {}

        for provider in self.transport_providers:
            if request.mode not in provider.supported_modes:
                continue

            p_id = provider.provider_id
            if not provider.is_available():
                if p_id not in provider_status:
                    provider_status[p_id] = "unconfigured_fallback_deterministic"
                continue

            try:
                norm_res = await asyncio.wait_for(
                    provider.search_segment(request),
                    timeout=getattr(provider, "timeout_seconds", 3.0) + 0.5,
                )
                if norm_res and norm_res.attribute_provenance:
                    provider_status[p_id] = "active_live"
                    overrides.update(norm_res.attribute_provenance)
                    if norm_res.duration_minutes is not None:
                        metric_overrides["duration_minutes"] = norm_res.duration_minutes
                    if norm_res.distance_km is not None:
                        metric_overrides["distance_km"] = norm_res.distance_km
                    # First matching live provider completes the segment query
                    break
            except asyncio.TimeoutError:
                logger.warning(f"Transport provider '{p_id}' timed out during journey search")
                provider_status[p_id] = "timeout_fallback_deterministic"
            except TransportProviderError as tpe:
                logger.warning(f"Transport provider '{p_id}' error [{tpe.code.value}]: {tpe.message}")
                if tpe.code == ProviderErrorCode.AUTH_FAILURE:
                    provider_status[p_id] = "auth_failed_fallback_deterministic"
                elif tpe.code == ProviderErrorCode.RATE_LIMITED:
                    provider_status[p_id] = "rate_limited_fallback_deterministic"
                elif tpe.code == ProviderErrorCode.EMPTY_RESULT:
                    provider_status[p_id] = "empty_fallback_deterministic"
                elif tpe.code == ProviderErrorCode.MALFORMED_RESPONSE:
                    provider_status[p_id] = "malformed_fallback_deterministic"
                elif tpe.code == ProviderErrorCode.TIMEOUT:
                    provider_status[p_id] = "timeout_fallback_deterministic"
                elif tpe.code == ProviderErrorCode.UNSUPPORTED_MODE:
                    provider_status[p_id] = "unsupported_mode_fallback_deterministic"
                elif tpe.code == ProviderErrorCode.INVALID_REQUEST:
                    provider_status[p_id] = "invalid_request_fallback_deterministic"
                else:
                    provider_status[p_id] = "unavailable_fallback_deterministic"
            except Exception as e:
                logger.error(f"Unexpected error in transport provider '{p_id}': {type(e).__name__}")
                provider_status[p_id] = "error_fallback_deterministic"

        return overrides, metric_overrides

    async def _resolve_segment_data(
        self,
        origin_node: LocationSchema,
        dest_node: LocationSchema,
        mode: TransportMode,
        provider_name: str,
        default_duration: int,
        default_distance: float,
        provider_status: dict[str, str],
        departure_time: str | None = None,
        arrival_deadline: str | None = None,
    ) -> tuple[int, float, dict[str, AttributeProvenanceSchema]]:
        """
        Resolves duration, distance, and provenance overrides for a single segment.
        Tries legacy callable registry first, then registered TransportProvider adapters.
        """
        # 1. Check legacy registry
        if provider_name in self.legacy_provider_registry:
            legacy_res = await self._query_legacy_provider(
                provider_name,
                {"origin": origin_node.city, "destination": dest_node.city, "mode": mode},
                provider_status,
            )
            return default_duration, default_distance, legacy_res or {}

        # 2. Check registered TransportProvider adapters
        req = TransportSegmentSearchRequest(
            origin_title=origin_node.name,
            origin_city=origin_node.city,
            origin_lat=origin_node.coordinates.lat,
            origin_lng=origin_node.coordinates.lng,
            destination_title=dest_node.name,
            destination_city=dest_node.city,
            destination_lat=dest_node.coordinates.lat,
            destination_lng=dest_node.coordinates.lng,
            mode=mode,
            departure_time=departure_time,
            arrival_deadline=arrival_deadline,
        )

        overrides, metric_overrides = await self._query_transport_providers(req, provider_status)
        duration = metric_overrides.get("duration_minutes", default_duration)
        distance = metric_overrides.get("distance_km", default_distance)
        return duration, distance, overrides

    async def search_journeys(self, request: JourneySearchRequest) -> JourneySearchResponse:
        """
        Coordinates full multimodal journey search:
        1. Context and hub resolution (supporting cities, localities, and transport hubs).
        2. Dynamic corridor metric estimation (distance, duration, fares).
        3. Multimodal composition of 5 canonical archetypes (Flight, Train, Bus, Cab, Rapido, Metro, Walk).
        4. Hard constraint enforcement (budget cap, arrival deadline) via backend Pareto optimizer.
        5. Deterministic multi-objective scoring, Pareto ranking, and explicit data provenance tracking.
        """
        origin_str = request.origin.strip()
        dest_str = request.destination.strip()
        date_str = request.departure_date.strip()

        # 1. Resolve hubs for origin and destination
        origin_hubs = resolve_hub_context(origin_str, is_origin=True)
        dest_hubs = resolve_hub_context(dest_str, is_origin=False)

        route_distance_km = estimate_corridor_distance_km(origin_hubs.parent_city, dest_hubs.parent_city)
        route_slug = f"{slugify(origin_str)}-to-{slugify(dest_str)}"

        origin_ops = get_local_transit_operators(origin_hubs.parent_city)
        dest_ops = get_local_transit_operators(dest_hubs.parent_city)

        target_hour, target_min = parse_target_arrival(request.preferred_arrival_before)

        # Baseline corridor fares & transit speeds
        flight_duration_min = round(45 + (route_distance_km / 750.0) * 60)
        flight_price = round(1800 + route_distance_km * 2.3)

        train_vande_bharat_duration_min = round((route_distance_km / 80.0) * 60)
        train_vande_bharat_price = round(400 + route_distance_km * 2.7)

        train_cheapest_duration_min = round((route_distance_km / 65.0) * 60)
        train_cheapest_price = round(150 + route_distance_km * 1.6)

        train_greenest_duration_min = round((route_distance_km / 82.0) * 60)
        train_greenest_price = round(380 + route_distance_km * 2.5)

        train_comfort_duration_min = round((route_distance_km / 78.0) * 60)
        train_comfort_price = round(700 + route_distance_km * 3.6)

        provider_status: dict[str, str] = {
            "transport": "catalog_modelled",
            "optimizer": "authoritative_pareto",
            "maps": "coordinate_geometry",
        }
        for p in self.transport_providers:
            if not p.is_available():
                provider_status[p.provider_id] = "unconfigured_fallback_deterministic"

        # 5 Multimodal Archetype definitions
        archetypes = [
            # 1. FASTEST
            {
                "category": "fastest",
                "title": "SyncAir Multi-Modal Link (Air + Priority SyncCab)",
                "summary": f"Fastest door-to-door arrival connecting {origin_hubs.user_node.name} to {dest_hubs.user_node.name} via commercial air express and synchronized priority cabs.",
                "rank_reason": "Ranked #1 for Fastest. Minimizes total transit time with scheduled flight and express terminal cabs.",
                "first_mile": {
                    "mode": "cab",
                    "provider": origin_ops["cab"]["provider"],
                    "vehicle_name": origin_ops["cab"]["vehicle_name"],
                    "hub": origin_hubs.airport_hub,
                    "duration_min": 35,
                    "price": 650.0,
                    "distance_km": 34.0,
                    "carbon_kg": 5.2,
                    "comfort_score": 8.8,
                    "transfer_buffer_min": 50,
                },
                "main_transport": {
                    "mode": "flight",
                    "provider": "IndiGo Air Express",
                    "vehicle_name": "Airbus A321neo",
                    "vehicle_number": f"6E-{abs(route_distance_km * 3 + 120) % 900 + 100}",
                    "dep_hub": origin_hubs.airport_hub,
                    "arr_hub": dest_hubs.airport_hub,
                    "duration_min": flight_duration_min,
                    "price": float(flight_price),
                    "distance_km": float(route_distance_km),
                    "carbon_kg": round(route_distance_km * 0.082, 1),
                    "comfort_score": 8.5,
                    "seat_class": "Economy Flex",
                    "notes": f"Direct flight corridor from {origin_hubs.airport_hub.code or origin_hubs.parent_city} to {dest_hubs.airport_hub.code or dest_hubs.parent_city}. Priority gate sync.",
                    "transfer_buffer_min": 25,
                },
                "last_mile": {
                    "mode": "cab",
                    "provider": dest_ops["cab"]["provider"],
                    "vehicle_name": dest_ops["cab"]["vehicle_name"],
                    "duration_min": 30,
                    "price": 450.0,
                    "distance_km": 18.0,
                    "carbon_kg": 2.8,
                    "comfort_score": 8.9,
                },
            },
            # 2. BEST VALUE
            {
                "category": "best_value",
                "title": f"{origin_hubs.parent_city} - {dest_hubs.parent_city} Vande Bharat + Rapido QuickSync",
                "summary": "Optimal Pareto balance: avoid urban congestion with Rapido quick transfers and 160 km/h high-speed electric rail.",
                "rank_reason": f"Ranked #1 for Best Overall Value. Outstanding speed-to-cost ratio connecting {origin_hubs.user_node.name} to {dest_hubs.user_node.name}.",
                "first_mile": {
                    "mode": "rapido",
                    "provider": origin_ops["rapido"]["provider"],
                    "vehicle_name": origin_ops["rapido"]["vehicle_name"],
                    "hub": origin_hubs.railway_hub,
                    "duration_min": 25,
                    "price": 180.0,
                    "distance_km": 12.0,
                    "carbon_kg": 1.6,
                    "comfort_score": 8.2,
                    "transfer_buffer_min": 15,
                },
                "main_transport": {
                    "mode": "train",
                    "provider": "Indian Railways Vande Bharat",
                    "vehicle_name": f"{origin_hubs.parent_city} - {dest_hubs.parent_city} Vande Bharat Express",
                    "vehicle_number": str(20000 + (abs(route_distance_km * 7) % 999)),
                    "dep_hub": origin_hubs.railway_hub,
                    "arr_hub": dest_hubs.railway_hub,
                    "duration_min": train_vande_bharat_duration_min,
                    "price": float(train_vande_bharat_price),
                    "distance_km": float(route_distance_km),
                    "carbon_kg": round(route_distance_km * 0.024, 1),
                    "comfort_score": 9.3,
                    "seat_class": "AC Chair Car (CC)",
                    "notes": "Includes reserved ergonomic seating, onboard refreshments, and high-speed rail corridor.",
                    "transfer_buffer_min": 15,
                },
                "last_mile": {
                    "mode": "rapido",
                    "provider": dest_ops["rapido"]["provider"],
                    "vehicle_name": dest_ops["rapido"]["vehicle_name"],
                    "duration_min": 25,
                    "price": 220.0,
                    "distance_km": 11.0,
                    "carbon_kg": 1.5,
                    "comfort_score": 8.2,
                },
            },
            # 3. CHEAPEST
            {
                "category": "cheapest",
                "title": "Economy Multi-Transit Link (City Feeder + Superfast Rail)",
                "summary": "Maximum savings with synchronized public transit feeder lines connecting to intercity express rail.",
                "rank_reason": "Ranked #1 for Economy. Lowest complete door-to-door journey fare.",
                "first_mile": {
                    "mode": "bus",
                    "provider": origin_ops["bus"]["provider"],
                    "vehicle_name": origin_ops["bus"]["vehicle_name"],
                    "hub": origin_hubs.railway_hub,
                    "duration_min": 40,
                    "price": 45.0,
                    "distance_km": 14.0,
                    "carbon_kg": 1.2,
                    "comfort_score": 6.8,
                    "transfer_buffer_min": 15,
                },
                "main_transport": {
                    "mode": "train",
                    "provider": "Indian Railways Superfast",
                    "vehicle_name": f"{origin_hubs.parent_city} - {dest_hubs.parent_city} Superfast Express",
                    "vehicle_number": str(12000 + (abs(route_distance_km * 5) % 999)),
                    "dep_hub": origin_hubs.railway_hub,
                    "arr_hub": dest_hubs.railway_hub,
                    "duration_min": train_cheapest_duration_min,
                    "price": float(train_cheapest_price),
                    "distance_km": float(route_distance_km),
                    "carbon_kg": round(route_distance_km * 0.026, 1),
                    "comfort_score": 7.8,
                    "seat_class": "Sleeper (SL) / 2S Reserved",
                    "notes": "Punctual intercity service with confirmed reserved seating.",
                    "transfer_buffer_min": 15,
                },
                "last_mile": {
                    "mode": "bus",
                    "provider": dest_ops["bus"]["provider"],
                    "vehicle_name": dest_ops["bus"]["vehicle_name"],
                    "duration_min": 35,
                    "price": 40.0,
                    "distance_km": 10.0,
                    "carbon_kg": 1.1,
                    "comfort_score": 6.8,
                },
            },
            # 4. GREENEST
            {
                "category": "greenest",
                "title": "100% Electrified Net-Zero Transit Corridor",
                "summary": "Lowest carbon footprint available: zero-emission urban lines synchronized with 100% electrified rail.",
                "rank_reason": "Ranked #1 for Eco-Friendly. Emits up to 70% lower greenhouse gases than highway or air transit.",
                "first_mile": {
                    "mode": "metro",
                    "provider": origin_ops["metro"]["provider"],
                    "vehicle_name": origin_ops["metro"]["vehicle_name"],
                    "hub": origin_hubs.metro_hub,
                    "duration_min": 25,
                    "price": 40.0,
                    "distance_km": 11.0,
                    "carbon_kg": 0.6,
                    "comfort_score": 8.5,
                    "transfer_buffer_min": 15,
                },
                "main_transport": {
                    "mode": "train",
                    "provider": "Indian Railways 100% Electric",
                    "vehicle_name": f"{origin_hubs.parent_city} - {dest_hubs.parent_city} 100% Electric Rail",
                    "vehicle_number": str(20600 + (abs(route_distance_km * 3) % 99)),
                    "dep_hub": origin_hubs.railway_hub,
                    "arr_hub": dest_hubs.railway_hub,
                    "duration_min": train_greenest_duration_min,
                    "price": float(train_greenest_price),
                    "distance_km": float(route_distance_km),
                    "carbon_kg": round(route_distance_km * 0.016, 1),
                    "comfort_score": 9.1,
                    "seat_class": "Executive Chair Car",
                    "notes": "100% solar and electrified rail corridor verified with minimal carbon emissions.",
                    "transfer_buffer_min": 15,
                },
                "last_mile": {
                    "mode": "metro",
                    "provider": dest_ops["metro"]["provider"],
                    "vehicle_name": dest_ops["metro"]["vehicle_name"],
                    "duration_min": 20,
                    "price": 45.0,
                    "distance_km": 9.0,
                    "carbon_kg": 0.5,
                    "comfort_score": 8.5,
                },
            },
            # 5. COMFORTABLE
            {
                "category": "comfortable",
                "title": "Executive Comfort SyncPass (Chauffeur + 1st AC Rail)",
                "summary": "First-class travel experience with dedicated door-to-station executive sedan pickup and spacious 1st AC carriage.",
                "rank_reason": "Ranked #1 for Comfort. Features dedicated chauffeur transfers, lounge access, and premium legroom.",
                "first_mile": {
                    "mode": "cab",
                    "provider": f"KogniSync Executive Chauffeur ({origin_hubs.parent_city})",
                    "vehicle_name": "Luxury Electric Sedan",
                    "hub": origin_hubs.railway_hub,
                    "duration_min": 25,
                    "price": 450.0,
                    "distance_km": 13.0,
                    "carbon_kg": 3.4,
                    "comfort_score": 9.8,
                    "transfer_buffer_min": 20,
                },
                "main_transport": {
                    "mode": "train",
                    "provider": "Indian Railways Shatabdi",
                    "vehicle_name": f"{origin_hubs.parent_city} - {dest_hubs.parent_city} Executive Express",
                    "vehicle_number": str(12000 + (abs(route_distance_km * 2) % 999)),
                    "dep_hub": origin_hubs.railway_hub,
                    "arr_hub": dest_hubs.railway_hub,
                    "duration_min": train_comfort_duration_min,
                    "price": float(train_comfort_price),
                    "distance_km": float(route_distance_km),
                    "carbon_kg": round(route_distance_km * 0.026, 1),
                    "comfort_score": 9.7,
                    "seat_class": "Executive AC Chair (1st Class)",
                    "notes": "Includes hot meals, refreshment service, and station VIP lounge access.",
                    "transfer_buffer_min": 20,
                },
                "last_mile": {
                    "mode": "cab",
                    "provider": f"KogniSync Executive Chauffeur ({dest_hubs.parent_city})",
                    "vehicle_name": "Luxury Electric Sedan",
                    "duration_min": 25,
                    "price": 500.0,
                    "distance_km": 12.0,
                    "carbon_kg": 3.2,
                    "comfort_score": 9.8,
                },
            },
        ]

        raw_journeys: list[JourneySchema] = []

        for arch_idx, arch in enumerate(archetypes):
            dep_hub: LocationSchema = arch["first_mile"]["hub"]
            arr_hub: LocationSchema = arch["main_transport"]["arr_hub"]

            # Anchor arrival safely before user's deadline (15 - 35 min buffer)
            arrival_buffer_min = 15 + (arch_idx * 5)
            target_arr_min = target_min - arrival_buffer_min
            target_arr_hour = target_hour
            if target_arr_min < 0:
                target_arr_hour -= 1
                target_arr_min += 60

            final_arr_date = build_iso_date(date_str, target_arr_hour, target_arr_min)

            # Query providers / resolve data for each segment
            dur3, dist3, prov_overrides3 = await self._resolve_segment_data(
                origin_node=arr_hub,
                dest_node=dest_hubs.user_node,
                mode=arch["last_mile"]["mode"],
                provider_name=arch["last_mile"]["provider"],
                default_duration=arch["last_mile"]["duration_min"],
                default_distance=arch["last_mile"]["distance_km"],
                provider_status=provider_status,
            )

            dur2, dist2, prov_overrides2 = await self._resolve_segment_data(
                origin_node=dep_hub,
                dest_node=arr_hub,
                mode=arch["main_transport"]["mode"],
                provider_name=arch["main_transport"]["provider"],
                default_duration=arch["main_transport"]["duration_min"],
                default_distance=arch["main_transport"]["distance_km"],
                provider_status=provider_status,
            )

            dur1, dist1, prov_overrides1 = await self._resolve_segment_data(
                origin_node=origin_hubs.user_node,
                dest_node=dep_hub,
                mode=arch["first_mile"]["mode"],
                provider_name=arch["first_mile"]["provider"],
                default_duration=arch["first_mile"]["duration_min"],
                default_distance=arch["first_mile"]["distance_km"],
                provider_status=provider_status,
            )

            # Compute segment boundaries backward with resolved durations
            seg3_arr = final_arr_date
            seg3_dep = seg3_arr - timedelta(minutes=dur3)

            seg2_arr = seg3_dep - timedelta(minutes=arch["main_transport"]["transfer_buffer_min"])
            seg2_dep = seg2_arr - timedelta(minutes=dur2)

            seg1_arr = seg2_dep - timedelta(minutes=arch["first_mile"]["transfer_buffer_min"])
            seg1_dep = seg1_arr - timedelta(minutes=dur1)

            cat = arch["category"]

            # Leg 1: First-Mile
            prov1 = build_default_segment_provenance(
                arch["first_mile"]["provider"],
                arch["first_mile"]["mode"],
                attribute_overrides=prov_overrides1,
            )
            carbon1 = calculate_calibrated_segment_carbon(
                mode=arch["first_mile"]["mode"],
                resolved_distance_km=dist1,
                baseline_distance_km=arch["first_mile"]["distance_km"],
                baseline_carbon_kg=arch["first_mile"]["carbon_kg"],
            )
            segment1 = JourneySegmentSchema(
                segment_id=f"seg-{route_slug}-{cat}-01",
                sequence=1,
                mode=arch["first_mile"]["mode"],
                provider=arch["first_mile"]["provider"],
                vehicle_name=arch["first_mile"]["vehicle_name"],
                origin=origin_hubs.user_node,
                destination=dep_hub,
                departure_time=seg1_dep.isoformat(),
                arrival_time=seg1_arr.isoformat(),
                duration_minutes=dur1,
                price=arch["first_mile"]["price"],
                currency="INR",
                availability=SegmentAvailabilitySchema(status="available", remaining_units=45, is_real_inventory=False),
                distance_km=dist1,
                carbon_kg=carbon1,
                comfort_score=arch["first_mile"]["comfort_score"],
                transfer_buffer_minutes=arch["first_mile"]["transfer_buffer_min"],
                notes=f"Direct pickup at {origin_hubs.user_node.name}. Sync transfer buffer: {arch['first_mile']['transfer_buffer_min']}m.",
                provenance=prov1,
            )

            # Leg 2: Main Transit Corridor
            prov2 = build_default_segment_provenance(
                arch["main_transport"]["provider"],
                arch["main_transport"]["mode"],
                attribute_overrides=prov_overrides2,
            )
            carbon2 = calculate_calibrated_segment_carbon(
                mode=arch["main_transport"]["mode"],
                resolved_distance_km=dist2,
                baseline_distance_km=arch["main_transport"]["distance_km"],
                baseline_carbon_kg=arch["main_transport"]["carbon_kg"],
            )
            segment2 = JourneySegmentSchema(
                segment_id=f"seg-{route_slug}-{cat}-02",
                sequence=2,
                mode=arch["main_transport"]["mode"],
                provider=arch["main_transport"]["provider"],
                vehicle_name=arch["main_transport"]["vehicle_name"],
                vehicle_number=arch["main_transport"]["vehicle_number"],
                origin=dep_hub,
                destination=arr_hub,
                departure_time=seg2_dep.isoformat(),
                arrival_time=seg2_arr.isoformat(),
                duration_minutes=dur2,
                price=arch["main_transport"]["price"],
                currency="INR",
                availability=SegmentAvailabilitySchema(status="available", remaining_units=18, is_real_inventory=False),
                distance_km=dist2,
                carbon_kg=carbon2,
                comfort_score=arch["main_transport"]["comfort_score"],
                seat_class=arch["main_transport"]["seat_class"],
                transfer_buffer_minutes=arch["main_transport"]["transfer_buffer_min"],
                notes=arch["main_transport"]["notes"],
                provenance=prov2,
            )

            # Leg 3: Last-Mile Drop-Off
            prov3 = build_default_segment_provenance(
                arch["last_mile"]["provider"],
                arch["last_mile"]["mode"],
                attribute_overrides=prov_overrides3,
            )
            carbon3 = calculate_calibrated_segment_carbon(
                mode=arch["last_mile"]["mode"],
                resolved_distance_km=dist3,
                baseline_distance_km=arch["last_mile"]["distance_km"],
                baseline_carbon_kg=arch["last_mile"]["carbon_kg"],
            )
            segment3 = JourneySegmentSchema(
                segment_id=f"seg-{route_slug}-{cat}-03",
                sequence=3,
                mode=arch["last_mile"]["mode"],
                provider=arch["last_mile"]["provider"],
                vehicle_name=arch["last_mile"]["vehicle_name"],
                origin=arr_hub,
                destination=dest_hubs.user_node,
                departure_time=seg3_dep.isoformat(),
                arrival_time=seg3_arr.isoformat(),
                duration_minutes=dur3,
                price=arch["last_mile"]["price"],
                currency="INR",
                availability=SegmentAvailabilitySchema(status="available", remaining_units=99, is_real_inventory=False),
                distance_km=dist3,
                carbon_kg=carbon3,
                comfort_score=arch["last_mile"]["comfort_score"],
                notes=f"Final transfer to {dest_hubs.user_node.name}. Driver will meet at {arr_hub.name} arrival exit.",
                provenance=prov3,
            )

            segments = [segment1, segment2, segment3]
            total_price = sum(s.price for s in segments)
            travel_dur = sum(s.duration_minutes for s in segments)
            waiting_dur = arch["first_mile"]["transfer_buffer_min"] + arch["main_transport"]["transfer_buffer_min"]
            total_duration_minutes = round((seg3_arr - seg1_dep).total_seconds() / 60.0)
            total_transfers = len(segments) - 1
            total_carbon = round(sum(s.carbon_kg for s in segments), 1)
            avg_comfort = round(sum(s.comfort_score * s.duration_minutes for s in segments) / travel_dur, 1)
            modes: list[TransportMode] = list(dict.fromkeys(s.mode for s in segments))

            journey_prov = build_journey_provenance(segments)

            has_live_dur = any(
                s.provenance and s.provenance.attributes.get("duration", AttributeProvenanceSchema()).source_type == "provider_live"
                for s in segments
            )
            live_dur_names = ", ".join(dict.fromkeys(
                s.provenance.attributes["duration"].provider_name
                for s in segments
                if s.provenance
                and s.provenance.attributes.get("duration", AttributeProvenanceSchema()).source_type == "provider_live"
                and s.provenance.attributes.get("duration", AttributeProvenanceSchema()).provider_name
            )) or "Google Routes API v2"

            if has_live_dur:
                credibility_notice = (
                    f"Transit durations reflect live provider routing feeds ({live_dur_names}). "
                    "Fares are deterministic corridor estimates and seat availability is simulated demo inventory "
                    "requiring live provider confirmation prior to booking."
                )
                trade_off_notes = [
                    f"Live traffic-aware duration: transit ETAs verified via {live_dur_names}",
                    "Corridor-modeled estimates: fare and seat capacity remain unverified demo inventory until live booking lock",
                ]
                is_dur_est = False
            else:
                credibility_notice = (
                    "Fares, travel durations, and schedules are deterministic estimates. "
                    "Availability is unverified synthetic data and requires live provider confirmation prior to booking."
                )
                trade_off_notes = [
                    "Corridor-modeled estimates: fare and transit duration are unverified until live booking lock"
                ]
                is_dur_est = True

            journey = JourneySchema(
                id=f"jny-{route_slug}-{cat}",
                title=arch["title"],
                origin=origin_hubs.user_node,
                destination=dest_hubs.user_node,
                departure_time=seg1_dep.isoformat(),
                arrival_time=seg3_arr.isoformat(),
                total_duration_minutes=total_duration_minutes,
                travel_duration_minutes=travel_dur,
                waiting_duration_minutes=waiting_dur,
                total_price=total_price,
                currency="INR",
                total_transfers=total_transfers,
                modes=modes,
                segments=segments,
                carbon_kg=total_carbon,
                comfort_score=avg_comfort,
                recommendation_category=cat,
                is_pareto_optimal=True,
                ai_explanation=AIExplanationSchema(
                    summary=arch["summary"],
                    rank_reason=f"{arch['rank_reason']} (Evaluated against deterministic corridor estimates; live availability unconfirmed).",
                    trade_offs=[
                        f"3 synchronized legs: {segment1.provider} → {segment2.provider} → {segment3.provider}",
                        f"Arrival guaranteed by {seg3_arr.strftime('%I:%M %p')} before deadline",
                        f"Total transfer wait: {waiting_dur} min with live synchronization",
                    ] + trade_off_notes,
                    score=90.0,
                    cost_vs_fastest_saving=max(0.0, float(flight_price + 1100 - total_price)),
                    duration_diff_minutes=total_duration_minutes - (flight_duration_min + 65),
                    data_credibility_notice=credibility_notice,
                    is_fare_estimated=True,
                    is_duration_estimated=is_dur_est,
                    is_availability_verified=False,
                ),
                booking_feasibility=BookingFeasibilitySchema(
                    hold_supported=True,
                    concurrency_safe=True,
                    hold_ttl_seconds=600,
                ),
                provenance=journey_prov,
            )
            raw_journeys.append(journey)

        # 2. Integrate with Backend JourneyOptimizerService
        candidate_inputs = [
            JourneyCandidateInput(
                id=j.id,
                title=j.title,
                total_price=j.total_price,
                total_duration_minutes=j.total_duration_minutes,
                total_transfers=j.total_transfers,
                carbon_kg=j.carbon_kg,
                comfort_score=j.comfort_score,
                modes=j.modes,
                recommendation_category=j.recommendation_category,
                departure_time=j.departure_time,
                arrival_time=j.arrival_time,
            )
            for j in raw_journeys
        ]

        # Preferred arrival formatting for optimizer check (HH:MM)
        preferred_arr = f"{target_hour:02d}:{target_min:02d}" if request.preferred_arrival_before else None

        opt_req = OptimizationRequest(
            weights=request.weights or OptimizationWeightsInput(),
            budget_max=request.budget_max,
            preferred_arrival_before=preferred_arr,
            candidates=candidate_inputs,
        )

        opt_res = self.optimizer.optimize_journeys(opt_req)

        # Map optimized results back to JourneySchema
        journey_by_id = {j.id: j for j in raw_journeys}
        final_journeys: list[JourneySchema] = []

        for opt_out in opt_res.journeys:
            if opt_out.id in journey_by_id:
                j = journey_by_id[opt_out.id]
                has_live_dur = any(
                    s.provenance and s.provenance.attributes.get("duration", AttributeProvenanceSchema()).source_type == "provider_live"
                    for s in j.segments
                )
                notes_to_add = (
                    [
                        "Live traffic-aware duration: transit ETAs verified via Google Routes API v2",
                        "Corridor-modeled estimates: fare and seat capacity remain unverified demo inventory until live booking lock",
                    ]
                    if has_live_dur
                    else [
                        "Corridor-modeled estimates: fare and transit duration are unverified until live booking lock"
                    ]
                )
                # Attach optimizer evaluation and explanation
                j.is_pareto_optimal = opt_out.is_pareto_optimal
                j.optimization = opt_out
                j.ai_explanation.score = round(opt_out.score * 100.0, 1)
                j.ai_explanation.trade_offs = opt_out.explanation.tradeoffs + notes_to_add
                j.ai_explanation.rank_reason = "; ".join(opt_out.explanation.reasons) or j.ai_explanation.rank_reason
                j.ai_explanation.is_duration_estimated = not has_live_dur
                j.ai_explanation.is_fare_estimated = True
                j.ai_explanation.is_availability_verified = False
                if has_live_dur:
                    j.ai_explanation.data_credibility_notice = (
                        "Transit durations reflect live provider traffic feeds (Google Routes API v2). "
                        "Fares are deterministic corridor estimates and seat availability is simulated demo inventory "
                        "requiring live provider confirmation prior to booking."
                    )
                final_journeys.append(j)

        return JourneySearchResponse(
            journeys=final_journeys,
            recommended_journey_id=opt_res.recommended_journey_id or (final_journeys[0].id if final_journeys else None),
            total_candidates=len(raw_journeys),
            eligible_candidates=len(final_journeys),
            pareto_frontier_count=opt_res.pareto_frontier_count,
            source="backend_orchestrator",
            provider_status=provider_status,
        )


journey_orchestrator = JourneyOrchestrationService()
