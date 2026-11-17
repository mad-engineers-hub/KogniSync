/**
 * frontend/src/tests/gpsCollisionDetector.test.ts
 *
 * Verification suite for M4.0.4.1 Cross-City Collision Detection and Intentional GPS preservation.
 * Proves that:
 * 1. Stale coordinates from prior city queries (e.g. searching Tumkur with leaked Bengaluru coords)
 *    are detected and cleared.
 * 2. Legitimate intentional custom coordinates outside the 45 km radius (Palolem in Goa ~60km,
 *    Sira in Tumkur ~52km, Jewar in NCR ~72km) are strictly preserved.
 * 3. Arbitrary map-picker pins are preserved.
 * 4. Normal end-to-end journey generation reflects accurate origin coordinates.
 */
import assert from 'node:assert';
import {
  detectCrossCityCollision,
  resolveHubContext,
  composeMultiModalJourneys,
} from '../api/orchestrationEngine';
import type { TravelRequest } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING GPS COLLISION DETECTOR & INTENTIONAL COORDINATES TEST');
console.log('=================================================================');

// 1. Direct Collision Detection Tests
console.log('\n--- 1. Cross-City Collision Detection Predicate ---');

// Case 1A: Query is 'Tumkur', but coordinates are Bengaluru center (12.9716, 77.5946)
const bengaluruCoords = { lat: 12.9716, lng: 77.5946 };
const collisionTumkurWithBlr = detectCrossCityCollision('Tumkur', bengaluruCoords);
assert.strictEqual(
  collisionTumkurWithBlr.isStaleCollision,
  true,
  'Must detect collision when Tumkur query receives Bengaluru coordinates'
);
assert.ok(
  ['Bengaluru', 'Bangalore'].includes(collisionTumkurWithBlr.conflictingCity!),
  'Must identify Bengaluru/Bangalore as the conflicting hub'
);

// Case 1B: Query is 'Tumkur', coordinates are genuine Tumkur coordinates
const tumkurCoords = { lat: 13.3379, lng: 77.1006 };
const collisionTumkurOwnCoords = detectCrossCityCollision('Tumkur', tumkurCoords);
assert.strictEqual(
  collisionTumkurOwnCoords.isStaleCollision,
  false,
  'Must not flag legitimate Tumkur coordinates as collision'
);

// Case 1C: Query is 'Goa', coordinates are Palolem Beach (14.99, 74.02, ~60 km from Panaji)
const palolemCoords = { lat: 14.99, lng: 74.02 };
const collisionGoaPalolem = detectCrossCityCollision('Goa', palolemCoords);
assert.strictEqual(
  collisionGoaPalolem.isStaleCollision,
  false,
  'Must not flag Palolem (Goa) as a collision despite being > 45 km from Panaji'
);

// Case 1D: Query is 'Tumkur', coordinates are Sira (13.74, 76.90, ~52 km from Tumkur center)
const siraCoords = { lat: 13.74, lng: 76.90 };
const collisionTumkurSira = detectCrossCityCollision('Tumkur', siraCoords);
assert.strictEqual(
  collisionTumkurSira.isStaleCollision,
  false,
  'Must not flag Sira (Tumkur district) as a collision despite being > 45 km from center'
);

// Case 1E: Query is 'Delhi', coordinates are Jewar / Noida Airport (28.18, 77.56, ~72 km from CP)
const jewarCoords = { lat: 28.18, lng: 77.56 };
const collisionDelhiJewar = detectCrossCityCollision('Delhi', jewarCoords);
assert.strictEqual(
  collisionDelhiJewar.isStaleCollision,
  false,
  'Must not flag Jewar as a collision with Delhi'
);

// Case 1F: Query is 'Mysuru', coordinates are Bengaluru (collision!)
const collisionMysuruWithBlr = detectCrossCityCollision('Mysuru', bengaluruCoords);
assert.strictEqual(
  collisionMysuruWithBlr.isStaleCollision,
  true,
  'Must detect stale Bengaluru coordinates when querying Mysuru'
);

console.log('✓ Cross-city collision detector properly flags conflicting cities and preserves intentional non-conflicting points');

// 2. Hub Resolution Integration Tests
console.log('\n--- 2. Hub Context Resolution with Collision & Intentional GPS ---');

// Test 2A: Tumkur with leaked Bengaluru coordinates -> stale cleared, resolved to Tumkur
const hubTumkurLeaked = resolveHubContext('Tumkur', true, bengaluruCoords);
assert.strictEqual(hubTumkurLeaked.parentCity, 'Tumkur');
assert.ok(
  Math.abs(hubTumkurLeaked.userNode.coordinates.lat - 13.34) < 0.1,
  'Stale Bengaluru coordinates must be cleared; origin should be in Tumkur (lat ~13.34)'
);
assert.ok(
  Math.abs(hubTumkurLeaked.userNode.coordinates.lng - 77.10) < 0.1,
  'Stale Bengaluru coordinates must be cleared; origin should be in Tumkur (lng ~77.10)'
);

// Test 2B: Goa with Palolem coordinates -> Palolem coordinates preserved
const hubGoaPalolem = resolveHubContext('Goa', false, palolemCoords);
assert.strictEqual(hubGoaPalolem.userNode.coordinates.lat, 14.99, 'Palolem lat must be strictly preserved');
assert.strictEqual(hubGoaPalolem.userNode.coordinates.lng, 74.02, 'Palolem lng must be strictly preserved');

// Test 2C: Tumkur with Sira coordinates -> Sira coordinates preserved
const hubTumkurSira = resolveHubContext('Tumkur', true, siraCoords);
assert.strictEqual(hubTumkurSira.userNode.coordinates.lat, 13.74, 'Sira lat must be strictly preserved');
assert.strictEqual(hubTumkurSira.userNode.coordinates.lng, 76.90, 'Sira lng must be strictly preserved');

// Test 2D: Unknown location with explicit map-picker pin (14.5, 75.5) -> preserved
const mapPickerPin = { lat: 14.5, lng: 75.5 };
const hubMapPicker = resolveHubContext('Channagiri Rural', true, mapPickerPin);
assert.strictEqual(hubMapPicker.userNode.coordinates.lat, 14.5, 'Custom map picker lat must be preserved');
assert.strictEqual(hubMapPicker.userNode.coordinates.lng, 75.5, 'Custom map picker lng must be preserved');

// Test 2E: Standard Bengaluru to Goa journey
const hubBlr = resolveHubContext('Bengaluru', true);
const hubGoa = resolveHubContext('Goa', false);
assert.strictEqual(hubBlr.parentCity, 'Bengaluru');
assert.strictEqual(hubGoa.parentCity, 'Goa');

console.log('✓ Hub context resolution correctly applies collision rules and preserves legitimate coordinates');

// 3. End-to-End Candidate Journey Generation
console.log('\n--- 3. Candidate Journey Generation with Stale Coordinates ---');

const reqWithStaleOrigin: TravelRequest = {
  origin: 'Tumkur',
  destination: 'Goa',
  departureDate: '2026-11-21',
  passengersCount: 1,
  weights: { cost: 0.5, duration: 0.5, comfort: 0.5, carbon: 0.5 },
  originCoordinates: bengaluruCoords, // Stale state leak
};

const candidateJourneys = composeMultiModalJourneys(reqWithStaleOrigin);
assert.ok(candidateJourneys.length > 0, 'Must produce candidate journeys');

for (const jny of candidateJourneys) {
  assert.ok(
    jny.origin.city.toLowerCase().includes('tumkur'),
    'Journey origin must be Tumkur'
  );
  assert.ok(
    Math.abs(jny.origin.coordinates.lat - 13.34) < 0.1,
    `Journey origin lat (${jny.origin.coordinates.lat}) must be near Tumkur (~13.34), not Bengaluru (~12.97)`
  );
  assert.ok(
    jny.segments[0].origin.city.toLowerCase().includes('tumkur'),
    `First segment origin city (${jny.segments[0].origin.city}) must be in Tumkur corridor`
  );
  assert.ok(
    Math.abs(jny.segments[0].origin.coordinates.lat - 13.34) < 0.1,
    `First segment origin lat (${jny.segments[0].origin.coordinates.lat}) must be near Tumkur`
  );
}

console.log('✓ Candidate journeys generated from stale input correctly ground origin in Tumkur');

console.log('\n=================================================================');
console.log('ALL GPS COLLISION DETECTOR TESTS PASSED (M4.0.4.1)');
console.log('=================================================================');
