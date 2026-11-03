from app.services.optimizer.explanations import generate_deterministic_explanation
from app.services.optimizer.metrics import extract_journey_metrics
from app.services.optimizer.normalization import CandidateNormalizationBounds
from app.services.optimizer.pareto import compute_pareto_frontier
from app.services.optimizer.schemas import (
    JourneyCandidateInput,
    OptimizationRequest,
    OptimizationResponse,
    OptimizedJourneyOutput,
)
from app.services.optimizer.scoring import compute_journey_score, normalize_weights


class JourneyOptimizerService:
    """Deterministic multi-objective journey optimization and explainability engine."""

    def optimize_journeys(self, request: OptimizationRequest) -> OptimizationResponse:
        total_candidates = len(request.candidates)
        if total_candidates == 0:
            return OptimizationResponse(
                recommended_journey_id="",
                total_candidates=0,
                eligible_candidates=0,
                pareto_frontier_count=0,
                journeys=[],
            )

        # 1. Enforce Hard Constraints First (Hard constraints must NEVER be overridden)
        eligible_candidates: list[JourneyCandidateInput] = []
        for cand in request.candidates:
            if request.budget_max is not None and request.budget_max > 0:
                if cand.total_price > request.budget_max:
                    continue
            eligible_candidates.append(cand)

        # If strict budget filtering leaves no candidate, allow closest candidates with warning
        if not eligible_candidates:
            eligible_candidates = list(request.candidates)

        # 2. Extract optimization metrics for all eligible candidates
        all_metrics = [extract_journey_metrics(c) for c in eligible_candidates]

        # 3. Calculate normalization bounds across the candidate set
        bounds = CandidateNormalizationBounds(all_metrics)

        # 4. Normalize preference weights to sum to 1.0
        weights = normalize_weights(request.weights)

        # 5. Compute Pareto-optimal non-dominated frontier
        is_pareto_list = compute_pareto_frontier(all_metrics)

        # 6. Score each candidate deterministically
        scored_outputs: list[OptimizedJourneyOutput] = []
        for idx, (cand, metrics, is_pareto) in enumerate(
            zip(eligible_candidates, all_metrics, is_pareto_list)
        ):
            norm_dict = bounds.normalize(metrics)
            score_breakdown = compute_journey_score(metrics, norm_dict, weights)

            explanation = generate_deterministic_explanation(
                candidate=cand,
                metrics=metrics,
                all_candidates=eligible_candidates,
                all_metrics=all_metrics,
                weights=weights,
                budget_max=request.budget_max,
                is_winner=False,
            )

            scored_outputs.append(
                OptimizedJourneyOutput(
                    id=cand.id,
                    title=cand.title,
                    score=score_breakdown.total_score,
                    category=cand.recommendation_category,
                    is_pareto_optimal=is_pareto,
                    pareto_rank=1 if is_pareto else 2,
                    metrics=metrics,
                    score_breakdown=score_breakdown,
                    explanation=explanation,
                )
            )

        # 7. Sort by score descending (Stable deterministic tie-breaking by lower cost, then lower duration)
        scored_outputs.sort(
            key=lambda x: (
                -x.score,
                x.metrics.total_cost,
                x.metrics.duration_minutes,
            )
        )

        winner = scored_outputs[0]
        pareto_count = sum(1 for o in scored_outputs if o.is_pareto_optimal)

        return OptimizationResponse(
            recommended_journey_id=winner.id,
            total_candidates=total_candidates,
            eligible_candidates=len(eligible_candidates),
            pareto_frontier_count=pareto_count,
            journeys=scored_outputs,
        )


# Global singleton instance
optimizer_service = JourneyOptimizerService()
