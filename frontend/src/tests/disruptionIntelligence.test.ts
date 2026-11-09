/**
 * frontend/src/tests/disruptionIntelligence.test.ts
 *
 * Comprehensive Frontend Test Suite for Real-Time Journey Disruption Intelligence (Milestone M3.7).
 * Tests disruption types, client-side impact evaluation, disrupted transfer readiness calculations,
 * recovery recommendations, and mandatory safety invariants.
 */
import assert from 'node:assert';
import {
  getDisruptionProviders,
  getActiveDisruptions,
  assessJourneyDisruptions,
  recoverDisruptedJourney,
} from '../api/disruptions';
import { calculateDisruptedTransferReadiness } from '../services/navigation/transferReadiness';
import type { Journey, JourneySegment } from '../types/journey';
import type {
  DisruptionEvent,
  JourneyDisruptionAssessment,
  RecoveryRecommendation,
} from '../types/disruption';

console.log('=================================================================');
console.log('RUNNING DISRUPTION INTELLIGENCE & RECOVERY TEST SUITE (M3.7)');
console.log('=================================================================');

// --- Fixtures ---
const mockOrigin = {
  id: 'loc-silkboard',
  name: 'Central Silk Board',
  city: 'Bengaluru',
  type: 'landmark' as const,
  coordinates: { lat: 12.9176, lng: 77.6238 },
};

const mockKsr = {
  id: 'loc-ksr',
  name: 'KSR Bengaluru Station',
  city: 'Bengaluru',
  type: 'railway_station' as const,
  coordinates: { lat: 12.9781, lng: 77.5695 },
};

const mockMangaluru = {
  id: 'loc-mangaluru',
  name: 'Mangaluru Central',
  city: 'Mangaluru',
  type: 'railway_station' as const,
  coordinates: { lat: 12.8698, lng: 74.8430 },
};

const mockUdupi = {
  id: 'loc-udupi',
  name: 'Udupi City Stand',
  city: 'Udupi',
  type: 'bus_terminal' as const,
  coordinates: { lat: 13.3409, lng: 74.7421 },
};

const nowMs = Date.now();
const t0 = new Date(nowMs + 600000).toISOString();
const t1 = new Date(nowMs + 3300000).toISOString(); // 45 min
const t2 = new Date(nowMs + 4500000).toISOString(); // 20 min transfer buffer
const t3 = new Date(nowMs + 22500000).toISOString(); // 300 min
const t4 = new Date(nowMs + 24300000).toISOString(); // 30 min transfer buffer
const t5 = new Date(nowMs + 27900000).toISOString(); // 60 min

const seg1: JourneySegment = {
  segmentId: 'seg-1-cab',
  sequence: 1,
  mode: 'cab',
  provider: 'Ola Cabs',
  origin: mockOrigin,
  destination: mockKsr,
  departureTime: t0,
  arrivalTime: t1,
  durationMinutes: 45,
  price: 350,
  currency: 'INR',
  distanceKm: 15,
  carbonKg: 3.2,
  comfortScore: 7.5,
  transferBufferMinutes: 20,
  availability: { status: 'available', remainingUnits: 10, isRealInventory: false },
};

const seg2: JourneySegment = {
  segmentId: 'seg-2-road',
  sequence: 2,
  mode: 'bus',
  provider: 'KSRTC FlyBus',
  origin: mockKsr,
  destination: mockMangaluru,
  departureTime: t2,
  arrivalTime: t3,
  durationMinutes: 300,
  price: 850,
  currency: 'INR',
  distanceKm: 350,
  carbonKg: 14.5,
  comfortScore: 8.0,
  transferBufferMinutes: 30,
  availability: { status: 'available', remainingUnits: 10, isRealInventory: false },
};

const seg3: JourneySegment = {
  segmentId: 'seg-3-bus',
  sequence: 3,
  mode: 'bus',
  provider: 'Local Express',
  origin: mockMangaluru,
  destination: mockUdupi,
  departureTime: t4,
  arrivalTime: t5,
  durationMinutes: 60,
  price: 120,
  currency: 'INR',
  distanceKm: 55,
  carbonKg: 2.5,
  comfortScore: 6.5,
  transferBufferMinutes: 15,
  availability: { status: 'available', remainingUnits: 10, isRealInventory: false },
};

const sampleJourney: Journey = {
  id: 'jny-test-blr-udupi',
  title: 'Bengaluru to Udupi Route',
  origin: mockOrigin,
  destination: mockUdupi,
  departureTime: t0,
  arrivalTime: t5,
  totalDurationMinutes: 455,
  totalPrice: 1320,
  currency: 'INR',
  totalTransfers: 2,
  modes: ['cab', 'bus'],
  segments: [seg1, seg2, seg3],
  carbonKg: 20.2,
  comfortScore: 7.4,
  recommendationCategory: 'best_value',
  aiExplanation: {
    summary: 'Standard multimodal route',
    tradeOffs: [],
    rankReason: 'Test route',
    score: 85,
  },
  bookingFeasibility: {
    holdSupported: true,
    concurrencySafe: true,
    holdTtlSeconds: 600,
  },
};

async function runTests() {
  // ============================================================================
  // 1. DISRUPTION PROVIDER DISCOVERY & STATUS
  // ============================================================================
  console.log('\n--- 1. Provider Discovery & Capability Reporting ---');

  const capabilities = await getDisruptionProviders();
  assert.ok(Array.isArray(capabilities), 'Capabilities should be an array');
  assert.ok(capabilities.length >= 2, 'Should report at least 2 provider adapters');

  const simCap = capabilities.find((c) => c.name === 'simulation_engine');
  assert.ok(simCap, 'Simulation engine provider must be registered');
  assert.strictEqual(simCap?.isAvailable, true, 'Simulation engine should be available');
  assert.strictEqual(simCap?.provenanceSource, 'simulated');

  const liveCap = capabilities.find((c) => c.name === 'live_traffic_feed');
  assert.ok(liveCap, 'Live traffic feed provider must be registered');
  if (!liveCap?.isAvailable) {
    assert.ok(
      liveCap?.statusNotice.includes('BLOCKED'),
      'Unavailable live provider must explicitly disclose credentials block'
    );
  }
  console.log('✓ Provider capability discovery correctly reflects live & simulation status');

  // ============================================================================
  // 2. DISRUPTION EVENT TAXONOMY & NOTICE INTEGRITY
  // ============================================================================
  console.log('\n--- 2. Disruption Event Taxonomy & Provenance Notice ---');

  const events = await getActiveDisruptions({ scenario: 'shiradi_ghat' });
  assert.ok(events.length > 0, 'Should return active demonstration disruption');
  const shiradiEvent = events[0];
  assert.strictEqual(shiradiEvent.eventType, 'road_closure');
  assert.strictEqual(shiradiEvent.severity, 'critical');
  assert.strictEqual(shiradiEvent.provenance, 'simulated');
  assert.ok(
    shiradiEvent.title.includes('SIMULATED DISRUPTION — NOT LIVE PROVIDER DATA'),
    'Simulated events must visibly carry the mandatory simulation notice'
  );
  assert.strictEqual(shiradiEvent.estimatedDelayMinutes, 180);
  console.log('✓ Disruption events enforce strict taxonomy and simulation notice');

  // ============================================================================
  // 3. DISRUPTED TRANSFER READINESS & PROGRESS IMMUTABILITY
  // ============================================================================
  console.log('\n--- 3. Disrupted Transfer Readiness & Progress Invariants ---');

  // Case 3.1: Normal transfer without disruption
  const normalReadiness = calculateDisruptedTransferReadiness(seg1, seg2, 0, nowMs);
  assert.strictEqual(normalReadiness.disruptionRisk, 'safe');
  assert.strictEqual(normalReadiness.state, 'upcoming');
  assert.strictEqual(normalReadiness.badgeColor, 'emerald');

  // Case 3.2: 45 min delay on 20 min transfer buffer -> critical connection risk
  const criticalReadiness = calculateDisruptedTransferReadiness(seg1, seg2, 45, nowMs);
  assert.strictEqual(criticalReadiness.disruptionRisk, 'critical');
  assert.strictEqual(criticalReadiness.state, 'missed_estimated');
  assert.strictEqual(criticalReadiness.badgeColor, 'rose');
  assert.ok(criticalReadiness.availableBufferMinutes < 0, 'Buffer should become negative under critical delay');

  // Case 3.3: 10 min delay on 20 min transfer buffer (required buffer = 20) -> tight connection
  const tightReadiness = calculateDisruptedTransferReadiness(seg1, seg2, 10, nowMs);
  assert.strictEqual(tightReadiness.disruptionRisk, 'at_risk');
  assert.strictEqual(tightReadiness.state, 'tight_connection');
  assert.strictEqual(tightReadiness.badgeColor, 'amber');

  // Case 3.4: Completed progress is IMMUTABLE (cannot be retroactively marked missed)
  const completedIds = new Set(['seg-1-cab', 'seg-2-road']);
  const completedReadiness = calculateDisruptedTransferReadiness(seg1, seg2, 120, nowMs, completedIds);
  assert.strictEqual(completedReadiness.state, 'completed');
  assert.strictEqual(completedReadiness.badgeColor, 'emerald');
  console.log('✓ Transfer readiness correctly detects disruption risks without corrupting completed progress');

  // ============================================================================
  // 4. JOURNEY IMPACT ASSESSMENT
  // ============================================================================
  console.log('\n--- 4. Journey Impact Assessment ---');

  const assessment = await assessJourneyDisruptions({
    journey: sampleJourney,
    includeSimulated: true,
    scenario: 'shiradi_ghat',
  });

  assert.strictEqual(assessment.isDisrupted, true);
  assert.strictEqual(assessment.highestSeverity, 'critical');
  assert.strictEqual(assessment.overallImpactLevel, 'critical');
  assert.ok(assessment.totalEstimatedDelayMinutes >= 120);
  assert.ok(assessment.notice?.includes('SIMULATED DISRUPTION'));
  console.log('✓ Disruption impact assessment correctly calculates delays and connection risks');

  // ============================================================================
  // 5. PARETO RECOVERY ENGINE & SAFETY INVARIANTS
  // ============================================================================
  console.log('\n--- 5. Pareto Recovery & Booking Safety Invariants ---');

  const recoveryResponse = await recoverDisruptedJourney({
    journey: sampleJourney,
    budgetMax: 2000,
    includeSimulated: true,
    scenario: 'shiradi_ghat',
  });

  assert.strictEqual(recoveryResponse.feasibleAlternativesFound, true);
  assert.ok(recoveryResponse.recommendations.length > 0);

  const primary = recoveryResponse.primaryRecommendation;
  assert.ok(primary, 'Must provide primary recommended alternative');
  assert.strictEqual(primary?.isFeasible, true);

  // Safety Invariant: Manual Rebooking Required
  assert.strictEqual(
    primary?.manualRebookingRequired,
    true,
    'All recovery alternatives MUST require explicit manual rebooking'
  );

  // Original Journey Immutability Check
  assert.strictEqual(sampleJourney.id, 'jny-test-blr-udupi');
  assert.strictEqual(sampleJourney.totalPrice, 1320);

  // Recovered Journey Metric Deltas
  assert.ok(typeof primary?.durationDeltaMinutes === 'number');
  assert.ok(typeof primary?.priceDelta === 'number');
  assert.ok(typeof primary?.carbonDeltaKg === 'number');

  // Case 5.2: Hard Budget Constraint Rejection
  const impossibleBudgetRecovery = await recoverDisruptedJourney({
    journey: sampleJourney,
    budgetMax: 200, // Impossibly low budget
    includeSimulated: true,
    scenario: 'shiradi_ghat',
  });

  assert.strictEqual(
    impossibleBudgetRecovery.feasibleAlternativesFound,
    false,
    'Must not silently relax hard budget constraints'
  );
  assert.strictEqual(
    impossibleBudgetRecovery.primaryRecommendation?.strategy,
    'no_feasible_alternative'
  );
  console.log('✓ Recovery engine generates feasible Pareto alternatives while enforcing safety invariants');

  console.log('\n=================================================================');
  console.log('ALL DISRUPTION INTELLIGENCE (M3.7) FRONTEND TESTS PASSED (12/12)');
  console.log('=================================================================');
}

runTests().catch((err) => {
  console.error('Test suite failed:', err);
  process.exit(1);
});

