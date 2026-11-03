from typing import Sequence
from app.services.optimizer.schemas import JourneyOptimizationMetrics


def normalize_minimization(val: float, min_val: float, max_val: float) -> float:
    """Normalizes a metric where lower is better (Cost, Duration, Carbon, Transfers).

    Formula: (max - val) / (max - min), clamped to [0.0, 1.0].
    If all candidates have identical values, returns 1.0.
    """
    if max_val - min_val <= 1e-9:
        return 1.0
    normalized = (max_val - val) / (max_val - min_val)
    return max(0.0, min(1.0, round(normalized, 4)))


def normalize_maximization(val: float, min_val: float, max_val: float) -> float:
    """Normalizes a metric where higher is better (Comfort).

    Formula: (val - min) / (max - min), clamped to [0.0, 1.0].
    If all candidates have identical values, returns 1.0.
    """
    if max_val - min_val <= 1e-9:
        return 1.0
    normalized = (val - min_val) / (max_val - min_val)
    return max(0.0, min(1.0, round(normalized, 4)))


class CandidateNormalizationBounds:
    def __init__(self, metrics_list: Sequence[JourneyOptimizationMetrics]):
        if not metrics_list:
            self.min_cost = self.max_cost = 0.0
            self.min_dur = self.max_dur = 0
            self.min_transfers = self.max_transfers = 0
            self.min_comf = self.max_comf = 0.0
            self.min_carb = self.max_carb = 0.0
            return

        self.min_cost = min(m.total_cost for m in metrics_list)
        self.max_cost = max(m.total_cost for m in metrics_list)

        self.min_dur = min(m.duration_minutes for m in metrics_list)
        self.max_dur = max(m.duration_minutes for m in metrics_list)

        self.min_transfers = min(m.transfer_count for m in metrics_list)
        self.max_transfers = max(m.transfer_count for m in metrics_list)

        self.min_comf = min(m.comfort_score for m in metrics_list)
        self.max_comf = max(m.comfort_score for m in metrics_list)

        self.min_carb = min(m.carbon_kg for m in metrics_list)
        self.max_carb = max(m.carbon_kg for m in metrics_list)

    def normalize(self, m: JourneyOptimizationMetrics) -> dict[str, float]:
        return {
            "cost": normalize_minimization(m.total_cost, self.min_cost, self.max_cost),
            "duration": normalize_minimization(m.duration_minutes, self.min_dur, self.max_dur),
            "transfers": normalize_minimization(m.transfer_count, self.min_transfers, self.max_transfers),
            "comfort": normalize_maximization(m.comfort_score, self.min_comf, self.max_comf),
            "carbon": normalize_minimization(m.carbon_kg, self.min_carb, self.max_carb),
        }
