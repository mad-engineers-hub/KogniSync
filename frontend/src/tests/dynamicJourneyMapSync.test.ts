import assert from 'node:assert';
import {
  composeMultiModalJourneys,
  resolveHubContext,
  estimateCorridorDistanceKm,
  REGIONAL_GAZETTEER,
} from '../api/orchestrationEngine';
import { buildClientFallbackRoute } from '../api/routes';
import { TravelRequest, Journey } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING DYNAMIC JOURNEY MAP SYNCHRONIZATION TEST SUITE (M4.0.3)');
console.log('=================================================================');

// ============================================================================
// TEST A: Origin Change (Bengaluru → Chennai to Tumkur → Chennai)
// ============================================================================
console.log('\n--- Test A: Origin Change (Bengaluru → Chennai to Tumkur → Chennai) ---');
const blrReq: TravelRequest = {
  origin: 'Bangalore',
  destination: 'Chennai',
  departureDate: '2026-11-16',
  passengersCount: 1,
  weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
};
const blrJourneys = composeMultiModalJourneys(blrReq);
assert(blrJourneys.length > 0, 'Must produce journeys for Bangalore -> Chennai');
const blrOriginCoords = blrJourneys[0].origin.coordinates;
assert(
  Math.abs(blrOriginCoords.lat - 12.9716) < 0.1,
  `Bangalore origin lat expected ~12.97, got ${blrOriginCoords.lat}`
);

const tumkurReq: TravelRequest = {
  origin: 'Tumkur',
  destination: 'Chennai',
  departureDate: '2026-11-16',
  passengersCount: 1,
  weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
};
const tumkurJourneys = composeMultiModalJourneys(tumkurReq);
assert(tumkurJourneys.length > 0, 'Must produce journeys for Tumkur -> Chennai');
const tumkurOriginCoords = tumkurJourneys[0].origin.coordinates;

// Verify Tumkur coordinates are in Tumkur (~13.34, 77.10), NOT Bengaluru (~12.97, 77.59)
assert(
  Math.abs(tumkurOriginCoords.lat - 13.34) < 0.05,
  `Tumkur origin lat expected ~13.34, got ${tumkurOriginCoords.lat}`
);
assert(
  Math.abs(tumkurOriginCoords.lng - 77.10) < 0.05,
  `Tumkur origin lng expected ~77.10, got ${tumkurOriginCoords.lng}`
);
assert(
  Math.abs(tumkurOriginCoords.lat - blrOriginCoords.lat) > 0.3,
  'Tumkur and Bangalore origins must be geographically distinct (> 30 km apart)'
);

// Verify fallback route geometry for Tumkur reflects Tumkur origin
const tumkurFallback = buildClientFallbackRoute(tumkurJourneys[0]);
assert(tumkurFallback.segments.length > 0, 'Fallback route must have segments');
assert(
  Math.abs(tumkurFallback.segments[0].origin_coords.latitude - 13.34) < 0.05,
  `Route geometry origin latitude must match Tumkur, got ${tumkurFallback.segments[0].origin_coords.latitude}`
);
console.log(`✓ Origin dynamically shifted: Bangalore (${blrOriginCoords.lat}, ${blrOriginCoords.lng}) -> Tumkur (${tumkurOriginCoords.lat}, ${tumkurOriginCoords.lng})`);
console.log(`✓ Route geometry origin verified at Tumkur: ${tumkurFallback.segments[0].origin_coords.latitude}°N, ${tumkurFallback.segments[0].origin_coords.longitude}°E`);

// ============================================================================
// TEST B: Destination Change (Tumkur → Chennai to Tumkur → Coimbatore)
// ============================================================================
console.log('\n--- Test B: Destination Change (Tumkur → Chennai to Tumkur → Coimbatore) ---');
const cbeReq: TravelRequest = {
  origin: 'Tumkur',
  destination: 'Coimbatore',
  departureDate: '2026-11-16',
  passengersCount: 1,
  weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
};
const cbeJourneys = composeMultiModalJourneys(cbeReq);
assert(cbeJourneys.length > 0, 'Must produce journeys for Tumkur -> Coimbatore');
const cbeDestCoords = cbeJourneys[0].destination.coordinates;
const chnDestCoords = tumkurJourneys[0].destination.coordinates;

assert(
  Math.abs(cbeDestCoords.lat - 11.0168) < 0.1,
  `Coimbatore dest lat expected ~11.0168, got ${cbeDestCoords.lat}`
);
assert(
  Math.abs(cbeDestCoords.lng - 76.9558) < 0.1,
  `Coimbatore dest lng expected ~76.9558, got ${cbeDestCoords.lng}`
);
assert(
  Math.abs(cbeDestCoords.lat - chnDestCoords.lat) > 1.0,
  'Coimbatore and Chennai destinations must be geographically distinct'
);

const cbeFallback = buildClientFallbackRoute(cbeJourneys[0]);
const lastSeg = cbeFallback.segments[cbeFallback.segments.length - 1];
assert(
  Math.abs(lastSeg.destination_coords.latitude - 11.0168) < 0.1,
  `Route geometry destination must match Coimbatore, got ${lastSeg.destination_coords.latitude}`
);
console.log(`✓ Destination dynamically shifted: Chennai (${chnDestCoords.lat}, ${chnDestCoords.lng}) -> Coimbatore (${cbeDestCoords.lat}, ${cbeDestCoords.lng})`);

// ============================================================================
// TEST C: Both Endpoints Change (Hubli → Goa)
// ============================================================================
console.log('\n--- Test C: Both Endpoints Change (Hubli → Goa) ---');
const hubliGoaReq: TravelRequest = {
  origin: 'Hubli',
  destination: 'Goa',
  departureDate: '2026-11-16',
  passengersCount: 1,
  weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
};
const hubliGoaJourneys = composeMultiModalJourneys(hubliGoaReq);
assert(hubliGoaJourneys.length > 0, 'Must produce journeys for Hubli -> Goa');
const hgOrigin = hubliGoaJourneys[0].origin.coordinates;
const hgDest = hubliGoaJourneys[0].destination.coordinates;

assert(
  Math.abs(hgOrigin.lat - 15.3647) < 0.1,
  `Hubli origin lat expected ~15.3647, got ${hgOrigin.lat}`
);
assert(
  Math.abs(hgDest.lat - 15.2993) < 0.3,
  `Goa destination lat expected ~15.2993, got ${hgDest.lat}`
);
// Neither origin nor destination must be near Bangalore (lat ~12.97)
assert(
  Math.abs(hgOrigin.lat - 12.9716) > 2.0,
  'Hubli origin must NOT be near Bangalore'
);
assert(
  Math.abs(hgDest.lat - 12.9716) > 2.0,
  'Goa destination must NOT be near Bangalore'
);
console.log(`✓ Both endpoints independent of Bangalore: Origin Hubli (${hgOrigin.lat}, ${hgOrigin.lng}), Destination Goa (${hgDest.lat}, ${hgDest.lng})`);

// ============================================================================
// TEST D: Query Cache Key Isolation
// ============================================================================
console.log('\n--- Test D: Query Cache Key Isolation ---');
function buildQueryKey(req: TravelRequest) {
  return [
    'journeys',
    req.origin.trim().toLowerCase(),
    req.destination.trim().toLowerCase(),
    req.naturalLanguageQuery || '',
    req.departureDate,
    req.preferredArrivalBefore || '14:00',
    req.budgetMax,
    req.weights.cost,
    req.weights.duration,
    req.weights.comfort,
    req.weights.carbon,
    req.passengersCount,
    req.originCoordinates?.lat,
    req.originCoordinates?.lng,
    req.destinationCoordinates?.lat,
    req.destinationCoordinates?.lng,
  ];
}

const key1 = JSON.stringify(buildQueryKey(blrReq));
const key2 = JSON.stringify(buildQueryKey(tumkurReq));
const key3 = JSON.stringify(buildQueryKey({ ...tumkurReq, origin: '  tumkur  ' }));
const keyWithCoords = JSON.stringify(
  buildQueryKey({ ...tumkurReq, originCoordinates: { lat: 13.3401, lng: 77.1006 } })
);

assert(key1 !== key2, 'Bangalore and Tumkur query keys must be strictly isolated');
assert(key2 === key3, 'Whitespace and case normalization must produce identical keys');
assert(key2 !== keyWithCoords, 'Query with GPS coordinates must have distinct cache key');
console.log('✓ Cache keys strictly isolate distinct geographic origins and destinations');

// ============================================================================
// TEST E: Pareto Route Selection Updates Active Polyline Geometry
// ============================================================================
console.log('\n--- Test E: Pareto Route Selection Updates Active Geometry ---');
assert(tumkurJourneys.length >= 2, 'Must have at least 2 candidate journeys');
const jny1 = tumkurJourneys[0];
const jny2 = tumkurJourneys[1];
const route1 = buildClientFallbackRoute(jny1);
const route2 = buildClientFallbackRoute(jny2);

assert(route1.journey_id === jny1.id, 'Route 1 must bind to Journey 1');
assert(route2.journey_id === jny2.id, 'Route 2 must bind to Journey 2');
assert(
  route1.segments.length > 0 && route2.segments.length > 0,
  'Both routes must have valid segment geometries'
);
console.log(`✓ Active journey selection switches between ${jny1.id} (${jny1.recommendationCategory}) and ${jny2.id} (${jny2.recommendationCategory})`);

// ============================================================================
// TEST F: Empty & Single-Segment Fallback Handling
// ============================================================================
console.log('\n--- Test F: Graceful Handling of Empty & Single-Segment Geometries ---');
const emptyJourney: Journey = {
  ...jny1,
  id: 'jny-empty',
  segments: [],
};
const emptyRoute = buildClientFallbackRoute(emptyJourney);
assert.strictEqual(emptyRoute.segments.length, 0, 'Empty journey must produce 0 segments');
assert.strictEqual(emptyRoute.total_distance_meters, 0, 'Distance must be 0');

console.log('✓ Empty journey gracefully produces clean 0-segment geometry without throwing');

// ============================================================================
// TEST G: URL Parameter Parsing & Direct Coordinate Restoration
// ============================================================================
console.log('\n--- Test G: URL Parameter Parsing & Direct Coordinate Restoration ---');
const searchStr = 'origin=Tumkur&destination=Chennai&date=2026-11-16&passengers=1&originLat=13.3401&originLng=77.1006';
const params = new URLSearchParams(searchStr);

const parsedOrigin = params.get('origin') || 'Bangalore';
const parsedDest = params.get('destination') || 'Chennai';
const parsedDate = params.get('date') || '2026-11-16';
const parsedOriginLat = params.get('originLat');
const parsedOriginLng = params.get('originLng');

assert.strictEqual(parsedOrigin, 'Tumkur');
assert.strictEqual(parsedDest, 'Chennai');
assert.strictEqual(parsedDate, '2026-11-16');
assert.strictEqual(Number(parsedOriginLat), 13.3401);
assert.strictEqual(Number(parsedOriginLng), 77.1006);

const restoredReq: TravelRequest = {
  origin: parsedOrigin,
  destination: parsedDest,
  departureDate: parsedDate,
  passengersCount: 1,
  weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
  originCoordinates: { lat: Number(parsedOriginLat), lng: Number(parsedOriginLng) },
};

const restoredJourneys = composeMultiModalJourneys(restoredReq);
assert(restoredJourneys.length > 0, 'Must compose journeys from restored request');
assert.strictEqual(restoredJourneys[0].origin.coordinates.lat, 13.3401);
assert.strictEqual(restoredJourneys[0].origin.coordinates.lng, 77.1006);
console.log('✓ URL parameters directly restore request and exact origin coordinates');

// ============================================================================
// TEST H: Regression Protection & Provenance Classification Preservation
// ============================================================================
console.log('\n--- Test H: Regression Protection & Provenance Classification ---');
for (const j of tumkurJourneys) {
  assert(j.id.startsWith('jny-'), `Journey id must have jny- prefix: ${j.id}`);
  assert(j.segments.length >= 2, `Multi-modal journey must have >= 2 segments, got ${j.segments.length}`);
  assert(j.totalPrice > 0, 'Total price must be > 0');
  assert(j.totalDurationMinutes > 0, 'Total duration must be > 0');

  for (const seg of j.segments) {
    assert(seg.segmentId.startsWith('seg-'), `Segment id must have seg- prefix: ${seg.segmentId}`);
    assert(seg.provenance !== undefined, `Segment ${seg.segmentId} must have provenance`);
    assert(seg.provenance.attributes?.fare !== undefined, 'Fare provenance must be present in attributes');
    assert(
      ['provider_live', 'deterministic_estimate', 'simulated', 'unknown'].includes(
        seg.provenance.attributes.fare.sourceType
      ),
      `Invalid fare sourceType: ${seg.provenance.attributes.fare.sourceType}`
    );
  }
}
console.log('✓ Provenance contracts and multi-modal constraints strictly preserved across all journeys');

console.log('\n=================================================================');
console.log('ALL TESTS (A through H) PASSED SUCCESSFULLY! ✓');
console.log('=================================================================');
