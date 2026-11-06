import assert from 'node:assert';
import { enrichJourneyRoute, fetchRoutesHealth, buildClientFallbackRoute } from '../api/routes';
import { parseTravelIntent, extractClientIntent } from '../api/journey';
import { composeMultiModalJourneys } from '../api/orchestrationEngine';
import { TravelRequest } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING API CONTRACT & INTEGRATION ALIGNMENT TEST SUITE');
console.log('=================================================================');

// ============================================================================
// TEST 1: Canonical Maps API Route Contract
// ============================================================================
console.log('\n--- Test 1: Canonical Maps API Endpoint & Schema Alignment ---');
const sampleReq: TravelRequest = {
  origin: 'Chennai',
  destination: 'Udupi',
  departureDate: '2026-11-04',
  preferredArrivalBefore: '20:00',
  budgetMax: 5000,
  passengersCount: 1,
  weights: { cost: 0.2, duration: 0.5, comfort: 0.2, carbon: 0.1 },
  naturalLanguageQuery: 'Chennai to Udupi fastest',
};

const candidateJourneys = composeMultiModalJourneys(sampleReq);
assert(candidateJourneys.length > 0, 'Must have at least one journey');
const testJourney = candidateJourneys[0];

// Verify buildClientFallbackRoute satisfies EnrichedJourneyRoute contract
const fallbackRoute = buildClientFallbackRoute(testJourney);
assert.strictEqual(fallbackRoute.journey_id, testJourney.id);
assert.strictEqual(fallbackRoute.segments.length, testJourney.segments.length);
assert(fallbackRoute.total_distance_meters > 0, 'Total distance must be positive');
assert(fallbackRoute.total_duration_seconds > 0, 'Total duration must be positive');
assert.strictEqual(fallbackRoute.source, 'client_fallback');
assert.strictEqual(fallbackRoute.provider_status, 'ok');

for (const seg of fallbackRoute.segments) {
  assert(seg.segment_id.length > 0, 'segment_id must be non-empty');
  assert(seg.mode.length > 0, 'mode must be non-empty');
  assert(seg.origin_title.length > 0, 'origin_title must be non-empty');
  assert(seg.origin_city.length > 0, 'origin_city must be non-empty');
  assert(seg.destination_title.length > 0, 'destination_title must be non-empty');
  assert(seg.destination_city.length > 0, 'destination_city must be non-empty');
  assert(seg.origin_coords.latitude !== undefined, 'origin latitude required');
  assert(seg.origin_coords.longitude !== undefined, 'origin longitude required');
  assert(seg.destination_coords.latitude !== undefined, 'dest latitude required');
  assert(seg.destination_coords.longitude !== undefined, 'dest longitude required');
  assert(Array.isArray(seg.coordinates), 'coordinates must be an array');
  assert(seg.coordinates.length >= 2, 'must have >= 2 coordinates');
}
console.log('✓ Maps fallback route strictly matches EnrichedJourneyRoute API contract.');

// Test enrichJourneyRoute execution (calling canonical /api/v1/maps/enrich with fallback resilience)
const enrichedRes = await enrichJourneyRoute(testJourney);
assert(enrichedRes !== null, 'enrichJourneyRoute must return a valid route object');
assert.strictEqual(enrichedRes.journey_id, testJourney.id);
assert.strictEqual(enrichedRes.segments.length, testJourney.segments.length);
console.log(`✓ enrichJourneyRoute successfully returned ${enrichedRes.segments.length} route segments (source: ${enrichedRes.source}).`);

// Test fetchRoutesHealth
const healthRes = await fetchRoutesHealth();
assert(typeof healthRes.enabled === 'boolean', 'health.enabled must be boolean');
assert(typeof healthRes.active_provider === 'string', 'health.active_provider must be string');
assert(typeof healthRes.service === 'string', 'health.service must be string');
console.log(`✓ fetchRoutesHealth returned active provider: '${healthRes.active_provider}'.`);

// ============================================================================
// TEST 2: Canonical AI API Route Contract & Heuristic Fallback
// ============================================================================
console.log('\n--- Test 2: Canonical AI Intent Endpoint & Fallback Alignment ---');
// Verify extractClientIntent returns valid TravelIntent
const clientIntent = extractClientIntent('I need to travel from Bangalore to Goa under 6000');
assert.strictEqual(clientIntent.origin, 'Bangalore');
assert.strictEqual(clientIntent.destination, 'Goa');
assert.strictEqual(clientIntent.budget, 6000);
assert(clientIntent.confidence !== undefined, 'confidence must be defined');

// Verify parseTravelIntent (calls /api/v1/ai/parse-travel-intent with fallback resilience)
const parsedIntent = await parseTravelIntent('Chennai to Udupi tomorrow before 8 PM budget 5000');
assert(parsedIntent !== null, 'parsedIntent must not be null');
assert(parsedIntent.origin?.includes('Chennai'), 'Origin must contain Chennai');
assert(parsedIntent.destination?.includes('Udupi'), 'Destination must contain Udupi');
console.log(`✓ parseTravelIntent extracted: ${parsedIntent.origin} -> ${parsedIntent.destination} (Budget: ₹${parsedIntent.budget}).`);

// Verify empty input explicit validation
await assert.rejects(
  async () => await parseTravelIntent('   '),
  (err: Error) => {
    assert(err.message.includes('Input text is required') || (err as any).status === 400);
    return true;
  }
);
console.log('✓ Empty/whitespace prompt explicitly rejected with validation error.');

// ============================================================================
// TEST 3: Contract Verification Summary
// ============================================================================
console.log('\n=================================================================');
console.log('ALL API CONTRACT TESTS PASSED (3/3) ✓');
console.log('=================================================================');

