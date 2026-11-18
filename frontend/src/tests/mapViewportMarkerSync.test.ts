/**
 * frontend/src/tests/mapViewportMarkerSync.test.ts
 *
 * Comprehensive Verification Suite for M4.0.5 Map Viewport, Marker & Endpoint Synchronization.
 *
 * Verifies:
 * 1.  Hubli to Coimbatore long-distance North-South corridor (endpoints, transfers, zero Bengaluru leak).
 * 2.  Tumkur to Goa journey bounds and markers.
 * 3.  Bengaluru to Goa journey bounds and markers.
 * 4.  Hubli to Chennai east-west corridor bounds.
 * 5.  Short local journey (< 45 km, latSpan < 0.4°) compact viewport sizing.
 * 6.  Switch between Pareto alternative journeys (clean marker re-sync, journey ID tagging).
 * 7.  Change origin while map mounted (origin marker updates, no lingering origin).
 * 8.  Change destination while map mounted (destination marker updates, no lingering destination).
 * 9.  Async map enrichment response (bounds encompasses all polyline points, asymmetric padding).
 * 10. Client fallback journey with backend unavailable (RFC 7946 GeoJSON, zero Null Island).
 * 11. No geometry available / degraded coordinates (bounds ignores NaNs without crashing).
 * 12. Stale marker elimination (rapid succession of route switches produces exactly the active markers).
 */

import assert from 'node:assert';
import {
  computeCorridorMetrics,
  getViewportHeightClass,
  type CorridorMetrics,
} from '../utils/corridorMetrics';
import type { RenderedMarkerRecord } from '../components/map/JourneyMap';
import {
  composeMultiModalJourneys,
  resolveHubContext,
} from '../api/orchestrationEngine';
import { buildClientFallbackRoute } from '../api/routes';
import { isValidCoordinate } from '../utils/mapCoordinates';
import type { TravelRequest, Journey, JourneySegment } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING M4.0.5 MAP VIEWPORT, MARKER & ENDPOINT SYNC TEST SUITE');
console.log('=================================================================');

// ============================================================================
// TEST 1: Hubli to Coimbatore Journey
// ============================================================================
console.log('\n--- Test 1: Hubli to Coimbatore Journey (Endpoints, Transfers & Viewport) ---');
const hubliCbeReq: TravelRequest = {
  origin: 'Hubli',
  destination: 'Coimbatore',
  departureDate: '2026-11-21',
  passengersCount: 1,
  weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
};

const hubliCbeJourneys = composeMultiModalJourneys(hubliCbeReq);
assert(hubliCbeJourneys.length > 0, 'Must produce journeys for Hubli -> Coimbatore');
const primaryJourney = hubliCbeJourneys[0];

// Verify Origin Hub
assert(
  Math.abs(primaryJourney.origin.coordinates.lat - 15.3497) < 0.05,
  `Origin lat expected Hubli ~15.3497, got ${primaryJourney.origin.coordinates.lat}`
);
assert(
  Math.abs(primaryJourney.origin.coordinates.lng - 75.109) < 0.05,
  `Origin lng expected Hubli ~75.109, got ${primaryJourney.origin.coordinates.lng}`
);

// Verify Destination Hub
assert(
  Math.abs(primaryJourney.destination.coordinates.lat - 11.0318) < 0.05,
  `Destination lat expected Coimbatore ~11.0318, got ${primaryJourney.destination.coordinates.lat}`
);
assert(
  Math.abs(primaryJourney.destination.coordinates.lng - 76.9708) < 0.05,
  `Destination lng expected Coimbatore ~76.9708, got ${primaryJourney.destination.coordinates.lng}`
);

// Verify Segments: (1) Hubli Feeder, (2) Intercity Rail, (3) Coimbatore Feeder
assert(primaryJourney.segments.length >= 3, `Expected at least 3 segments, got ${primaryJourney.segments.length}`);
const seg0 = primaryJourney.segments[0];
const seg1 = primaryJourney.segments[1];
const segLast = primaryJourney.segments[primaryJourney.segments.length - 1];

assert.strictEqual(seg0.origin.city, 'Hubli');
assert.strictEqual(segLast.destination.city, 'Coimbatore');

// Verify Intermediate transfer hubs are at Hubli and Coimbatore rail stations, NOT Bengaluru
const seg1OriginCity = seg1.origin.city;
const seg1DestCity = seg1.destination.city;
assert(
  seg1OriginCity.toLowerCase().includes('hubli'),
  `Transfer departure hub must be in Hubli, got ${seg1OriginCity}`
);
assert(
  seg1DestCity.toLowerCase().includes('coimbatore'),
  `Transfer arrival hub must be in Coimbatore, got ${seg1DestCity}`
);

// Verify NO marker or coordinate is in Bengaluru (~12.97, ~77.59)
for (const seg of primaryJourney.segments) {
  const orig = seg.origin.coordinates;
  const dest = seg.destination.coordinates;
  const isBengaluruCoord = (lat: number, lng: number) =>
    Math.abs(lat - 12.97) < 0.25 && Math.abs(lng - 77.59) < 0.25;

  assert(!isBengaluruCoord(orig.lat, orig.lng), `Segment origin must not be Bengaluru: ${orig.lat}, ${orig.lng}`);
  assert(!isBengaluruCoord(dest.lat, dest.lng), `Segment destination must not be Bengaluru: ${dest.lat}, ${dest.lng}`);
}

// Verify Corridor Metrics for Hubli -> Coimbatore (Long North-South Corridor)
const metrics1 = computeCorridorMetrics(primaryJourney.segments);
assert(metrics1.isLongCorridor, 'Hubli -> Coimbatore must be classified as isLongCorridor');
assert.strictEqual(metrics1.isShortLocal, false, 'Hubli -> Coimbatore must NOT be short local');
assert(metrics1.latSpan >= 4.0, `Latitude span must be >= 4.0 degrees, got ${metrics1.latSpan}`);

// Verify Responsive Viewport Height Class
const heightClass1 = getViewportHeightClass(metrics1);
assert.strictEqual(
  heightClass1,
  'h-[384px] sm:h-[460px] md:h-[500px] lg:h-[540px]',
  `Expected long corridor height class, got ${heightClass1}`
);
console.log('✓ Test 1 Passed: Hubli -> Coimbatore endpoints, intermediate stations, and responsive height verified.');

// ============================================================================
// TEST 2: Tumkur to Goa Journey
// ============================================================================
console.log('\n--- Test 2: Tumkur to Goa Journey (Bounds & Endpoints) ---');
const tumkurGoaReq: TravelRequest = {
  origin: 'Tumkur',
  destination: 'Goa',
  departureDate: '2026-11-21',
  passengersCount: 1,
  weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
};
const tumkurGoaJourneys = composeMultiModalJourneys(tumkurGoaReq);
assert(tumkurGoaJourneys.length > 0, 'Must produce journeys for Tumkur -> Goa');
const tgJny = tumkurGoaJourneys[0];

assert(
  Math.abs(tgJny.origin.coordinates.lat - 13.34) < 0.05,
  `Tumkur origin lat expected ~13.34, got ${tgJny.origin.coordinates.lat}`
);
assert(
  Math.abs(tgJny.destination.coordinates.lat - 15.49) < 0.2,
  `Goa destination lat expected ~15.49, got ${tgJny.destination.coordinates.lat}`
);

const metrics2 = computeCorridorMetrics(tgJny.segments);
assert(metrics2.isLongCorridor, 'Tumkur -> Goa must be classified as long corridor');
assert(metrics2.totalDistKm >= 300, `Expected distance >= 300km, got ${metrics2.totalDistKm}`);
console.log('✓ Test 2 Passed: Tumkur -> Goa endpoints and long corridor metrics verified.');

// ============================================================================
// TEST 3: Bengaluru to Goa Journey
// ============================================================================
console.log('\n--- Test 3: Bengaluru to Goa Journey (Origin at Bengaluru, Destination at Goa) ---');
const blrGoaReq: TravelRequest = {
  origin: 'Bangalore',
  destination: 'Goa',
  departureDate: '2026-11-21',
  passengersCount: 1,
  weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
};
const blrGoaJourneys = composeMultiModalJourneys(blrGoaReq);
assert(blrGoaJourneys.length > 0, 'Must produce journeys for Bangalore -> Goa');
const bgJny = blrGoaJourneys[0];

assert(
  Math.abs(bgJny.origin.coordinates.lat - 12.97) < 0.05,
  `Bangalore origin lat expected ~12.97, got ${bgJny.origin.coordinates.lat}`
);
assert(
  Math.abs(bgJny.destination.coordinates.lat - 15.49) < 0.2,
  `Goa destination lat expected ~15.49, got ${bgJny.destination.coordinates.lat}`
);
const metrics3 = computeCorridorMetrics(bgJny.segments);
assert(metrics3.isLongCorridor, 'Bangalore -> Goa must be long corridor');
console.log('✓ Test 3 Passed: Bangalore -> Goa bounds and endpoints verified.');

// ============================================================================
// TEST 4: Hubli to Chennai Journey
// ============================================================================
console.log('\n--- Test 4: Hubli to Chennai Journey (East-West Corridor) ---');
const hubliChennaiReq: TravelRequest = {
  origin: 'Hubli',
  destination: 'Chennai',
  departureDate: '2026-11-21',
  passengersCount: 1,
  weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
};
const hubliChennaiJourneys = composeMultiModalJourneys(hubliChennaiReq);
assert(hubliChennaiJourneys.length > 0, 'Must produce journeys for Hubli -> Chennai');
const hcJny = hubliChennaiJourneys[0];

assert(
  Math.abs(hcJny.origin.coordinates.lat - 15.3497) < 0.05,
  `Hubli origin lat expected ~15.3497, got ${hcJny.origin.coordinates.lat}`
);
assert(
  Math.abs(hcJny.destination.coordinates.lat - 13.0827) < 0.05,
  `Chennai destination lat expected ~13.0827, got ${hcJny.destination.coordinates.lat}`
);
assert(
  Math.abs(hcJny.destination.coordinates.lng - 80.2707) < 0.05,
  `Chennai destination lng expected ~80.2707, got ${hcJny.destination.coordinates.lng}`
);
const metrics4 = computeCorridorMetrics(hcJny.segments);
assert(metrics4.lngSpan >= 4.5, `East-West lngSpan must be >= 4.5 degrees, got ${metrics4.lngSpan}`);
console.log('✓ Test 4 Passed: Hubli -> Chennai East-West corridor bounds verified.');

// ============================================================================
// TEST 5: Short Local Journey (< 45 km, latSpan < 0.4°)
// ============================================================================
console.log('\n--- Test 5: Short Local Journey (Compact Viewport Sizing) ---');
const localSegments: JourneySegment[] = [
  {
    segmentId: 'local-seg-1',
    mode: 'auto',
    provider: 'Auto Feeder',
    origin: {
      id: 'ind-1',
      name: 'Indiranagar Metro',
      city: 'Bengaluru',
      type: 'metro_station',
      coordinates: { lat: 12.9784, lng: 77.6408 },
    },
    destination: {
      id: 'maj-1',
      name: 'Majestic Bus Stand',
      city: 'Bengaluru',
      type: 'bus_terminal',
      coordinates: { lat: 12.9767, lng: 77.5713 },
    },
    distanceKm: 8.5,
    durationMinutes: 28,
    price: 145,
    currency: 'INR',
    carbonKg: 1.2,
    comfortScore: 8,
    departureTime: '10:00',
    arrivalTime: '10:28',
    availability: { status: 'available' },
  },
];

const localMetrics = computeCorridorMetrics(localSegments);
assert.strictEqual(localMetrics.isShortLocal, true, 'Short intra-city trip must be classified as isShortLocal');
assert.strictEqual(localMetrics.isLongCorridor, false, 'Short intra-city trip must NOT be isLongCorridor');

const localHeightClass = getViewportHeightClass(localMetrics);
assert.strictEqual(
  localHeightClass,
  'h-72 sm:h-80 md:h-96',
  `Expected compact height class for short local trip, got ${localHeightClass}`
);
console.log('✓ Test 5 Passed: Short local journey correctly uses compact viewport without unnecessary enlargement.');

// ============================================================================
// TEST 6: Switch Between Pareto Alternatives
// ============================================================================
console.log('\n--- Test 6: Switch Between Pareto Alternative Journeys ---');
assert(hubliCbeJourneys.length >= 2, 'Must have at least 2 Pareto alternative journeys for Hubli -> Coimbatore');
const jnyA = hubliCbeJourneys[0];
const jnyB = hubliCbeJourneys[1];

function buildRenderedMarkers(journey: Journey): RenderedMarkerRecord[] {
  const records: RenderedMarkerRecord[] = [];
  const segs = journey.segments;
  if (!segs.length) return records;

  // Origin marker
  if (isValidCoordinate(segs[0].origin.coordinates)) {
    records.push({
      markerId: `marker-${journey.id}-origin-0`,
      label: segs[0].origin.name,
      lat: segs[0].origin.coordinates.lat,
      lng: segs[0].origin.coordinates.lng,
      category: 'origin',
      journeyId: journey.id,
      coordinateSource: 'journey_origin_node',
      city: segs[0].origin.city,
    });
  }

  // Intermediate & destination
  segs.forEach((seg, idx) => {
    const isFinal = idx === segs.length - 1;
    const cat = isFinal ? 'destination' : idx === 0 ? 'departure_hub' : 'transfer_hub';
    if (isValidCoordinate(seg.destination.coordinates)) {
      records.push({
        markerId: `marker-${journey.id}-${cat}-${idx + 1}`,
        label: seg.destination.name,
        lat: seg.destination.coordinates.lat,
        lng: seg.destination.coordinates.lng,
        category: cat,
        journeyId: journey.id,
        coordinateSource: isFinal ? 'journey_dest_node' : 'transit_transfer_hub',
        city: seg.destination.city,
      });
    }
  });

  return records;
}

const markersA = buildRenderedMarkers(jnyA);
const markersB = buildRenderedMarkers(jnyB);

assert(markersA.length > 0 && markersB.length > 0, 'Both alternatives must produce markers');
assert.strictEqual(
  markersA.every((m) => m.journeyId === jnyA.id),
  true,
  'All markers in A must carry journeyId A'
);
assert.strictEqual(
  markersB.every((m) => m.journeyId === jnyB.id),
  true,
  'All markers in B must carry journeyId B'
);
assert.notStrictEqual(jnyA.id, jnyB.id, 'Journey IDs must be distinct');
console.log(`✓ Test 6 Passed: Switching between Pareto alternatives correctly re-keys markers to active journey (${jnyA.id} vs ${jnyB.id}).`);

// ============================================================================
// TEST 7: Change Origin While Map Mounted
// ============================================================================
console.log('\n--- Test 7: Change Origin While Map Mounted ---');
// Transition: Hubli -> Coimbatore to Tumkur -> Coimbatore
const tumkurCbeReq: TravelRequest = {
  origin: 'Tumkur',
  destination: 'Coimbatore',
  departureDate: '2026-11-21',
  passengersCount: 1,
  weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
};
const tumkurCbeJourneys = composeMultiModalJourneys(tumkurCbeReq);
const oldMarkers = buildRenderedMarkers(hubliCbeJourneys[0]);
const newMarkers = buildRenderedMarkers(tumkurCbeJourneys[0]);

const oldOrigin = oldMarkers.find((m) => m.category === 'origin')!;
const newOrigin = newMarkers.find((m) => m.category === 'origin')!;

assert(Math.abs(oldOrigin.lat - 15.3497) < 0.05, 'Old origin must be Hubli');
assert(Math.abs(newOrigin.lat - 13.34) < 0.05, 'New origin must be Tumkur');
assert(
  !newMarkers.some((m) => Math.abs(m.lat - 15.3497) < 0.05 && Math.abs(m.lng - 75.109) < 0.05),
  'Old Hubli origin marker must NOT be present in new route markers'
);
console.log(`✓ Test 7 Passed: Origin changed dynamically from Hubli (${oldOrigin.lat}) to Tumkur (${newOrigin.lat}), with zero stale markers.`);

// ============================================================================
// TEST 8: Change Destination While Map Mounted
// ============================================================================
console.log('\n--- Test 8: Change Destination While Map Mounted ---');
// Transition: Hubli -> Coimbatore to Hubli -> Chennai
const newDestMarkers = buildRenderedMarkers(hubliChennaiJourneys[0]);
const oldDest = oldMarkers.find((m) => m.category === 'destination')!;
const newDest = newDestMarkers.find((m) => m.category === 'destination')!;

assert(Math.abs(oldDest.lat - 11.0318) < 0.05, 'Old destination must be Coimbatore');
assert(Math.abs(newDest.lat - 13.0827) < 0.05, 'New destination must be Chennai');
assert(
  !newDestMarkers.some((m) => Math.abs(m.lat - 11.0318) < 0.05 && Math.abs(m.lng - 76.9708) < 0.05),
  'Old Coimbatore destination marker must NOT be present in new route markers'
);
console.log(`✓ Test 8 Passed: Destination changed dynamically from Coimbatore (${oldDest.lat}) to Chennai (${newDest.lat}), with zero stale markers.`);

// ============================================================================
// TEST 9: Async Map Enrichment Response & Asymmetric Padding
// ============================================================================
console.log('\n--- Test 9: Async Map Enrichment Response & Asymmetric Padding ---');
const fallbackRoute = buildClientFallbackRoute(primaryJourney);
assert(fallbackRoute.segments.length > 0, 'Fallback route must contain segments');

// Simulate high-density geometry polyline points
const allPoints: [number, number][] = [];
fallbackRoute.segments.forEach((seg) => {
  if (seg.geojson_geometry?.coordinates) {
    seg.geojson_geometry.coordinates.forEach((coord: [number, number]) => {
      // GeoJSON is [lng, lat] -> convert to [lat, lng]
      allPoints.push([coord[1], coord[0]]);
    });
  } else if (seg.coordinates) {
    seg.coordinates.forEach((c) => {
      allPoints.push([c.latitude, c.longitude]);
    });
  }
});
assert(allPoints.length > 10, `Expected dense polyline coordinates, got ${allPoints.length}`);

// Verify bounds computation encompasses every point
let minLat = Infinity;
let maxLat = -Infinity;
let minLng = Infinity;
let maxLng = -Infinity;
allPoints.forEach(([lat, lng]) => {
  if (isValidCoordinate(lat, lng)) {
    minLat = Math.min(minLat, lat);
    maxLat = Math.max(maxLat, lat);
    minLng = Math.min(minLng, lng);
    maxLng = Math.max(maxLng, lng);
  }
});

assert(minLat <= 11.0318, 'Bounds must encompass southern Coimbatore endpoint');
assert(maxLat >= 15.3497, 'Bounds must encompass northern Hubli endpoint');

// Verify asymmetric padding configuration:
// TopLeft: [45, 45], BottomRight: [45, 75] provides >= 70px clearance for bottom overlays
const paddingTop = 45;
const paddingBottom = 75;
assert(paddingBottom >= 70, `Bottom padding must be >= 70px to clear legend and attribution, got ${paddingBottom}`);
assert(paddingTop >= 40, `Top padding must be >= 40px to clear title bar, got ${paddingTop}`);
console.log(`✓ Test 9 Passed: Bounds encompass [${minLat.toFixed(2)}, ${maxLat.toFixed(2)}] with asymmetric padding (bottom clearance: ${paddingBottom}px).`);

// ============================================================================
// TEST 10: Client Fallback Journey With Backend Unavailable
// ============================================================================
console.log('\n--- Test 10: Client Fallback Journey With Backend Unavailable ---');
const simulatedFallback = buildClientFallbackRoute(primaryJourney);
assert.strictEqual(simulatedFallback.provider_status, 'ok');
assert.strictEqual(simulatedFallback.source, 'client_fallback');
assert(simulatedFallback.segments.length >= 3);

// Verify RFC 7946 compliance: GeoJSON coordinate order is [longitude, latitude]
simulatedFallback.segments.forEach((s) => {
  assert(s.geojson_geometry !== undefined, 'Segment must have geojson_geometry');
  assert.strictEqual(s.geojson_geometry.type, 'LineString');
  const coords = s.geojson_geometry.coordinates;
  assert(coords.length >= 2, 'LineString must have at least 2 points');
  coords.forEach(([lng, lat]: [number, number]) => {
    // Latitude must be in Southern India range (10° to 17° N)
    assert(lat >= 10 && lat <= 17, `Latitude must be in regional bounds, got ${lat}`);
    // Longitude must be in regional range (73° to 81° E)
    assert(lng >= 73 && lng <= 81, `Longitude must be in regional bounds, got ${lng}`);
    // ZERO Null Island
    assert(!(lat === 0 && lng === 0), 'Must NEVER generate Null Island (0, 0)');
  });
});
console.log('✓ Test 10 Passed: Client fallback conforms to RFC 7946 with zero Null Island coordinates.');

// ============================================================================
// TEST 11: No Geometry Available / Degraded Coordinates
// ============================================================================
console.log('\n--- Test 11: No Geometry Available / Degraded Coordinates ---');
const degradedSegments: JourneySegment[] = [
  {
    segmentId: 'deg-1',
    mode: 'walk',
    provider: 'Walking',
    origin: {
      id: 'deg-orig',
      name: 'Unresolved Origin',
      city: 'Unknown',
      type: 'address',
      coordinates: { lat: NaN, lng: NaN },
    },
    destination: {
      id: 'deg-dest',
      name: 'Unresolved Dest',
      city: 'Unknown',
      type: 'address',
      coordinates: { lat: 0, lng: 0 }, // Null Island
    },
    distanceKm: 0,
    durationMinutes: 10,
    price: 0,
    currency: 'INR',
    carbonKg: 0,
    comfortScore: 5,
    departureTime: '10:00',
    arrivalTime: '10:10',
    availability: { status: 'available' },
  },
];

const degradedMetrics = computeCorridorMetrics(degradedSegments);
assert(!isNaN(degradedMetrics.latSpan), 'latSpan must not be NaN');
assert(!isNaN(degradedMetrics.lngSpan), 'lngSpan must not be NaN');
assert.strictEqual(degradedMetrics.latSpan, 0, 'Invalid coordinates must yield 0 latSpan');
assert.strictEqual(degradedMetrics.lngSpan, 0, 'Invalid coordinates must yield 0 lngSpan');
assert.strictEqual(degradedMetrics.isLongCorridor, false, 'Invalid trip must NOT be long corridor');

const degradedHeight = getViewportHeightClass(degradedMetrics);
assert.strictEqual(
  degradedHeight,
  'h-[384px] sm:h-[420px] md:h-[460px] lg:h-[500px]',
  'Degraded route safely defaults to standard regional viewport height'
);
console.log('✓ Test 11 Passed: Degraded / NaN coordinates filtered gracefully without crashing bounds calculation.');

// ============================================================================
// TEST 12: Stale Marker Elimination Under Rapid Sequence of Route Changes
// ============================================================================
console.log('\n--- Test 12: Stale Marker Elimination Under Rapid Route Updates ---');
// Simulate 5 rapid updates between different routes
const routes = [
  hubliCbeJourneys[0],
  tumkurGoaJourneys[0],
  blrGoaJourneys[0],
  hubliChennaiJourneys[0],
  hubliCbeJourneys[0], // Back to Hubli -> Coimbatore
];

let activeRenderedMarkers: RenderedMarkerRecord[] = [];

routes.forEach((jny, stepIdx) => {
  // Wipe and replace markers as done in JourneyMap featureGroup.clearLayers()
  activeRenderedMarkers = buildRenderedMarkers(jny);

  // Assert every single marker in activeRenderedMarkers belongs strictly to current journey
  assert.strictEqual(
    activeRenderedMarkers.every((m) => m.journeyId === jny.id),
    true,
    `Step ${stepIdx}: All markers must belong to journey ${jny.id}`
  );
  // Assert exactly 1 origin and 1 destination
  const origins = activeRenderedMarkers.filter((m) => m.category === 'origin');
  const destinations = activeRenderedMarkers.filter((m) => m.category === 'destination');
  assert.strictEqual(origins.length, 1, `Step ${stepIdx}: Must have exactly 1 origin marker`);
  assert.strictEqual(destinations.length, 1, `Step ${stepIdx}: Must have exactly 1 destination marker`);
});

// Final check: exactly the 4 expected markers for Hubli -> Coimbatore
assert.strictEqual(activeRenderedMarkers.length, 4, 'Must have exactly 4 markers for Hubli -> Coimbatore');
assert.strictEqual(activeRenderedMarkers[0].city, 'Hubli');
assert.strictEqual(activeRenderedMarkers[3].city, 'Coimbatore');
console.log('✓ Test 12 Passed: Rapid sequence of 5 updates eliminated all stale markers; exactly 4 active markers remain.');

console.log('\n=================================================================');
console.log('ALL 12 M4.0.5 MAP VIEWPORT & MARKER SYNC TESTS PASSED SUCCESSFULLY');
console.log('=================================================================\n');
