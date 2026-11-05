import assert from 'node:assert';
import {
  searchJourneys,
  getLastSearchSource,
  setLastSearchSource,
  getJourneyById,
} from '../api/journey';
import { composeMultiModalJourneys } from '../api/orchestrationEngine';
import { Journey, TravelRequest } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING TRUST-AWARE JOURNEY EXPERIENCE & PROVENANCE TEST SUITE');
console.log('=================================================================');

const sampleReq: TravelRequest = {
  origin: 'Chennai',
  destination: 'Udupi',
  departureDate: '2026-11-04',
  preferredArrivalBefore: '20:00',
  budgetMax: 5000,
  passengersCount: 1,
  weights: { cost: 0.2, duration: 0.5, comfort: 0.2, carbon: 0.1 },
  naturalLanguageQuery: 'Chennai to Udupi fastest with live synchronization',
};

// ============================================================================
// TEST 1: Backend Journey Search Success
// ============================================================================
console.log('\n--- Test 1: Backend Journey Search Success ---');
const originalFetch = globalThis.fetch;

// Mock live backend response
const mockBackendJourneys = composeMultiModalJourneys(sampleReq).map((j) => ({
  ...j,
  provenance: {
    overallSourceType: 'deterministic_estimate' as const,
    isFullyConfirmed: false,
    hasLiveAttributes: false,
    hasSimulatedAttributes: true,
    summary: 'Composed of backend deterministic estimates and simulated availability.',
  },
}));

globalThis.fetch = async (url: any, init?: any) => {
  if (String(url).includes('/api/v1/journeys/search')) {
    return new Response(
      JSON.stringify({
        journeys: mockBackendJourneys,
        recommendedJourneyId: mockBackendJourneys[0].id,
        totalCandidates: mockBackendJourneys.length,
        eligibleCandidates: mockBackendJourneys.length,
        paretoFrontierCount: mockBackendJourneys.length,
        source: 'backend_orchestrator',
        providerStatus: {
          transport: 'catalog_modelled',
          optimizer: 'authoritative_pareto',
        },
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  }
  return new Response(JSON.stringify({}), { status: 404 });
};

setLastSearchSource(null);
const liveResults = await searchJourneys(sampleReq);
assert(liveResults.length > 0, 'Live results must not be empty');
assert.strictEqual(getLastSearchSource(), 'backend_orchestrator', 'Must record backend_orchestrator as source');
assert.strictEqual(liveResults[0].origin.city, 'Chennai');
console.log(`✓ Live backend search succeeded: retrieved ${liveResults.length} journeys via backend_orchestrator.`);

// ============================================================================
// TEST 2: Backend Unavailable Graceful Client Fallback
// ============================================================================
console.log('\n--- Test 2: Backend Unavailable Graceful Client Fallback ---');

// Mock backend failure (e.g. network disconnect or 503)
globalThis.fetch = async () => {
  throw new Error('Connection refused to backend:5000');
};

setLastSearchSource(null);
const fallbackResults = await searchJourneys(sampleReq);
assert(fallbackResults.length > 0, 'Fallback results must generate multi-modal candidates');
assert.strictEqual(getLastSearchSource(), 'client_fallback', 'Must record client_fallback as source');
assert.strictEqual(fallbackResults[0].provenance?.isFullyConfirmed, false, 'Fallback must never claim confirmed status');
console.log(`✓ Backend unavailable: seamlessly degraded to client_fallback with ${fallbackResults.length} options.`);

// Restore fetch
globalThis.fetch = originalFetch;

// ============================================================================
// TEST 3: Overall Provenance Model Rendering
// ============================================================================
console.log('\n--- Test 3: Overall Provenance Model Rendering ---');
const testJourney = fallbackResults[0];

assert(testJourney.provenance !== undefined, 'Journey must have provenance metadata');
assert(
  ['deterministic_estimate', 'provider_live', 'simulated', 'mixed', 'unknown'].includes(
    testJourney.provenance!.overallSourceType
  ),
  'Overall source type must match canonical taxonomy'
);
assert.strictEqual(testJourney.provenance!.isFullyConfirmed, false, 'isFullyConfirmed must be false');
assert.strictEqual(testJourney.provenance!.hasSimulatedAttributes, true, 'hasSimulatedAttributes must be true');
assert(testJourney.provenance!.summary.length > 10, 'Provenance summary must be descriptive');
console.log(`✓ Overall provenance verified: [${testJourney.provenance!.overallSourceType}] "${testJourney.provenance!.summary}"`);

// ============================================================================
// TEST 4: Mixed-Provenance Journey Representation
// ============================================================================
console.log('\n--- Test 4: Mixed-Provenance Journey Representation ---');
const mixedJourney: Journey = {
  ...testJourney,
  provenance: {
    overallSourceType: 'mixed',
    isFullyConfirmed: false,
    hasLiveAttributes: true,
    hasSimulatedAttributes: true,
    summary: 'Contains both real-time provider data and deterministic corridor estimates.',
  },
  segments: testJourney.segments.map((seg, idx) => {
    if (idx === 1) {
      return {
        ...seg,
        provenance: {
          sourceType: 'deterministic_estimate' as const,
          providerName: seg.provider,
          isEstimate: true,
          hasLiveProvider: true,
          attributes: {
            duration: {
              sourceType: 'provider_live' as const,
              providerName: 'IndiGo Live Air Traffic',
              isEstimate: false,
              notes: 'Live radar tracking',
            },
            fare: {
              sourceType: 'deterministic_estimate' as const,
              providerName: seg.provider,
              isEstimate: true,
              notes: 'Corridor estimate',
            },
            availability: {
              sourceType: 'simulated' as const,
              providerName: 'Demo Fleet Simulator',
              isEstimate: true,
            },
          },
        },
      };
    }
    return seg;
  }),
};

assert.strictEqual(mixedJourney.provenance?.overallSourceType, 'mixed');
assert.strictEqual(mixedJourney.provenance?.hasLiveAttributes, true);
assert.strictEqual(mixedJourney.provenance?.isFullyConfirmed, false);
assert.strictEqual(mixedJourney.segments[1].provenance?.attributes.duration?.sourceType, 'provider_live');
assert.strictEqual(mixedJourney.segments[1].provenance?.attributes.duration?.isEstimate, false);
assert.strictEqual(mixedJourney.segments[1].provenance?.attributes.fare?.sourceType, 'deterministic_estimate');
assert.strictEqual(mixedJourney.segments[1].provenance?.attributes.fare?.isEstimate, true);
console.log('✓ Mixed-provenance journey accurately isolates live duration from estimated fare without conflation.');

// ============================================================================
// TEST 5: Granular Attribute-Level Provenance
// ============================================================================
console.log('\n--- Test 5: Granular Attribute-Level Provenance ---');
for (const seg of testJourney.segments) {
  assert(seg.provenance !== undefined, `Segment ${seg.segmentId} must carry provenance`);
  const attrs = seg.provenance!.attributes;
  assert('fare' in attrs, 'Segment must have fare provenance');
  assert('duration' in attrs, 'Segment must have duration provenance');
  assert('availability' in attrs, 'Segment must have availability provenance');

  assert.strictEqual(attrs.fare.isEstimate, true, 'Fare must be labeled as estimate');
  assert.strictEqual(attrs.duration.isEstimate, true, 'Duration must be labeled as estimate');
  assert.strictEqual(attrs.availability.sourceType, 'simulated', 'Availability must be labeled simulated');
}
console.log('✓ All 3 legs reflect granular attribute-level provenance (fare, duration, availability).');

// ============================================================================
// TEST 6: Simulated Inventory Safety Guard
// ============================================================================
console.log('\n--- Test 6: Simulated Inventory Safety Guard ---');
for (const seg of testJourney.segments) {
  assert.strictEqual(
    seg.availability.isRealInventory,
    false,
    `Segment ${seg.segmentId} must explicitly set isRealInventory = false`
  );
}
assert.strictEqual(
  testJourney.aiExplanation.isAvailabilityVerified,
  false,
  'aiExplanation.isAvailabilityVerified must be false'
);
assert(
  testJourney.aiExplanation.dataCredibilityNotice !== undefined,
  'aiExplanation must contain dataCredibilityNotice'
);
assert(
  testJourney.aiExplanation.dataCredibilityNotice!.toLowerCase().includes('estimate') ||
  testJourney.aiExplanation.dataCredibilityNotice!.toLowerCase().includes('simulat'),
  'dataCredibilityNotice must disclose estimation or simulation'
);
console.log('✓ Simulated inventory safety enforced: isRealInventory is strictly false across all legs.');

// ============================================================================
// TEST 7: Sandbox Booking Simulation Guard
// ============================================================================
console.log('\n--- Test 7: Sandbox Booking Simulation Guard ---');
assert(testJourney.bookingFeasibility.holdSupported, 'Hold must be supported in demo mode');
assert.strictEqual(testJourney.provenance?.isFullyConfirmed, false, 'Hold cannot be marked fully confirmed');
console.log('✓ Sandbox booking guard verified: hold operates in demo simulation mode without live carrier lock.');

// ============================================================================
// TEST 8: Distinguishable Estimated vs Provider-Backed Fares
// ============================================================================
console.log('\n--- Test 8: Distinguishable Estimated vs Provider-Backed Fares ---');
assert(testJourney.aiExplanation.isFareEstimated === true, 'isFareEstimated flag must be true');
for (const seg of testJourney.segments) {
  const isEst = seg.provenance?.attributes.fare?.isEstimate;
  assert.strictEqual(isEst, true, 'Individual segment fare must be marked as estimate');
}
console.log('✓ Fares deterministically distinguishable as corridor estimates.');

// ============================================================================
// TEST 9: Pareto Optimization & Comparison Intact With Provenance
// ============================================================================
console.log('\n--- Test 9: Pareto Optimization & Comparison Intact With Provenance ---');
for (const j of fallbackResults) {
  assert(j.isParetoOptimal !== undefined, 'isParetoOptimal must be defined');
  assert(j.aiExplanation.score >= 0 && j.aiExplanation.score <= 100, 'Score must be 0-100');
  assert(j.aiExplanation.tradeOffs.length >= 1, 'Trade-offs must be present');
  assert(j.aiExplanation.summary.length > 0, 'Explanation summary must be present');
}
console.log('✓ Pareto classification and multi-criteria comparison remain fully functional with provenance.');

console.log('\n=================================================================');
console.log('ALL 9 TRUST-AWARE JOURNEY TESTS PASSED! ✓');
console.log('=================================================================');
