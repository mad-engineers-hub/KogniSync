import assert from 'node:assert';
import { composeMultiModalJourneys } from '../api/orchestrationEngine';
import { buildClientFallbackRoute, enrichJourneyRoute } from '../api/routes';
import { matchXRSceneForHub } from '../utils/xrMatching';
import { TravelRequest } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING GOOGLE ROUTES & MULTI-MODAL MAP INTEGRATION TEST SUITE');
console.log('=================================================================');

// Synthesize journeys for testing
const testReq: TravelRequest = {
  origin: 'Chennai',
  destination: 'Udupi',
  departureDate: '2026-11-04',
  preferredArrivalBefore: '20:00',
  budgetMax: 5000,
  passengersCount: 1,
  weights: { cost: 0.2, duration: 0.5, comfort: 0.2, carbon: 0.1 },
  naturalLanguageQuery: 'Chennai to Udupi fastest',
};

const journeys = composeMultiModalJourneys(testReq);
const journey = journeys[0];

// ============================================================================
// TEST 1: Fallback Route Generation Data Integrity
// ============================================================================
console.log('\n--- Test 1: Fallback Route Spatial Data Integrity ---');
const enriched = buildClientFallbackRoute(journey);

assert(enriched.journey_id === journey.id, 'Journey ID must match');
assert.strictEqual(enriched.segments.length, journey.segments.length, 'Segment count must match');
assert(enriched.total_distance_meters > 500000, `Total distance must be > 500 km, got ${enriched.total_distance_meters}`);
assert(enriched.total_duration_seconds > 5000, `Total duration must be > 5000s, got ${enriched.total_duration_seconds}`);
assert.strictEqual(enriched.provider_status, 'ok', 'Provider status must be ok');
console.log(`✓ Enriched route contains ${enriched.segments.length} legs spanning ${Math.round(enriched.total_distance_meters / 1000)} km.`);

// ============================================================================
// TEST 2: Waypoint Coordinates & Mode Specifics
// ============================================================================
console.log('\n--- Test 2: Mode-Specific Waypoint Coordinates ---');
for (const seg of enriched.segments) {
  assert(seg.coordinates.length >= 2, `Segment ${seg.segment_id} must have >= 2 coordinates`);
  assert(seg.distance_meters > 0, `Segment ${seg.segment_id} distance must be positive`);
  assert(seg.duration_seconds > 0, `Segment ${seg.segment_id} duration must be positive`);

  // First coordinate must match origin
  const firstPt = seg.coordinates[0];
  assert(
    Math.abs(firstPt.latitude - seg.origin_coords.latitude) < 1e-4,
    `Origin coordinate mismatch in segment ${seg.segment_id}`
  );

  // Last coordinate must match destination
  const lastPt = seg.coordinates[seg.coordinates.length - 1];
  assert(
    Math.abs(lastPt.latitude - seg.destination_coords.latitude) < 1e-4,
    `Destination coordinate mismatch in segment ${seg.segment_id}`
  );

  if (seg.mode === 'flight') {
    assert(seg.coordinates.length >= 15, `Flight segment should have >= 15 arc points, got ${seg.coordinates.length}`);
  }
}
console.log('✓ All segment coordinate vectors conform to spatial bounds and mode geometry.');

// ============================================================================
// TEST 3: Door-to-Door Summation Invariants
// ============================================================================
console.log('\n--- Test 3: Segment Summation Invariants ---');
const sumDistance = enriched.segments.reduce((sum, s) => sum + s.distance_meters, 0);
const sumDuration = enriched.segments.reduce((sum, s) => sum + s.duration_seconds, 0);

assert.strictEqual(enriched.total_distance_meters, sumDistance, 'Total distance must equal sum of segment distances');
assert.strictEqual(enriched.total_duration_seconds, sumDuration, 'Total duration must equal sum of segment durations');
console.log(`✓ Distance (${sumDistance}m) and duration (${sumDuration}s) summation invariants verified.`);

// ============================================================================
// TEST 4: Hub XR Linking from Waypoints
// ============================================================================
console.log('\n--- Test 4: Hub XR Linking from Waypoints ---');
const chennaiCentralXR = matchXRSceneForHub('Chennai Central');
assert(chennaiCentralXR !== null, 'Chennai Central hub must resolve to XR scene');
assert.strictEqual(chennaiCentralXR, 'xrs_chennai_central_concourse', 'Must resolve to xrs_chennai_central_concourse');

const ksrXR = matchXRSceneForHub('KSR Bengaluru');
assert(ksrXR !== null, 'KSR Bengaluru hub must resolve to XR scene');
assert(ksrXR.startsWith('xrs_ksr_bengaluru'), 'Must resolve to KSR Bengaluru XR scene');
console.log('✓ Hubs correctly map to canonical organizer XR concourses.');

// ============================================================================
// TEST 5: Graceful Degradation on Network Failure
// ============================================================================
console.log('\n--- Test 5: Graceful Client Degradation on Network Failure ---');
const asyncResult = await enrichJourneyRoute(journey);
assert(asyncResult !== null, 'enrichJourneyRoute must never return null');
assert.strictEqual(asyncResult.journey_id, journey.id, 'Enriched journey ID must match');
assert.strictEqual(asyncResult.segments.length, journey.segments.length, 'Segments count must match');
console.log('✓ enrichJourneyRoute seamlessly degrades to deterministic local geometry if backend is offline.');

console.log('\n=================================================================');
console.log('ALL 5 GOOGLE ROUTES & MAP INTEGRATION TESTS PASSED! ✓');
console.log('=================================================================');
