from app.services.optimizer.schemas import (
    JourneyOptimizationMetrics,
    ObjectiveScoreContribution,
    JourneyScoreBreakdown,
    JourneyRecommendationExplanation,
    OptimizationWeightsInput,
    JourneyCandidateInput,
    OptimizedJourneyOutput,
    OptimizationRequest,
    OptimizationResponse,
)
from app.services.optimizer.metrics import (
    CARBON_FACTORS_KG_PER_KM,
    BASE_MODE_COMFORT,
    compute_segment_carbon_kg,
    derive_journey_comfort_score,
    extract_journey_metrics,
)
from app.services.optimizer.normalization import (
    normalize_minimization,
    normalize_maximization,
    CandidateNormalizationBounds,
)
from app.services.optimizer.scoring import normalize_weights, compute_journey_score
from app.services.optimizer.pareto import dominates, compute_pareto_frontier
from app.services.optimizer.explanations import generate_deterministic_explanation
from app.services.optimizer.service import JourneyOptimizerService, optimizer_service

__all__ = [
    "JourneyOptimizationMetrics",
    "ObjectiveScoreContribution",
    "JourneyScoreBreakdown",
    "JourneyRecommendationExplanation",
    "OptimizationWeightsInput",
    "JourneyCandidateInput",
    "OptimizedJourneyOutput",
    "OptimizationRequest",
    "OptimizationResponse",
    "CARBON_FACTORS_KG_PER_KM",
    "BASE_MODE_COMFORT",
    "compute_segment_carbon_kg",
    "derive_journey_comfort_score",
    "extract_journey_metrics",
    "normalize_minimization",
    "normalize_maximization",
    "CandidateNormalizationBounds",
    "normalize_weights",
    "compute_journey_score",
    "dominates",
    "compute_pareto_frontier",
    "generate_deterministic_explanation",
    "JourneyOptimizerService",
    "optimizer_service",
]
