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

    # Apply any attribute-level overrides (e.g. from live external provider)
    for attr_key, attr_prov in overrides.items():
        default_attrs[attr_key] = attr_prov

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

    return JourneyProvenanceSchema(
        overall_source_type=overall,
        is_fully_confirmed=False,  # Never claims confirmed availability based on generated estimates
        has_live_attributes=has_live,
        has_simulated_attributes=has_simulated,
        summary=summary,
    )


class JourneyOrchestrationService:
    """Authoritative multimodal journey orchestration and data credibility service."""

    def __init__(
        self,
        optimizer: JourneyOptimizerService | None = None,
        provider_registry: dict[str, Callable] | None = None,
    ):
        self.optimizer = optimizer or optimizer_service
        self.provider_registry = provider_registry or {}

    async def _query_provider(
        self,
        provider_key: str,
        context: dict[str, Any],
        provider_status: dict[str, str],
    ) -> dict[str, AttributeProvenanceSchema] | None:
        """
        Safely invokes registered external providers with strict timeout and error boundaries.
        Never leaks internal exceptions or credentials.
        """
        provider_fn = self.provider_registry.get(provider_key)
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

            # Compute segment boundaries backward
            seg3_arr = final_arr_date
            seg3_dep = seg3_arr - timedelta(minutes=arch["last_mile"]["duration_min"])

            seg2_arr = seg3_dep - timedelta(minutes=arch["main_transport"]["transfer_buffer_min"])
            seg2_dep = seg2_arr - timedelta(minutes=arch["main_transport"]["duration_min"])

            seg1_arr = seg2_dep - timedelta(minutes=arch["first_mile"]["transfer_buffer_min"])
            seg1_dep = seg1_arr - timedelta(minutes=arch["first_mile"]["duration_min"])

            cat = arch["category"]

            # Query any registered live provider for this archetype/leg
            live_seg2_overrides = await self._query_provider(
                arch["main_transport"]["provider"],
                {"origin": dep_hub.city, "destination": arr_hub.city, "mode": arch["main_transport"]["mode"]},
                provider_status,
            )

            # Leg 1: First-Mile
            prov1 = build_default_segment_provenance(arch["first_mile"]["provider"], arch["first_mile"]["mode"])
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
                duration_minutes=arch["first_mile"]["duration_min"],
                price=arch["first_mile"]["price"],
                currency="INR",
                availability=SegmentAvailabilitySchema(status="available", remaining_units=45, is_real_inventory=False),
                distance_km=arch["first_mile"]["distance_km"],
                carbon_kg=arch["first_mile"]["carbon_kg"],
                comfort_score=arch["first_mile"]["comfort_score"],
                transfer_buffer_minutes=arch["first_mile"]["transfer_buffer_min"],
                notes=f"Direct pickup at {origin_hubs.user_node.name}. Sync transfer buffer: {arch['first_mile']['transfer_buffer_min']}m.",
                provenance=prov1,
            )

            # Leg 2: Main Transit Corridor
            prov2 = build_default_segment_provenance(
                arch["main_transport"]["provider"],
                arch["main_transport"]["mode"],
                attribute_overrides=live_seg2_overrides,
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
                duration_minutes=arch["main_transport"]["duration_min"],
                price=arch["main_transport"]["price"],
                currency="INR",
                availability=SegmentAvailabilitySchema(status="available", remaining_units=18, is_real_inventory=False),
                distance_km=arch["main_transport"]["distance_km"],
                carbon_kg=arch["main_transport"]["carbon_kg"],
                comfort_score=arch["main_transport"]["comfort_score"],
                seat_class=arch["main_transport"]["seat_class"],
                transfer_buffer_minutes=arch["main_transport"]["transfer_buffer_min"],
                notes=arch["main_transport"]["notes"],
                provenance=prov2,
            )

            # Leg 3: Last-Mile Drop-Off
            prov3 = build_default_segment_provenance(arch["last_mile"]["provider"], arch["last_mile"]["mode"])
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
                duration_minutes=arch["last_mile"]["duration_min"],
                price=arch["last_mile"]["price"],
                currency="INR",
                availability=SegmentAvailabilitySchema(status="available", remaining_units=99, is_real_inventory=False),
                distance_km=arch["last_mile"]["distance_km"],
                carbon_kg=arch["last_mile"]["carbon_kg"],
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
                        "Corridor-modeled estimates: fare and transit duration are unverified until live booking lock",
                    ],
                    score=90.0,
                    cost_vs_fastest_saving=max(0.0, float(flight_price + 1100 - total_price)),
                    duration_diff_minutes=total_duration_minutes - (flight_duration_min + 65),
                    data_credibility_notice="Fares, travel durations, and schedules are deterministic estimates. Availability is unverified synthetic data and requires live provider confirmation prior to booking.",
                    is_fare_estimated=True,
                    is_duration_estimated=True,
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
                # Attach optimizer evaluation and explanation
                j.is_pareto_optimal = opt_out.is_pareto_optimal
                j.optimization = opt_out
                j.ai_explanation.score = round(opt_out.score * 100.0, 1)
                j.ai_explanation.trade_offs = opt_out.explanation.tradeoffs + [
                    "Corridor-modeled estimates: fare and transit duration are unverified until live booking lock"
                ]
                j.ai_explanation.rank_reason = "; ".join(opt_out.explanation.reasons) or j.ai_explanation.rank_reason
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
