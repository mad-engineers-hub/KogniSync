from typing import Any, Literal
from pydantic import BaseModel, Field


class JourneyOptimizationMetrics(BaseModel):
    total_cost: float
    duration_minutes: int
    transfer_count: int
    comfort_score: float  # [0, 1] or [1, 10]
    carbon_kg: float


class ObjectiveScoreContribution(BaseModel):
    raw: float
    normalized: float  # [0, 1]
    weight: float      # [0, 1]
    contribution: float  # normalized * weight


class JourneyScoreBreakdown(BaseModel):
    cost: ObjectiveScoreContribution
    duration: ObjectiveScoreContribution
    comfort: ObjectiveScoreContribution
    carbon: ObjectiveScoreContribution
    transfers: ObjectiveScoreContribution | None = None
    total_score: float  # [0, 1] or scaled 0-100


class JourneyRecommendationExplanation(BaseModel):
    headline: str = "Best match for your priorities"
    reasons: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    compared_against: str | None = None


class OptimizationWeightsInput(BaseModel):
    cost: float = 0.40
    duration: float = 0.30
    comfort: float = 0.20
    carbon: float = 0.10
    transfers: float = 0.00


class JourneyCandidateInput(BaseModel):
    id: str
    title: str
    total_price: float
    total_duration_minutes: int
    total_transfers: int
    carbon_kg: float
    comfort_score: float
    modes: list[str] = Field(default_factory=list)
    recommendation_category: str = "best_value"
    departure_time: str | None = None
    arrival_time: str | None = None
    extra_metadata: dict[str, Any] = Field(default_factory=dict)


class OptimizedJourneyOutput(BaseModel):
    id: str
    title: str
    score: float
    category: str
    is_pareto_optimal: bool
    pareto_rank: int = 1
    metrics: JourneyOptimizationMetrics
    score_breakdown: JourneyScoreBreakdown
    explanation: JourneyRecommendationExplanation


class OptimizationRequest(BaseModel):
    weights: OptimizationWeightsInput
    budget_max: float | None = None
    preferred_arrival_before: str | None = None
    candidates: list[JourneyCandidateInput]


class OptimizationResponse(BaseModel):
    recommended_journey_id: str
    total_candidates: int
    eligible_candidates: int
    pareto_frontier_count: int
    journeys: list[OptimizedJourneyOutput]
