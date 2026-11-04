from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict, AliasChoices


class JourneyOptimizationMetrics(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    total_cost: float = Field(..., validation_alias=AliasChoices("total_cost", "totalCost"))
    duration_minutes: int = Field(..., validation_alias=AliasChoices("duration_minutes", "durationMinutes"))
    transfer_count: int = Field(..., validation_alias=AliasChoices("transfer_count", "transferCount"))
    comfort_score: float = Field(..., validation_alias=AliasChoices("comfort_score", "comfortScore"))  # [0, 1] or [1, 10]
    carbon_kg: float = Field(..., validation_alias=AliasChoices("carbon_kg", "carbonKg"))


class ObjectiveScoreContribution(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    raw: float
    normalized: float  # [0, 1]
    weight: float      # [0, 1]
    contribution: float  # normalized * weight


class JourneyScoreBreakdown(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    cost: ObjectiveScoreContribution
    duration: ObjectiveScoreContribution
    comfort: ObjectiveScoreContribution
    carbon: ObjectiveScoreContribution
    transfers: ObjectiveScoreContribution | None = None
    total_score: float = Field(..., validation_alias=AliasChoices("total_score", "totalScore"))  # [0, 1] or scaled 0-100


class JourneyRecommendationExplanation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    headline: str = "Best match for your priorities"
    reasons: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    compared_against: str | None = Field(default=None, validation_alias=AliasChoices("compared_against", "comparedAgainst"))


class OptimizationWeightsInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    cost: float = 0.40
    duration: float = 0.30
    comfort: float = 0.20
    carbon: float = 0.10
    transfers: float = 0.00


class JourneyCandidateInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    title: str
    total_price: float = Field(..., validation_alias=AliasChoices("total_price", "totalPrice"))
    total_duration_minutes: int = Field(..., validation_alias=AliasChoices("total_duration_minutes", "totalDurationMinutes"))
    total_transfers: int = Field(..., validation_alias=AliasChoices("total_transfers", "totalTransfers"))
    carbon_kg: float = Field(..., validation_alias=AliasChoices("carbon_kg", "carbonKg"))
    comfort_score: float = Field(..., validation_alias=AliasChoices("comfort_score", "comfortScore"))
    modes: list[str] = Field(default_factory=list)
    recommendation_category: str = Field(default="best_value", validation_alias=AliasChoices("recommendation_category", "recommendationCategory"))
    departure_time: str | None = Field(default=None, validation_alias=AliasChoices("departure_time", "departureTime"))
    arrival_time: str | None = Field(default=None, validation_alias=AliasChoices("arrival_time", "arrivalTime"))
    extra_metadata: dict[str, Any] = Field(default_factory=dict, validation_alias=AliasChoices("extra_metadata", "extraMetadata"))


class OptimizedJourneyOutput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    title: str
    score: float
    category: str
    is_pareto_optimal: bool = Field(..., validation_alias=AliasChoices("is_pareto_optimal", "isParetoOptimal"))
    pareto_rank: int = Field(default=1, validation_alias=AliasChoices("pareto_rank", "paretoRank"))
    metrics: JourneyOptimizationMetrics
    score_breakdown: JourneyScoreBreakdown = Field(..., validation_alias=AliasChoices("score_breakdown", "scoreBreakdown"))
    explanation: JourneyRecommendationExplanation


class OptimizationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    weights: OptimizationWeightsInput
    budget_max: float | None = Field(default=None, validation_alias=AliasChoices("budget_max", "budgetMax"))
    preferred_arrival_before: str | None = Field(default=None, validation_alias=AliasChoices("preferred_arrival_before", "preferredArrivalBefore"))
    candidates: list[JourneyCandidateInput]


class OptimizationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    recommended_journey_id: str = Field(..., validation_alias=AliasChoices("recommended_journey_id", "recommendedJourneyId"))
    total_candidates: int = Field(..., validation_alias=AliasChoices("total_candidates", "totalCandidates"))
    eligible_candidates: int = Field(..., validation_alias=AliasChoices("eligible_candidates", "eligibleCandidates"))
    pareto_frontier_count: int = Field(..., validation_alias=AliasChoices("pareto_frontier_count", "paretoFrontierCount"))
    journeys: list[OptimizedJourneyOutput]
