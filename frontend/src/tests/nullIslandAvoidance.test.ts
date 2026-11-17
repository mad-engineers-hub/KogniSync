/**
 * frontend/src/tests/nullIslandAvoidance.test.ts
 *
 * Verification suite for M4.0.4.1 Null Island Avoidance & Coordinate Integrity.
 * Proves that:
 * 1. Missing, undefined, NaN, Infinity, out-of-range coordinates are rejected.
 * 2. Synthetic (0, 0) "Null Island" is rejected.
 * 3. Individual zero coordinates (Equator lat=0, Prime Meridian lng=0) are preserved.
 * 4. buildClientFallbackRoute does not interpolate towards (0, 0).
 * 5. Spatial geometry filtering eliminates invalid coordinates from bounds and polylines.
 */
import assert from 'node:assert';
import { isValidCoordinate } from '../utils/mapCoordinates';
import { buildClientFallbackRoute } from '../api/routes';
import type { Journey, JourneySegment } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING NULL ISLAND AVOIDANCE & COORDINATE INTEGRITY TESTS');
console.log('=================================================================');

// 1. Direct Predicate Invariant Tests
console.log('\n--- 1. isValidCoordinate Predicate Invariants ---');

// Null Island rejection
assert.strictEqual(isValidCoordinate(0, 0), false, 'Direct (0, 0) must be rejected');
assert.strictEqual(isValidCoordinate({ lat: 0, lng: 0 }), false, 'Object {lat:0, lng:0} must be rejected');
assert.strictEqual(isValidCoordinate({ latitude: 0, longitude: 0 }), false, 'Object {latitude:0, longitude:0} must be rejected');

// Equator / Prime Meridian preservation (single-axis zeros must NOT be rejected)
assert.strictEqual(isValidCoordinate(0, 77.59), true, 'Equator coordinate (lat: 0, lng: 77.59) must be valid');
assert.strictEqual(isValidCoordinate({ lat: 0, lng: 77.59 }), true, 'Equator object must be valid');
assert.strictEqual(isValidCoordinate(51.5074, 0), true, 'Prime Meridian coordinate (lat: 51.5074, lng: 0) must be valid');
assert.strictEqual(isValidCoordinate({ lat: 51.5074, lng: 0 }), true, 'Prime Meridian object must be valid');

// NaN / Infinity rejection
assert.strictEqual(isValidCoordinate(NaN, 77.59), false, 'NaN latitude must be rejected');
assert.strictEqual(isValidCoordinate(12.97, NaN), false, 'NaN longitude must be rejected');
assert.strictEqual(isValidCoordinate(Infinity, 77.59), false, 'Infinity latitude must be rejected');
assert.strictEqual(isValidCoordinate(12.97, -Infinity), false, '-Infinity longitude must be rejected');
assert.strictEqual(isValidCoordinate({ lat: NaN, lng: NaN }), false, '{lat: NaN, lng: NaN} must be rejected');

// Range boundary validation
assert.strictEqual(isValidCoordinate(90.1, 77.59), false, 'Latitude > 90 must be rejected');
assert.strictEqual(isValidCoordinate(-90.1, 77.59), false, 'Latitude < -90 must be rejected');
assert.strictEqual(isValidCoordinate(12.97, 180.1), false, 'Longitude > 180 must be rejected');
assert.strictEqual(isValidCoordinate(12.97, -180.1), false, 'Longitude < -180 must be rejected');
assert.strictEqual(isValidCoordinate(90, 180), true, 'Boundary [90, 180] must be valid');
assert.strictEqual(isValidCoordinate(-90, -180), true, 'Boundary [-90, -180] must be valid');

// Undefined / null handling
assert.strictEqual(isValidCoordinate(undefined), false, 'undefined must be rejected');
assert.strictEqual(isValidCoordinate(null), false, 'null must be rejected');
assert.strictEqual(isValidCoordinate({} as any), false, 'empty object must be rejected');

console.log('✓ isValidCoordinate correctly rejects Null Island, NaN, Infinity, and out-of-range while preserving Equator/Meridian points');

// 2. buildClientFallbackRoute Null Island Resilience Tests
console.log('\n--- 2. Client Fallback Route Interpolation Safety ---');

const baseSegment: JourneySegment = {
  segmentId: 'seg-1',
  mode: 'train',
  provider: 'Indian Railways',
  origin: {
    id: 'loc-orig',
    name: 'Tumkur Railway Station',
    city: 'Tumkur',
    type: 'railway_station',
    coordinates: { lat: 13.34, lng: 77.10 },
  },
  destination: {
    id: 'loc-dest',
    name: 'Madgaon Junction',
    city: 'Goa',
    type: 'railway_station',
    coordinates: { lat: 15.27, lng: 73.98 },
  },
  departureTime: '2026-11-21T08:00:00Z',
  arrivalTime: '2026-11-21T18:00:00Z',
  durationMinutes: 600,
  distanceKm: 550,
  price: 650,
  currency: 'INR',
  carbonKg: 25,
  comfortScore: 8,
  availability: {
    status: 'available',
    remainingUnits: 50,
    isRealInventory: false,
  },
};

const baseJourney: Journey = {
  id: 'jny-test-1',
  title: 'Tumkur to Goa Test Journey',
  origin: baseSegment.origin,
  destination: baseSegment.destination,
  departureTime: baseSegment.departureTime,
  arrivalTime: baseSegment.arrivalTime,
  totalDurationMinutes: 600,
  totalPrice: 650,
  currency: 'INR',
  totalTransfers: 0,
  modes: ['train'],
  segments: [baseSegment],
  carbonKg: 25,
  comfortScore: 8,
  recommendationCategory: 'best_value',
  aiExplanation: {
    summary: 'Direct rail corridor',
    tradeOffs: [],
    rankReason: 'Best value',
    score: 85,
  },
  bookingFeasibility: {
    holdSupported: true,
    concurrencySafe: true,
    holdTtlSeconds: 900,
  },
};

// Case 2A: Valid endpoints generate valid polyline
const validFallback = buildClientFallbackRoute(baseJourney);
assert.strictEqual(validFallback.segments.length, 1);
assert.ok(validFallback.segments[0].coordinates.length >= 2, 'Must produce interpolated coordinates for valid endpoints');
assert.ok(
  validFallback.segments[0].coordinates.every((c) => isValidCoordinate(c.latitude, c.longitude)),
  'All generated coordinates must be valid non-Null Island coordinates'
);

// Case 2B: Missing origin coordinates -> must NOT interpolate to (0, 0)
const missingOrigSeg: JourneySegment = {
  ...baseSegment,
  segmentId: 'seg-missing-orig',
  origin: {
    ...baseSegment.origin,
    coordinates: undefined as any,
  },
};
const missingOrigJourney: Journey = {
  ...baseJourney,
  segments: [missingOrigSeg],
};

const missingOrigFallback = buildClientFallbackRoute(missingOrigJourney);
assert.strictEqual(
  missingOrigFallback.segments[0].coordinates.length,
  0,
  'When origin coordinates are missing, fallback coordinates array must be empty (NOT interpolated to Null Island)'
);
assert.strictEqual(
  Number.isNaN(missingOrigFallback.segments[0].origin_coords.latitude),
  true,
  'Missing origin coords must be set to NaN, not (0, 0)'
);

// Case 2C: Synthetic (0, 0) origin coordinates -> treated as invalid, not interpolated
const zeroOrigSeg: JourneySegment = {
  ...baseSegment,
  segmentId: 'seg-zero-orig',
  origin: {
    ...baseSegment.origin,
    coordinates: { lat: 0, lng: 0 },
  },
};
const zeroOrigJourney: Journey = {
  ...baseJourney,
  segments: [zeroOrigSeg],
};

const zeroOrigFallback = buildClientFallbackRoute(zeroOrigJourney);
assert.strictEqual(
  zeroOrigFallback.segments[0].coordinates.length,
  0,
  'When origin coordinates are (0,0), fallback coordinates must be empty'
);

console.log('✓ buildClientFallbackRoute never interpolates towards Null Island or generates spurious geometries');

// 3. Spatial Geometry Filtering & Bounds Calculation
console.log('\n--- 3. Spatial Bounds Filtering ---');

const mixedCoordinates: [number, number][] = [
  [0, 0], // Null Island
  [NaN, 77.10], // NaN
  [13.34, 77.10], // Valid Tumkur
  [15.27, 73.98], // Valid Goa
  [95.0, 77.0], // Out of range lat
  [12.97, NaN], // NaN lng
];

const validPoints = mixedCoordinates.filter(([lat, lng]) => isValidCoordinate(lat, lng));
assert.strictEqual(validPoints.length, 2, 'Only the 2 valid coordinates must survive filtering');
assert.deepStrictEqual(validPoints[0], [13.34, 77.10]);
assert.deepStrictEqual(validPoints[1], [15.27, 73.98]);

console.log('✓ Spatial bounds filtering cleanly purges Null Island and invalid tuples');

console.log('\n=================================================================');
console.log('ALL NULL ISLAND AVOIDANCE TESTS PASSED (M4.0.4.1)');
console.log('=================================================================');
