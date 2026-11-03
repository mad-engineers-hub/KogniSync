from app.services.optimizer.schemas import (
    JourneyCandidateInput,
    JourneyOptimizationMetrics,
    JourneyRecommendationExplanation,
)


def format_duration_short(mins: int) -> str:
    h = mins // 60
    m = mins % 60
    if h > 0 and m > 0:
        return f"{h}h {m}m"
    elif h > 0:
        return f"{h}h"
    return f"{m}m"


def generate_deterministic_explanation(
    candidate: JourneyCandidateInput,
    metrics: JourneyOptimizationMetrics,
    all_candidates: list[JourneyCandidateInput],
    all_metrics: list[JourneyOptimizationMetrics],
    weights: dict[str, float],
    budget_max: float | None = None,
    is_winner: bool = False,
) -> JourneyRecommendationExplanation:
    """Generates traceable, human-readable reasons and trade-offs comparing candidate to baseline options."""
    reasons: list[str] = []
    tradeoffs: list[str] = []

    # Find cheapest and fastest baselines
    cheapest_idx = min(range(len(all_metrics)), key=lambda i: all_metrics[i].total_cost)
    fastest_idx = min(range(len(all_metrics)), key=lambda i: all_metrics[i].duration_minutes)
    greenest_idx = min(range(len(all_metrics)), key=lambda i: all_metrics[i].carbon_kg)

    cheapest_cand = all_candidates[cheapest_idx]
    cheapest_met = all_metrics[cheapest_idx]

    fastest_cand = all_candidates[fastest_idx]
    fastest_met = all_metrics[fastest_idx]

    greenest_met = all_metrics[greenest_idx]

    # Headline determination
    cost_wt = weights.get("cost", 0.4)
    dur_wt = weights.get("duration", 0.3)
    carb_wt = weights.get("carbon", 0.1)
    comf_wt = weights.get("comfort", 0.2)

    if candidate.id == cheapest_cand.id:
        headline = "Lowest cost multi-modal itinerary"
        reasons.append(f"Guaranteed lowest fare: ₹{int(metrics.total_cost):,}")
    elif candidate.id == fastest_cand.id:
        headline = "Fastest door-to-door corridor"
        reasons.append(f"Shortest transit duration: {format_duration_short(metrics.duration_minutes)}")
    elif dur_wt >= 0.45 or (dur_wt > cost_wt and dur_wt >= 0.38):
        headline = "Best match for your priority for speed"
    elif cost_wt >= 0.45 or (cost_wt > dur_wt and cost_wt >= 0.38):
        headline = "Best match for your budget and cost savings"
    elif carb_wt >= 0.30:
        headline = "Eco-conscious choice with minimal carbon emissions"
    elif comf_wt >= 0.30:
        headline = "Maximized passenger comfort & premium transit link"
    else:
        headline = "Best overall balance of cost, time and comfort"

    # 1. Comparison vs Cheapest Option
    if metrics.total_cost == cheapest_met.total_cost:
        reasons.append("Zero premium: matches lowest fare on this route")
    else:
        dur_saved = cheapest_met.duration_minutes - metrics.duration_minutes
        if dur_saved > 15:
            reasons.append(f"{format_duration_short(dur_saved)} faster than the cheapest option ({cheapest_cand.title})")
        extra_cost = int(metrics.total_cost - cheapest_met.total_cost)
        tradeoffs.append(f"Costs ₹{extra_cost:,} more than the cheapest option ({cheapest_cand.title})")

    # 2. Comparison vs Fastest Option
    if metrics.duration_minutes == fastest_met.duration_minutes:
        if candidate.id != fastest_cand.id:
            reasons.append("Matches the fastest flight speed on this corridor")
    else:
        extra_dur = metrics.duration_minutes - fastest_met.duration_minutes
        if extra_dur > 20:
            tradeoffs.append(f"Takes {format_duration_short(extra_dur)} longer than the express route ({fastest_cand.title})")
        cost_saved = int(fastest_met.total_cost - metrics.total_cost)
        if cost_saved > 200:
            reasons.append(f"Saves ₹{cost_saved:,} compared to the express flight route")

    # 3. Budget headroom
    if budget_max is not None and budget_max > 0:
        under_budget = int(budget_max - metrics.total_cost)
        if under_budget >= 0:
            reasons.append(f"₹{under_budget:,} under your specified budget limit of ₹{int(budget_max):,}")
        else:
            tradeoffs.append(f"Exceeds target budget by ₹{-under_budget:,}")

    # 4. Transfers
    if metrics.transfer_count == 0:
        reasons.append("Direct journey with 0 transfers")
    elif metrics.transfer_count <= 2:
        reasons.append(f"Only {metrics.transfer_count} seamless intermodal transfers")
    else:
        tradeoffs.append(f"Requires {metrics.transfer_count} transfers across transit hubs")

    # 5. Carbon & Environmental
    if greenest_met.carbon_kg > 0:
        if metrics.carbon_kg == greenest_met.carbon_kg:
            reasons.append(f"Lowest carbon emissions: {metrics.carbon_kg} kg CO₂")
        elif metrics.carbon_kg <= greenest_met.carbon_kg * 1.3:
            reasons.append(f"Eco-friendly profile: {metrics.carbon_kg} kg CO₂")

    # 6. Comfort
    comfort_pct = int(round(metrics.comfort_score * 100))
    if comfort_pct >= 80:
        reasons.append(f"High passenger comfort score: {comfort_pct}%")

    # Keep reasons clean (3-5 max)
    if len(reasons) > 4:
        reasons = reasons[:4]
    if len(tradeoffs) > 3:
        tradeoffs = tradeoffs[:3]

    return JourneyRecommendationExplanation(
        headline=headline,
        reasons=reasons,
        tradeoffs=tradeoffs,
        compared_against=cheapest_cand.title if candidate.id != cheapest_cand.id else fastest_cand.title,
    )
