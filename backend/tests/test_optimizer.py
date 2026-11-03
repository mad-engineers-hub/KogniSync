import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.optimizer.schemas import (
    JourneyCandidateInput,
    JourneyOptimizationMetrics,
    OptimizationRequest,
    OptimizationWeightsInput,
)
from app.services.optimizer.normalization import (
    normalize_minimization,
    normalize_maximization,
    CandidateNormalizationBounds,
)
from app.services.optimizer.scoring import normalize_weights, compute_journey_score
from app.services.optimizer.pareto import dominates, compute_pareto_frontier
from app.services.optimizer.service import JourneyOptimizerService

client = TestClient(app)


# ============================================================================
# 1. NORMALIZATION TESTS
# ============================================================================

def test_normalization_min_max_clamping():
    """Verify minimization and maximization normalizations clamp to [0, 1]."""
    # Lower is better (Minimization): min=100, max=500
    assert normalize_minimization(100, 100, 500) == 1.0  # Lowest cost -> best score
    assert normalize_minimization(500, 100, 500) == 0.0  # Highest cost -> worst score
    assert normalize_minimization(300, 100, 500) == 0.5  # Midpoint
    assert normalize_minimization(50, 100, 500) == 1.0   # Out of bounds lower -> clamped to 1.0
    assert normalize_minimization(600, 100, 500) == 0.0  # Out of bounds upper -> clamped to 0.0

    # Higher is better (Maximization - Comfort): min=0.4, max=0.9
    assert normalize_maximization(0.9, 0.4, 0.9) == 1.0  # Highest comfort -> best score
    assert normalize_maximization(0.4, 0.4, 0.9) == 0.0  # Lowest comfort -> worst score
    assert normalize_maximization(0.65, 0.4, 0.9) == 0.5 # Midpoint
    assert normalize_maximization(1.0, 0.4, 0.9) == 1.0  # Clamped to 1.0


def test_normalization_identical_values_and_single_candidate():
    """Verify identical candidate metrics and single-candidate sets return 1.0."""
    assert normalize_minimization(2000, 2000, 2000) == 1.0
    assert normalize_maximization(0.75, 0.75, 0.75) == 1.0

    single_m = [
        JourneyOptimizationMetrics(
            total_cost=2500, duration_minutes=300, transfer_count=1, comfort_score=0.8, carbon_kg=15.0
        )
    ]
    bounds = CandidateNormalizationBounds(single_m)
    norm = bounds.normalize(single_m[0])
    assert norm["cost"] == 1.0
    assert norm["duration"] == 1.0
    assert norm["transfers"] == 1.0
    assert norm["comfort"] == 1.0
    assert norm["carbon"] == 1.0


# ============================================================================
# 2. WEIGHT NORMALIZATION & SCORING TESTS
# ============================================================================

def test_weights_normalization():
    """Verify weights sum to exactly 1.0."""
    w = OptimizationWeightsInput(cost=4, duration=3, comfort=2, carbon=1, transfers=0)
    norm_w = normalize_weights(w)
    assert sum(norm_w.values()) == pytest.approx(1.0, abs=1e-3)
    assert norm_w["cost"] == 0.4
    assert norm_w["duration"] == 0.3

    # Zero weights fallback
    zero_w = OptimizationWeightsInput(cost=0, duration=0, comfort=0, carbon=0, transfers=0)
    norm_zero = normalize_weights(zero_w)
    assert sum(norm_zero.values()) == pytest.approx(1.0, abs=1e-3)


def test_scoring_cost_heavy_preference():
    """Verify cost-heavy preference prioritizes the lowest-cost journey."""
    m_cheap = JourneyOptimizationMetrics(total_cost=800, duration_minutes=420, transfer_count=2, comfort_score=0.6, carbon_kg=8.0)
    m_fast = JourneyOptimizationMetrics(total_cost=4500, duration_minutes=180, transfer_count=1, comfort_score=0.9, carbon_kg=35.0)

    bounds = CandidateNormalizationBounds([m_cheap, m_fast])
    cost_weights = {"cost": 0.70, "duration": 0.15, "comfort": 0.10, "carbon": 0.05, "transfers": 0.0}

    score_cheap = compute_journey_score(m_cheap, bounds.normalize(m_cheap), cost_weights)
    score_fast = compute_journey_score(m_fast, bounds.normalize(m_fast), cost_weights)

    assert score_cheap.total_score > score_fast.total_score
    assert score_cheap.cost.contribution > score_fast.cost.contribution


def test_scoring_speed_heavy_preference():
    """Verify speed-heavy preference prioritizes the fastest journey."""
    m_cheap = JourneyOptimizationMetrics(total_cost=800, duration_minutes=420, transfer_count=2, comfort_score=0.6, carbon_kg=8.0)
    m_fast = JourneyOptimizationMetrics(total_cost=4500, duration_minutes=180, transfer_count=1, comfort_score=0.9, carbon_kg=35.0)

    bounds = CandidateNormalizationBounds([m_cheap, m_fast])
    speed_weights = {"cost": 0.10, "duration": 0.70, "comfort": 0.10, "carbon": 0.10, "transfers": 0.0}

    score_cheap = compute_journey_score(m_cheap, bounds.normalize(m_cheap), speed_weights)
    score_fast = compute_journey_score(m_fast, bounds.normalize(m_fast), speed_weights)

    assert score_fast.total_score > score_cheap.total_score
    assert score_fast.duration.contribution > score_cheap.duration.contribution


# ============================================================================
# 3. PARETO OPTIMALITY & DOMINANCE TESTS
# ============================================================================

def test_pareto_obvious_dominant_journey():
    """Verify Journey A dominates Journey B when A is strictly better in all aspects."""
    a = JourneyOptimizationMetrics(total_cost=1000, duration_minutes=120, transfer_count=0, comfort_score=0.9, carbon_kg=5.0)
    b = JourneyOptimizationMetrics(total_cost=2000, duration_minutes=240, transfer_count=2, comfort_score=0.6, carbon_kg=15.0)

    assert dominates(a, b) is True
    assert dominates(b, a) is False

    frontier = compute_pareto_frontier([a, b])
    assert frontier == [True, False]  # A is in frontier, B is dominated


def test_pareto_two_non_dominated_tradeoff_journeys():
    """Verify both journeys lie on Pareto frontier when one is cheaper and the other is faster."""
    j_cheap = JourneyOptimizationMetrics(total_cost=1200, duration_minutes=360, transfer_count=1, comfort_score=0.7, carbon_kg=10.0)
    j_fast = JourneyOptimizationMetrics(total_cost=3500, duration_minutes=150, transfer_count=1, comfort_score=0.85, carbon_kg=25.0)

    assert dominates(j_cheap, j_fast) is False
    assert dominates(j_fast, j_cheap) is False

    frontier = compute_pareto_frontier([j_cheap, j_fast])
    assert frontier == [True, True]  # Both are Pareto-optimal!


def test_pareto_multiple_frontier_and_dominated():
    """Verify Pareto frontier filters out strictly inferior choices."""
    j1 = JourneyOptimizationMetrics(total_cost=500, duration_minutes=300, transfer_count=1, comfort_score=0.7, carbon_kg=10.0) # Cheapest
    j2 = JourneyOptimizationMetrics(total_cost=2000, duration_minutes=120, transfer_count=0, comfort_score=0.9, carbon_kg=20.0) # Fastest
    j3 = JourneyOptimizationMetrics(total_cost=800, duration_minutes=250, transfer_count=1, comfort_score=0.8, carbon_kg=5.0)   # Greenest
    j_bad = JourneyOptimizationMetrics(total_cost=2500, duration_minutes=350, transfer_count=2, comfort_score=0.5, carbon_kg=30.0) # Dominated by all

    frontier = compute_pareto_frontier([j1, j2, j3, j_bad])
    assert frontier == [True, True, True, False]


# ============================================================================
# 4. HARD CONSTRAINTS & OPTIMIZER SERVICE TESTS
# ============================================================================

def test_hard_constraint_budget_exclusion():
    """Verify that a journey exceeding budget ceiling never wins, even if score would be high."""
    service = JourneyOptimizerService()
    c_cheap = JourneyCandidateInput(
        id="c-cheap", title="Economy Train", total_price=1200, total_duration_minutes=360, total_transfers=1, carbon_kg=8.0, comfort_score=7.0
    )
    c_expensive = JourneyCandidateInput(
        id="c-expensive", title="Luxury Flight", total_price=6000, total_duration_minutes=100, total_transfers=0, carbon_kg=30.0, comfort_score=9.5
    )

    req = OptimizationRequest(
        weights=OptimizationWeightsInput(cost=0.1, duration=0.8, comfort=0.1, carbon=0.0),
        budget_max=4000.0,  # Luxury Flight exceeds budget!
        candidates=[c_cheap, c_expensive],
    )

    res = service.optimize_journeys(req)
    assert res.recommended_journey_id == "c-cheap"
    assert len(res.journeys) == 1
    assert res.journeys[0].id == "c-cheap"


def test_explanations_traceability_and_budget_comparison():
    """Verify deterministic explanations generate traceable reasons, budget diffs, and trade-offs."""
    service = JourneyOptimizerService()
    c1 = JourneyCandidateInput(
        id="c1", title="Bus Feeder", total_price=800, total_duration_minutes=420, total_transfers=1, carbon_kg=6.0, comfort_score=6.0
    )
    c2 = JourneyCandidateInput(
        id="c2", title="Express Air", total_price=4200, total_duration_minutes=150, total_transfers=1, carbon_kg=28.0, comfort_score=8.5
    )

    req = OptimizationRequest(
        weights=OptimizationWeightsInput(cost=0.15, duration=0.70, comfort=0.10, carbon=0.05),
        budget_max=5000.0,
        candidates=[c1, c2],
    )

    res = service.optimize_journeys(req)
    winner = res.journeys[0]
    assert winner.id == "c2"

    exp = winner.explanation
    assert len(exp.reasons) > 0
    # Must mention time saved over cheapest
    has_faster_reason = any("faster than the cheapest" in r for r in exp.reasons)
    assert has_faster_reason is True
    # Must mention budget limit
    has_budget_reason = any("under your specified budget" in r for r in exp.reasons)
    assert has_budget_reason is True
    # Must mention trade-off (costs more than cheapest)
    has_tradeoff = any("Costs" in t and "more than the cheapest" in t for t in exp.tradeoffs)
    assert has_tradeoff is True


def test_deterministic_repeatability():
    """Verify identical inputs yield 100% byte-for-byte identical scores, frontier, and winner."""
    service = JourneyOptimizerService()
    c1 = JourneyCandidateInput(id="c1", title="Route A", total_price=1500, total_duration_minutes=300, total_transfers=1, carbon_kg=12.0, comfort_score=7.5)
    c2 = JourneyCandidateInput(id="c2", title="Route B", total_price=2200, total_duration_minutes=210, total_transfers=1, carbon_kg=16.0, comfort_score=8.0)

    req = OptimizationRequest(
        weights=OptimizationWeightsInput(cost=0.4, duration=0.3, comfort=0.2, carbon=0.1),
        candidates=[c1, c2],
    )

    res1 = service.optimize_journeys(req)
    res2 = service.optimize_journeys(req)

    assert res1.recommended_journey_id == res2.recommended_journey_id
    assert res1.journeys[0].score == res2.journeys[0].score
    assert res1.journeys[0].is_pareto_optimal == res2.journeys[0].is_pareto_optimal
    assert res1.journeys[0].explanation.headline == res2.journeys[0].explanation.headline


# ============================================================================
# 5. API ENDPOINT TESTS
# ============================================================================

def test_api_optimize_endpoint_success():
    """Verify POST /api/v1/optimizer/optimize returns 200 with structured optimization data."""
    payload = {
        "weights": {"cost": 0.4, "duration": 0.3, "comfort": 0.2, "carbon": 0.1, "transfers": 0.0},
        "budget_max": 5000,
        "candidates": [
            {
                "id": "jny-1",
                "title": "Superfast Rail",
                "total_price": 1200,
                "total_duration_minutes": 380,
                "total_transfers": 1,
                "carbon_kg": 9.5,
                "comfort_score": 7.5,
                "modes": ["bus", "train", "cab"],
            },
            {
                "id": "jny-2",
                "title": "Air Express Link",
                "total_price": 4500,
                "total_duration_minutes": 210,
                "total_transfers": 2,
                "carbon_kg": 24.0,
                "comfort_score": 8.8,
                "modes": ["cab", "flight", "cab"],
            },
        ],
    }

    response = client.post("/api/v1/optimizer/optimize", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "recommended_journey_id" in data
    assert data["total_candidates"] == 2
    assert len(data["journeys"]) == 2
    assert "score_breakdown" in data["journeys"][0]
    assert "explanation" in data["journeys"][0]
    assert "is_pareto_optimal" in data["journeys"][0]


def test_api_optimize_endpoint_empty_candidates_rejection():
    """Verify endpoint rejects empty candidates with 400 Bad Request."""
    payload = {
        "weights": {"cost": 0.5, "duration": 0.5},
        "candidates": [],
    }
    response = client.post("/api/v1/optimizer/optimize", json=payload)
    assert response.status_code == 400


def test_optimizer_hard_budget_constraint_no_silent_relaxation():
    """Verify optimizer strictly returns 0 eligible candidates when all exceed budget."""
    service = JourneyOptimizerService()
    c1 = JourneyCandidateInput(
        id="c1",
        title="Route A",
        total_price=2500,
        total_duration_minutes=300,
        total_transfers=1,
        carbon_kg=12.0,
        comfort_score=7.5,
    )
    c2 = JourneyCandidateInput(
        id="c2",
        title="Route B",
        total_price=3500,
        total_duration_minutes=210,
        total_transfers=1,
        carbon_kg=16.0,
        comfort_score=8.0,
    )

    req = OptimizationRequest(
        weights=OptimizationWeightsInput(cost=0.5, duration=0.5),
        budget_max=1000,  # Both c1 and c2 exceed ₹1000
        candidates=[c1, c2],
    )

    res = service.optimize_journeys(req)
    assert res.total_candidates == 2
    assert res.eligible_candidates == 0
    assert res.pareto_frontier_count == 0
    assert len(res.journeys) == 0
    assert res.recommended_journey_id == ""


def test_optimizer_hard_arrival_deadline_constraint():
    """Verify optimizer excludes candidates arriving after preferred deadline."""
    service = JourneyOptimizerService()
    c1 = JourneyCandidateInput(
        id="c1",
        title="On-Time Route",
        total_price=1500,
        total_duration_minutes=180,
        total_transfers=0,
        carbon_kg=8.0,
        comfort_score=7.5,
        arrival_time="2026-11-04T16:00:00",
    )
    c2 = JourneyCandidateInput(
        id="c2",
        title="Late Route",
        total_price=1000,
        total_duration_minutes=240,
        total_transfers=1,
        carbon_kg=10.0,
        comfort_score=6.5,
        arrival_time="2026-11-04T20:00:00",
    )

    req = OptimizationRequest(
        weights=OptimizationWeightsInput(cost=0.5, duration=0.5),
        preferred_arrival_before="2026-11-04T18:00:00",
        candidates=[c1, c2],
    )

    res = service.optimize_journeys(req)
    assert res.total_candidates == 2
    assert res.eligible_candidates == 1
    assert len(res.journeys) == 1
    assert res.journeys[0].id == "c1"
