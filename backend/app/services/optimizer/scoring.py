from app.services.optimizer.schemas import (
    JourneyOptimizationMetrics,
    JourneyScoreBreakdown,
    ObjectiveScoreContribution,
    OptimizationWeightsInput,
)


def normalize_weights(w: OptimizationWeightsInput) -> dict[str, float]:
    """Ensures preference weights sum to exactly 1.0."""
    raw = {
        "cost": max(0.0, float(w.cost)),
        "duration": max(0.0, float(w.duration)),
        "comfort": max(0.0, float(w.comfort)),
        "carbon": max(0.0, float(w.carbon)),
        "transfers": max(0.0, float(w.transfers)),
    }
    total = sum(raw.values())
    if total <= 1e-9:
        # Balanced default
        return {"cost": 0.40, "duration": 0.30, "comfort": 0.20, "carbon": 0.10, "transfers": 0.0}

    return {k: round(v / total, 4) for k, v in raw.items()}


def compute_journey_score(
    metrics: JourneyOptimizationMetrics,
    norm_dict: dict[str, float],
    weights: dict[str, float],
) -> JourneyScoreBreakdown:
    """Computes transparent weighted score and intermediate contribution breakdowns."""
    cost_contrib = round(norm_dict["cost"] * weights["cost"], 4)
    dur_contrib = round(norm_dict["duration"] * weights["duration"], 4)
    comf_contrib = round(norm_dict["comfort"] * weights["comfort"], 4)
    carb_contrib = round(norm_dict["carbon"] * weights["carbon"], 4)
    transf_contrib = round(norm_dict.get("transfers", 1.0) * weights.get("transfers", 0.0), 4)

    total = round(
        min(1.0, max(0.0, cost_contrib + dur_contrib + comf_contrib + carb_contrib + transf_contrib)),
        4,
    )

    cost_obj = ObjectiveScoreContribution(
        raw=metrics.total_cost,
        normalized=norm_dict["cost"],
        weight=weights["cost"],
        contribution=cost_contrib,
    )
    dur_obj = ObjectiveScoreContribution(
        raw=float(metrics.duration_minutes),
        normalized=norm_dict["duration"],
        weight=weights["duration"],
        contribution=dur_contrib,
    )
    comf_obj = ObjectiveScoreContribution(
        raw=metrics.comfort_score,
        normalized=norm_dict["comfort"],
        weight=weights["comfort"],
        contribution=comf_contrib,
    )
    carb_obj = ObjectiveScoreContribution(
        raw=metrics.carbon_kg,
        normalized=norm_dict["carbon"],
        weight=weights["carbon"],
        contribution=carb_contrib,
    )
    transf_obj = ObjectiveScoreContribution(
        raw=float(metrics.transfer_count),
        normalized=norm_dict["transfers"],
        weight=weights.get("transfers", 0.0),
        contribution=transf_contrib,
    )

    return JourneyScoreBreakdown(
        cost=cost_obj,
        duration=dur_obj,
        comfort=comf_obj,
        carbon=carb_obj,
        transfers=transf_obj,
        total_score=total,
    )
