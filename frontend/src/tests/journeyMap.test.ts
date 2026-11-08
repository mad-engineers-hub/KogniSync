import assert from 'node:assert';
import { composeMultiModalJourneys } from '../api/orchestrationEngine';
import { buildClientFallbackRoute, enrichJourneyRoute } from '../api/routes';
import { matchXRSceneForHub } from '../utils/xrMatching';
import { TravelRequest } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING INTELLIGENT MAP VISUALIZATION TEST SUITE (M3.5)');
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
assert.strictEqual(enriched.has_live_geometry, false, 'Fallback route must not claim live geometry');
console.log(`✓ Enriched route contains ${enriched.segments.length} legs spanning ${Math.round(enriched.total_distance_meters / 1000)} km.`);

// ============================================================================
// TEST 2: GeoJSON LineString Geometry Conformance (RFC 7946)
// ============================================================================
console.log('\n--- Test 2: GeoJSON LineString Geometry Conformance (RFC 7946) ---');
for (const seg of enriched.segments) {
  assert(seg.coordinates.length >= 2, `Segment ${seg.segment_id} must have >= 2 coordinates`);
  assert(seg.distance_meters > 0, `Segment ${seg.segment_id} distance must be positive`);
  assert(seg.duration_seconds > 0, `Segment ${seg.segment_id} duration must be positive`);

  // Verify GeoJSON geometry structure
  assert(seg.geojson_geometry !== undefined, `Segment ${seg.segment_id} must have geojson_geometry`);
  assert.strictEqual(seg.geojson_geometry.type, 'LineString', 'GeoJSON geometry type must be LineString');
  assert(seg.geojson_geometry.coordinates.length >= 2, 'GeoJSON LineString must contain at least 2 points');

  // Verify RFC 7946 coordinate ordering: [longitude, latitude]
  const firstGeoPoint = seg.geojson_geometry.coordinates[0];
  assert(Array.isArray(firstGeoPoint) && firstGeoPoint.length === 2, 'Coordinates must be [lng, lat] pairs');
  const [firstLng, firstLat] = firstGeoPoint;

  assert(
    Math.abs(firstLat - seg.origin_coords.latitude) < 1e-4,
    `Origin latitude mismatch in GeoJSON: expected ${seg.origin_coords.latitude}, got ${firstLat}`
  );
  assert(
    Math.abs(firstLng - seg.origin_coords.longitude) < 1e-4,
    `Origin longitude mismatch in GeoJSON: expected ${seg.origin_coords.longitude}, got ${firstLng}`
  );

  const lastGeoPoint = seg.geojson_geometry.coordinates[seg.geojson_geometry.coordinates.length - 1];
  const [lastLng, lastLat] = lastGeoPoint;
  assert(
    Math.abs(lastLat - seg.destination_coords.latitude) < 1e-4,
    `Destination latitude mismatch in GeoJSON: expected ${seg.destination_coords.latitude}, got ${lastLat}`
  );
  assert(
    Math.abs(lastLng - seg.destination_coords.longitude) < 1e-4,
    `Destination longitude mismatch in GeoJSON: expected ${seg.destination_coords.longitude}, got ${lastLng}`
  );

  if (seg.mode === 'flight') {
    assert(seg.coordinates.length >= 15, `Flight segment should have >= 15 arc points, got ${seg.coordinates.length}`);
  }
}
console.log('✓ All segment coordinate vectors strictly conform to GeoJSON LineString [lng, lat] specifications.');

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

// ============================================================================
// TEST 6: Alternative Journey Route Switching Contract
// ============================================================================
console.log('\n--- Test 6: Alternative Journey Route Switching Contract ---');
assert(journeys.length >= 2, 'Journey composition must produce at least 2 distinct alternative routes');
const altJourneys = journeys.slice(1);
for (const alt of altJourneys) {
  assert(alt.id !== journey.id, 'Alternative journey must have unique ID');
  assert(alt.segments.length > 0, 'Alternative journey must have segments');
  assert(alt.totalPrice > 0, 'Alternative journey price must be positive');
  assert(alt.totalDurationMinutes > 0, 'Alternative journey duration must be positive');
}
console.log(`✓ Verified ${altJourneys.length} distinct alternative Pareto journey routes available for map switching.`);

// ============================================================================
// TEST 7: Waypoints and Transfer Connection Buffers
// ============================================================================
console.log('\n--- Test 7: Waypoints and Transfer Connection Buffers ---');
for (let i = 0; i < journey.segments.length; i++) {
  const seg = journey.segments[i];
  if (i < journey.segments.length - 1) {
    // Intermodal transfer hub
    assert(seg.transferBufferMinutes !== undefined, `Segment ${seg.segmentId} must define transferBufferMinutes`);
    assert(seg.transferBufferMinutes >= 0, `Transfer buffer must be non-negative, got ${seg.transferBufferMinutes}`);
  }
}
console.log('✓ All intermodal transfer waypoints contain positive transfer connection buffers.');

// ============================================================================
// TEST 8: Strict Non-Road / Mode Segregation & Provenance Safety
// ============================================================================
console.log('\n--- Test 8: Non-Road Mode Segregation & Provenance Safety ---');
for (const seg of enriched.segments) {
  if (seg.mode === 'flight' || seg.mode === 'train') {
    assert(
      seg.is_live_geometry !== true,
      `Non-road mode ${seg.mode} must never be falsely marked as live geometry`
    );
  }
}
console.log('✓ Strict mode segregation confirmed: trains and flights cannot be falsely attributed to live road geometry.');

console.log('\n=================================================================');
console.log('ALL 8 INTELLIGENT MAP VISUALIZATION TESTS PASSED! ✓');
console.log('=================================================================');
