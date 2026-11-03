import assert from 'node:assert';
import {
  deriveJourneyComfortScore,
  normalizeMinimization,
  normalizeMaximization,
  normalizeWeights,
  dominates,
  computeParetoFrontier,
  computeJourneyScore,
  generateDeterministicExplanation,
  optimizeCandidateJourneys,
  getNormalizationBounds,
  normalizeMetrics,
} from '../utils/optimizer';
import { composeMultiModalJourneys } from '../api/orchestrationEngine';
import { JourneyOptimizationMetrics } from '../types/optimizer';
import { TravelRequest } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING EXPLAINABLE OPTIMIZER & PARETO COMPARISON TEST SUITE');
console.log('=================================================================');

// ============================================================================
// TEST 1: Normalization Formulations
// ============================================================================
console.log('\n--- Test 1: Normalization (Minimization vs Maximization) ---');
// Minimization (lower is better: 100 is best, 500 is worst)
assert.strictEqual(normalizeMinimization(100, 100, 500), 1.0);
assert.strictEqual(normalizeMinimization(500, 100, 500), 0.0);
assert.strictEqual(normalizeMinimization(300, 100, 500), 0.5);
// Identical values return 1.0
assert.strictEqual(normalizeMinimization(200, 200, 200), 1.0);

// Maximization (higher is better: 1.0 is best, 0.0 is worst)
assert.strictEqual(normalizeMaximization(1.0, 0.0, 1.0), 1.0);
assert.strictEqual(normalizeMaximization(0.0, 0.0, 1.0), 0.0);
assert.strictEqual(normalizeMaximization(0.5, 0.0, 1.0), 0.5);
assert.strictEqual(normalizeMaximization(0.8, 0.8, 0.8), 1.0);
console.log('✓ Normalization correctly handles boundary, proportional, and degenerate min/max bounds.');

// ============================================================================
// TEST 2: Weight Normalization
// ============================================================================
console.log('\n--- Test 2: Weight Normalization ---');
const normalizedW = normalizeWeights({ cost: 2, duration: 1, comfort: 1, carbon: 0, transfers: 0 });
const sumW = normalizedW.cost + normalizedW.duration + normalizedW.comfort + normalizedW.carbon + normalizedW.transfers;
assert(Math.abs(sumW - 1.0) < 1e-3, `Weights must sum to 1.0, got ${sumW}`);
assert(normalizedW.cost > normalizedW.duration, 'Cost weight must be higher than duration');

const defaultW = normalizeWeights({ cost: 0, duration: 0, comfort: 0, carbon: 0, transfers: 0 });
assert.strictEqual(defaultW.cost, 0.40, 'Fallback default cost weight must be 0.40');
console.log('✓ Preference weight normalization guarantees convex linear combinations.');

// ============================================================================
// TEST 3: Deterministic Comfort Rating & Penalties
// ============================================================================
console.log('\n--- Test 3: Deterministic Comfort Scoring & Penalties ---');
const flightComfort = deriveJourneyComfortScore(['flight'], 0, 120);
const busComfort = deriveJourneyComfortScore(['bus'], 0, 120);
assert(flightComfort > busComfort, `Flight comfort (${flightComfort}) must exceed bus comfort (${busComfort})`);

const transferPenaltyComfort = deriveJourneyComfortScore(['train'], 3, 240);
const directTrainComfort = deriveJourneyComfortScore(['train'], 0, 240);
assert(directTrainComfort > transferPenaltyComfort, 'Direct journey must have higher comfort than 3-transfer journey');

const longDurationComfort = deriveJourneyComfortScore(['train'], 0, 720); // 12 hours
assert(directTrainComfort > longDurationComfort, 'Excessive duration must penalize comfort');
console.log(`✓ Comfort scores reflect transport modes and penalize transfers/fatigue cleanly (${flightComfort} vs ${busComfort}).`);

// ============================================================================
// TEST 4: Pareto Dominance & Non-Dominated Frontier
// ============================================================================
console.log('\n--- Test 4: Pareto Dominance Logic ---');
// Candidate A dominates Candidate B in all dimensions
const candA: JourneyOptimizationMetrics = {
  totalCost: 1000,
  durationMinutes: 120,
  transferCount: 1,
  comfortScore: 0.85,
  carbonKg: 20.0,
};
const candB: JourneyOptimizationMetrics = {
  totalCost: 1500,
  durationMinutes: 180,
  transferCount: 2,
  comfortScore: 0.70,
  carbonKg: 30.0,
};
assert.strictEqual(dominates(candA, candB), true, 'A must strictly dominate B');
assert.strictEqual(dominates(candB, candA), false, 'B cannot dominate A');

// Candidate C has a trade-off: cheaper than A, but slower than A
const candC: JourneyOptimizationMetrics = {
  totalCost: 600,
  durationMinutes: 240,
  transferCount: 1,
  comfortScore: 0.80,
  carbonKg: 15.0,
};
assert.strictEqual(dominates(candA, candC), false, 'A cannot dominate C because C is cheaper');
assert.strictEqual(dominates(candC, candA), false, 'C cannot dominate A because A is faster');

const frontier = computeParetoFrontier([candA, candB, candC]);
// candA is optimal, candB is dominated by candA, candC is optimal
assert.strictEqual(frontier[0], true, 'candA must be Pareto optimal');
assert.strictEqual(frontier[1], false, 'candB must be dominated');
assert.strictEqual(frontier[2], true, 'candC must be Pareto optimal');
console.log('✓ Multi-objective Pareto frontier correctly identifies dominated and non-dominated choices.');

// ============================================================================
// TEST 5: Speed Priority vs Cost Priority Journey Ranking
// ============================================================================
console.log('\n--- Test 5: Speed-Heavy vs Cost-Heavy Optimization Ranking ---');
const baseReq: TravelRequest = {
  origin: 'Chennai',
  destination: 'Udupi',
  departureDate: '2026-11-04',
  passengersCount: 1,
  weights: { cost: 0.1, duration: 0.7, comfort: 0.1, carbon: 0.1 },
  naturalLanguageQuery: 'Chennai to Udupi urgent fastest',
};

const speedJourneys = composeMultiModalJourneys(baseReq);
assert(speedJourneys.length > 0, 'Journeys must be returned');
const speedWinner = speedJourneys[0];
assert.strictEqual(speedWinner.recommendationCategory, 'fastest', `Speed-heavy search must recommend fastest option, got ${speedWinner.recommendationCategory}`);
assert(speedWinner.isParetoOptimal, 'Winner must be Pareto optimal');
assert(speedWinner.optimization !== undefined, 'Optimization output must be attached');
assert(speedWinner.optimization.scoreBreakdown.duration.contribution > speedWinner.optimization.scoreBreakdown.cost.contribution, 'Duration contribution must dominate');

// Now switch to cost-heavy weights
const costReq: TravelRequest = {
  ...baseReq,
  weights: { cost: 0.8, duration: 0.1, comfort: 0.05, carbon: 0.05 },
  naturalLanguageQuery: 'Chennai to Udupi cheapest on a budget',
};
const costJourneys = composeMultiModalJourneys(costReq);
const costWinner = costJourneys[0];
assert.strictEqual(costWinner.recommendationCategory, 'cheapest', `Cost-heavy search must recommend cheapest option, got ${costWinner.recommendationCategory}`);
assert(costWinner.totalPrice < speedWinner.totalPrice, 'Cost winner must be cheaper than speed winner');
console.log(`✓ Objective weighting deterministically steers winner (Speed: ${speedWinner.title} [₹${speedWinner.totalPrice}] vs Cost: ${costWinner.title} [₹${costWinner.totalPrice}]).`);

// ============================================================================
// TEST 6: Hard Budget Constraint Enforcement
// ============================================================================
console.log('\n--- Test 6: Hard Budget Constraint Enforcement ---');
const budgetReq: TravelRequest = {
  origin: 'Bangalore',
  destination: 'Goa',
  departureDate: '2026-11-04',
  passengersCount: 1,
  budgetMax: 2000, // Flight is ~₹4,000+ so it must be pruned
  weights: { cost: 0.3, duration: 0.5, comfort: 0.1, carbon: 0.1 },
  naturalLanguageQuery: 'Bangalore to Goa budget 2000',
};

const budgetJourneys = composeMultiModalJourneys(budgetReq);
for (const j of budgetJourneys) {
  assert(j.totalPrice <= 2000, `Journey ${j.id} exceeds budget limit ₹2000: ₹${j.totalPrice}`);
}
assert(
  !budgetJourneys.some((j) => j.recommendationCategory === 'fastest'),
  'Express flight exceeding budget must be excluded from recommendations'
);
console.log(`✓ Strict budget constraint pruned all options above ₹2,000; remaining options: ${budgetJourneys.length}`);

// ============================================================================
// TEST 7: Traceable Explanations & Reproducibility
// ============================================================================
console.log('\n--- Test 7: Traceable Deterministic Explanations & Reproducibility ---');
const run1 = composeMultiModalJourneys(baseReq);
const run2 = composeMultiModalJourneys(baseReq);

assert.strictEqual(run1.length, run2.length, 'Output count must be identical');
for (let i = 0; i < run1.length; i++) {
  assert.strictEqual(run1[i].id, run2[i].id, `Journey order must be deterministic at index ${i}`);
  assert.strictEqual(run1[i].aiExplanation.score, run2[i].aiExplanation.score, `Scores must match exactly at index ${i}`);
  assert.strictEqual(run1[i].optimization?.score, run2[i].optimization?.score, `Raw scores must match exactly at index ${i}`);
}

const explanation = run1[0].optimization?.explanation;
assert(explanation !== undefined, 'Explanation must exist');
assert(explanation.headline.length > 5, `Headline must be descriptive: ${explanation.headline}`);
assert(explanation.reasons.length > 0, 'Must include specific reasons');
console.log(`✓ Winner explanation headline: "${explanation.headline}"`);
console.log(`✓ Reasons: ${explanation.reasons.join(' | ')}`);
console.log(`✓ Trade-offs: ${explanation.tradeoffs.join(' | ')}`);
console.log('✓ 100% deterministic reproducibility verified across repeated executions.');

console.log('\n=================================================================');
console.log('ALL EXPLAINABLE OPTIMIZER TESTS PASSED (7/7)');
console.log('=================================================================');
