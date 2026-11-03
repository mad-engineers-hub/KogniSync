from typing import Sequence
from app.services.optimizer.schemas import JourneyOptimizationMetrics


def dominates(
    a: JourneyOptimizationMetrics,
    b: JourneyOptimizationMetrics,
    tolerance: float = 1e-6,
) -> bool:
    """Evaluates whether Journey A dominates Journey B across all 5 objectives.

    Criteria for A to dominate B:
    1. A is no worse than B in all objectives:
       - cost: a <= b
       - duration: a <= b
       - carbon: a <= b
       - transfers: a <= b
       - comfort: a >= b
    2. A is strictly better than B in at least one objective.
    """
    no_worse = (
        (a.total_cost <= b.total_cost + tolerance)
        and (a.duration_minutes <= b.duration_minutes)
        and (a.carbon_kg <= b.carbon_kg + tolerance)
        and (a.transfer_count <= b.transfer_count)
        and (a.comfort_score >= b.comfort_score - tolerance)
    )

    if not no_worse:
        return False

    strictly_better = (
        (a.total_cost < b.total_cost - tolerance)
        or (a.duration_minutes < b.duration_minutes)
        or (a.carbon_kg < b.carbon_kg - tolerance)
        or (a.transfer_count < b.transfer_count)
        or (a.comfort_score > b.comfort_score + tolerance)
    )

    return strictly_better


def compute_pareto_frontier(
    metrics_list: Sequence[JourneyOptimizationMetrics],
) -> list[bool]:
    """Computes a boolean array indicating whether each candidate is Pareto-optimal (non-dominated).

    Returns a list of booleans of identical length where True means the candidate
    belongs to the Pareto frontier.
    """
    n = len(metrics_list)
    if n <= 1:
        return [True] * n

    is_pareto = [True] * n

    for i in range(n):
        for j in range(n):
            if i != j and dominates(metrics_list[j], metrics_list[i]):
                is_pareto[i] = False
                break

    return is_pareto
