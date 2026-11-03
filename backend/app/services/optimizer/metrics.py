from typing import Sequence
from app.services.optimizer.schemas import JourneyCandidateInput, JourneyOptimizationMetrics

# Centralized emissions factors (kg CO2 per passenger-km)
CARBON_FACTORS_KG_PER_KM: dict[str, float] = {
    "flight": 0.150,   # Domestic passenger flight
    "cab": 0.120,      # Dedicated private cab / taxi
    "car": 0.120,
    "taxi": 0.120,
    "auto": 0.075,     # Auto-rickshaw (CNG / petrol)
    "rapido": 0.045,   # Two-wheeler motorcycle taxi
    "bus": 0.040,      # Intercity / municipal feeder bus
    "train": 0.025,    # Electric passenger rail / superfast
    "rail": 0.025,
    "metro": 0.020,    # Urban rapid electric metro
    "walk": 0.000,     # Pedestrian
}

# Base deterministic comfort ratings per transport mode [0, 1]
BASE_MODE_COMFORT: dict[str, float] = {
    "flight": 0.85,
    "cab": 0.80,
    "car": 0.80,
    "taxi": 0.80,
    "train": 0.75,
    "rail": 0.75,
    "metro": 0.70,
    "bus": 0.60,
    "auto": 0.55,
    "rapido": 0.50,
    "walk": 0.40,
}


def compute_segment_carbon_kg(mode: str, distance_km: float) -> float:
    """Calculates carbon footprint for a segment based on centralized emission factors."""
    factor = CARBON_FACTORS_KG_PER_KM.get(mode.lower(), 0.060)
    return round(distance_km * factor, 2)


def derive_journey_comfort_score(
    modes: Sequence[str],
    total_transfers: int,
    duration_minutes: int,
    base_comfort_input: float | None = None,
) -> float:
    """Derives a transparent, deterministic comfort score in [0.0, 1.0]."""
    if base_comfort_input is not None and base_comfort_input > 0:
        # If already on 1-10 scale, normalize to [0, 1]
        raw_base = base_comfort_input / 10.0 if base_comfort_input > 1.0 else base_comfort_input
    else:
        # Derive from modes
        if modes:
            raw_base = sum(BASE_MODE_COMFORT.get(m.lower(), 0.65) for m in modes) / len(modes)
        else:
            raw_base = 0.70

    # Multi-transfer penalty
    transfer_penalty = max(0, total_transfers) * 0.04

    # Excessive duration penalty (journeys exceeding 6 hours lose 0.03 per additional 2 hours)
    excess_hours = max(0.0, (duration_minutes - 360) / 120.0)
    duration_penalty = min(0.15, excess_hours * 0.03)

    final_comfort = raw_base - transfer_penalty - duration_penalty
    # Clamp to [0.10, 1.00]
    return round(max(0.10, min(1.00, final_comfort)), 3)


def extract_journey_metrics(candidate: JourneyCandidateInput) -> JourneyOptimizationMetrics:
    """Extracts or normalizes the 5 core optimization metrics for a candidate journey."""
    comfort = derive_journey_comfort_score(
        candidate.modes,
        candidate.total_transfers,
        candidate.total_duration_minutes,
        candidate.comfort_score,
    )

    return JourneyOptimizationMetrics(
        total_cost=float(candidate.total_price),
        duration_minutes=int(candidate.total_duration_minutes),
        transfer_count=int(candidate.total_transfers),
        comfort_score=comfort,
        carbon_kg=float(round(candidate.carbon_kg, 2)),
    )
