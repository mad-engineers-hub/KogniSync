"""
backend/app/services/journey/connection_validator.py

Authoritative connection feasibility and quality evaluation engine for KogniSync multimodal journeys (M3.3).
Validates:
1. Chronological validity and sequence order (no reversed or overlapping legs).
2. Intermodal transfer buffer adequacy (planning assumptions for airport security, rail boarding, bus terminals).
3. Realistic connection windows (prunes impossible or excessively tight transfers).
4. Excessive idle transfer time detection.
5. User arrival deadline and budget constraints.
"""
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Sequence
from app.services.journey.schemas import JourneySchema, JourneySegmentSchema

# Documented planning buffer assumptions (minutes)
# Note: These values are transparent planning assumptions for multimodal coordination,
# not official carrier-mandated check-in times.
PLANNING_BUFFER_DEFAULTS: dict[str, int] = {
    # Departure hubs
    "flight_departure_buffer": 45,       # Domestic airport check-in, security screening, and gate arrival
    "train_departure_buffer": 15,        # Station concourse navigation, platform access, boarding
    "bus_departure_buffer": 15,          # Intercity bus terminal boarding
    "metro_departure_buffer": 8,         # Urban metro turnstile and platform interchange
    # Arrival / exit hubs (deboarding & exit to street access)
    "flight_arrival_exit_buffer": 20,    # Aircraft deboarding, terminal walk, baggage retrieval
    "train_arrival_exit_buffer": 10,     # Deboarding and platform exit
    "bus_arrival_exit_buffer": 10,       # Deboarding and terminal exit
    "metro_arrival_exit_buffer": 5,      # Metro platform to street exit
    # Street road access
    "road_transfer_buffer": 5,           # Road-to-road interchange / vehicle swap
}

# Maximum allowed idle transfer window before connection is flagged as impractical (4 hours)
MAX_ALLOWED_TRANSFER_BUFFER_MINUTES = 240


@dataclass
class ConnectionEvaluationResult:
    """Detailed result of connection quality and feasibility evaluation."""
    is_feasible: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    connection_quality_score: float = 1.0  # Normalized [0.0, 1.0]
    total_waiting_minutes: int = 0
    buffer_evaluations: list[dict[str, Any]] = field(default_factory=list)


def get_minimum_required_buffer_minutes(
    incoming_mode: str,
    outgoing_mode: str,
    outgoing_hub_type: str | None = None,
) -> int:
    """
    Returns the minimum planning buffer assumption (in minutes) required between
    an incoming segment and outgoing segment at an intermodal transfer node.
    """
    inc = incoming_mode.lower()
    out = outgoing_mode.lower()

    # Outgoing flight requires airport check-in & security screening buffer
    if out == "flight":
        return PLANNING_BUFFER_DEFAULTS["flight_departure_buffer"]

    # Incoming flight requires deplaning and baggage claim buffer
    if inc == "flight":
        return PLANNING_BUFFER_DEFAULTS["flight_arrival_exit_buffer"]

    # Outgoing train requires platform boarding buffer
    if out == "train":
        return PLANNING_BUFFER_DEFAULTS["train_departure_buffer"]

    # Outgoing intercity bus requires terminal boarding buffer
    if out == "bus":
        return PLANNING_BUFFER_DEFAULTS["bus_departure_buffer"]

    # Metro concourse interchange
    if out == "metro" or inc == "metro":
        return PLANNING_BUFFER_DEFAULTS["metro_departure_buffer"]

    # Road-to-road transfer (e.g. cab to auto or rapido)
    return PLANNING_BUFFER_DEFAULTS["road_transfer_buffer"]


def validate_journey_connections(
    journey: JourneySchema,
    preferred_arrival_before: str | None = None,
    budget_max: float | None = None,
) -> ConnectionEvaluationResult:
    """
    Evaluates connection feasibility, chronological sequence, transfer buffers, and hard constraints.
    Returns a ConnectionEvaluationResult. If is_feasible is False, the journey must NOT be recommended.
    """
    reasons: list[str] = []
    warnings: list[str] = []
    buffer_evals: list[dict[str, Any]] = []
    total_waiting = 0
    segments = journey.segments

    if not segments:
        return ConnectionEvaluationResult(
            is_feasible=False,
            reasons=["Journey contains no transport segments."],
            connection_quality_score=0.0,
        )

    # 1. Hard Budget Constraint
    if budget_max is not None and budget_max > 0:
        if journey.total_price > budget_max:
            reasons.append(
                f"Total journey fare (₹{journey.total_price:.2f}) exceeds specified budget cap (₹{budget_max:.2f})."
            )

    # 2. Hard Arrival Deadline Constraint
    if preferred_arrival_before and journey.arrival_time:
        try:
            arr_str = str(journey.arrival_time)
            pref_str = str(preferred_arrival_before)
            arr_time_hhmm = arr_str.split("T")[1][:5] if "T" in arr_str else arr_str[:5]
            pref_time_hhmm = pref_str.split("T")[1][:5] if "T" in pref_str else pref_str[:5]
            if arr_time_hhmm > pref_time_hhmm:
                reasons.append(
                    f"Journey arrival time ({arr_time_hhmm}) exceeds requested arrival deadline ({pref_time_hhmm})."
                )
        except Exception:
            pass

    # 3. Individual Segment Chronological Validation
    def _to_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    parsed_times: list[tuple[datetime, datetime]] = []
    for idx, seg in enumerate(segments):
        try:
            dep_dt = _to_utc(datetime.fromisoformat(seg.departure_time))
            arr_dt = _to_utc(datetime.fromisoformat(seg.arrival_time))
            parsed_times.append((dep_dt, arr_dt))

            if dep_dt >= arr_dt:
                reasons.append(
                    f"Segment #{idx + 1} ({seg.mode} by {seg.provider}) has invalid inverted or zero duration: departure {seg.departure_time} >= arrival {seg.arrival_time}."
                )
        except Exception as e:
            reasons.append(f"Segment #{idx + 1} has unparseable ISO timestamps: {e}")

    # If basic timestamps are unparseable or inverted, return early as infeasible
    if reasons:
        return ConnectionEvaluationResult(
            is_feasible=False,
            reasons=reasons,
            connection_quality_score=0.0,
        )

    # 4. Intermodal Transfer Node Validations
    quality_score = 1.0

    for i in range(len(segments) - 1):
        prev_seg = segments[i]
        next_seg = segments[i + 1]
        prev_arr_dt = parsed_times[i][1]
        next_dep_dt = parsed_times[i + 1][0]

        # Calculate actual transfer buffer in elapsed minutes
        actual_buffer_seconds = (next_dep_dt - prev_arr_dt).total_seconds()
        actual_buffer_minutes = round(actual_buffer_seconds / 60.0)

        min_required_buffer = get_minimum_required_buffer_minutes(
            incoming_mode=prev_seg.mode,
            outgoing_mode=next_seg.mode,
            outgoing_hub_type=prev_seg.destination.type,
        )

        buffer_eval = {
            "transfer_index": i + 1,
            "hub_name": prev_seg.destination.name,
            "incoming_mode": prev_seg.mode,
            "outgoing_mode": next_seg.mode,
            "actual_buffer_minutes": actual_buffer_minutes,
            "min_required_buffer_minutes": min_required_buffer,
            "is_buffer_sufficient": actual_buffer_minutes >= min_required_buffer,
        }
        buffer_evals.append(buffer_eval)
        total_waiting += max(0, actual_buffer_minutes)

        # Rule A: Reversed or negative connection sequence
        if actual_buffer_seconds < 0:
            reasons.append(
                f"Negative connection window at {prev_seg.destination.name}: outgoing {next_seg.mode} departs ({next_seg.departure_time}) before incoming {prev_seg.mode} arrives ({prev_seg.arrival_time})."
            )
            quality_score = 0.0

        # Rule B: Unrealistically short connection window (sub-minimum buffer)
        elif actual_buffer_minutes < min_required_buffer:
            reasons.append(
                f"Unrealistically short connection window at {prev_seg.destination.name}: transfer buffer of {actual_buffer_minutes}m is less than the required {min_required_buffer}m planning assumption for {next_seg.mode} boarding."
            )
            quality_score = min(quality_score, 0.2)

        # Rule C: Tight connection warning (within 5 minutes of minimum)
        elif actual_buffer_minutes < min_required_buffer + 5:
            warnings.append(
                f"Tight connection window at {prev_seg.destination.name}: {actual_buffer_minutes}m available ({min_required_buffer}m min planning assumption)."
            )
            quality_score -= 0.1

        # Rule D: Excessive transfer time (> 4 hours)
        if actual_buffer_minutes > MAX_ALLOWED_TRANSFER_BUFFER_MINUTES:
            warnings.append(
                f"Excessive transfer idle time at {prev_seg.destination.name}: {actual_buffer_minutes}m ({actual_buffer_minutes // 60}h {actual_buffer_minutes % 60}m) exceeds 4-hour threshold."
            )
            quality_score -= 0.3

    is_feasible = len(reasons) == 0
    final_quality_score = max(0.0, min(1.0, round(quality_score, 2)))

    return ConnectionEvaluationResult(
        is_feasible=is_feasible,
        reasons=reasons,
        warnings=warnings,
        connection_quality_score=final_quality_score,
        total_waiting_minutes=total_waiting,
        buffer_evaluations=buffer_evals,
    )
