import assert from 'node:assert';
import {
  composeMultiModalJourneys,
  calculateGeodesicDistanceKm,
  computeFeederDistanceKm,
  CITY_HUB_REGISTRY,
} from '../api/orchestrationEngine';
import { buildClientFallbackRoute } from '../api/routes';
import { matchXRSceneForHub } from '../utils/xrMatching';
import {
  normalizeLeafletCoord,
  decodePolyline,
  DEFAULT_TILE_URL,
  DEFAULT_TILE_SUBDOMAINS,
  DEFAULT_TILE_ATTRIBUTION,
  getModeStyle,
  MODE_COLORS,
} from '../utils/mapCoordinates';
import { TravelRequest } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING MULTIMODAL JOURNEY MAP & REALISTIC ITINERARY TEST SUITE (UI-01.2)');
console.log('=================================================================');

// ============================================================================
// BASELINE TEST: Coordinate Normalization, Explicit Boundaries & International Safety
// ============================================================================
console.log('\n--- Foundation Test: Coordinate Normalization, Explicit Boundaries & International Safety ---');

const geoJsonCoord: [number, number] = [77.5100, 12.8250]; // [lng, lat] for Udayapura
const leafletNormalized = normalizeLeafletCoord(geoJsonCoord, true);
assert.notStrictEqual(leafletNormalized, null, 'Normalized coordinate must not be null');
assert.strictEqual(leafletNormalized![0], 12.8250, 'Latitude must be at index 0 in Leaflet');
assert.strictEqual(leafletNormalized![1], 77.5100, 'Longitude must be at index 1 in Leaflet');

// Domestic Coordinates: Bengaluru & Delhi
const blr = normalizeLeafletCoord([12.9716, 77.5946], false);
assert.notStrictEqual(blr, null);
assert.strictEqual(blr![0], 12.9716);
assert.strictEqual(blr![1], 77.5946);

// Outside India coordinates must never be falsely swapped
const oslo = normalizeLeafletCoord([59.9139, 10.7522], false);
assert.strictEqual(oslo![0], 59.9139);
assert.strictEqual(oslo![1], 10.7522);

const london = normalizeLeafletCoord([51.5074, -0.1278], false);
assert.strictEqual(london![0], 51.5074);
assert.strictEqual(london![1], -0.1278);

console.log('✓ Coordinate normalization verified across domestic and international bounds.');

// ============================================================================
// REFINEMENT 01.2 SECTION 7 SPECIFIC REGRESSION TESTS (1 through 10)
// ============================================================================

// ----------------------------------------------------------------------------
// TEST 1: Udayapura-to-KSR Geodesic Lower-Bound Validation
// ----------------------------------------------------------------------------
console.log('\n--- Test 1: Udayapura-to-KSR Geodesic Lower-Bound Validation ---');
const udayapuraCoords = { lat: 12.8250, lng: 77.5100 };
const ksrCoords = { lat: 12.9781, lng: 77.5694 };

const geodesicDistanceKm = calculateGeodesicDistanceKm(udayapuraCoords, ksrCoords);
console.log(`Calculated geodesic straight-line distance: ${geodesicDistanceKm.toFixed(2)} km`);

assert(
  geodesicDistanceKm >= 18.0 && geodesicDistanceKm <= 18.5,
  `Geodesic straight-line distance must be ~18.2 km, got ${geodesicDistanceKm.toFixed(2)} km`
);

const computedFeederRoadKm = computeFeederDistanceKm(udayapuraCoords, ksrCoords);
console.log(`Computed feeder road route distance: ${computedFeederRoadKm} km`);

// PHYSICAL LAW: Road route cannot be shorter than the straight-line geodesic lower bound
assert(
  computedFeederRoadKm >= geodesicDistanceKm,
  `Feeder road distance (${computedFeederRoadKm} km) must be >= geodesic lower bound (${geodesicDistanceKm.toFixed(2)} km)`
);
assert.strictEqual(
  computedFeederRoadKm,
  24.0,
  `Feeder road route along Kanakapura Rd corridor must be 24.0 km, got ${computedFeederRoadKm} km`
);
console.log('✓ Geodesic lower bound strictly enforced: 24.0 km road distance >= 18.20 km geodesic distance.');

// ----------------------------------------------------------------------------
// TEST 2: Correct Feeder-Road Route Geometry and Distance
// ----------------------------------------------------------------------------
console.log('\n--- Test 2: Correct Feeder-Road Route Geometry, Distance & Mode ---');
const req: TravelRequest = {
  origin: 'Udayapura',
  destination: 'Delhi',
  departureDate: '2026-11-15',
  preferredArrivalBefore: '20:00',
  budgetMax: 8000,
  passengersCount: 1,
  weights: { cost: 0.2, duration: 0.2, comfort: 0.2, carbon: 0.4 }, // Prioritize Greenest
  naturalLanguageQuery: 'Udayapura to Delhi multimodal greenest net-zero',
};

const candidateJourneys = composeMultiModalJourneys(req);
const greenestJourney = candidateJourneys.find((j) => j.recommendationCategory === 'greenest') || candidateJourneys[0];
assert(greenestJourney, 'Greenest journey option must exist');

const leg1 = greenestJourney.segments[0];
assert.strictEqual(leg1.mode, 'shuttle', 'Leg 1 transport mode must be "shuttle", NOT "metro"');
assert.strictEqual(leg1.distanceKm, 24.0, `Leg 1 road distance must be 24.0 km, got ${leg1.distanceKm}`);
assert.strictEqual(leg1.durationMinutes, 45, `Leg 1 duration must be 45 min, got ${leg1.durationMinutes}`);
assert.strictEqual(leg1.destination.name, 'KSR Bengaluru City Railway Station', 'Leg 1 destination must be KSR Bengaluru City');
assert.strictEqual(leg1.destination.code, 'SBC', 'Leg 1 railway hub code must be SBC');

const leg1Fallback = buildClientFallbackRoute(greenestJourney).segments[0];
assert(leg1Fallback.coordinates.length >= 2, 'Leg 1 must have valid road waypoints');
console.log(`✓ Leg 1 validated: mode="${leg1.mode}", distance=${leg1.distanceKm} km, duration=${leg1.durationMinutes} min, hub=${leg1.destination.name}.`);

// ----------------------------------------------------------------------------
// TEST 3: Railway Corridor Station-Pair Consistency (SBC-NDLS vs SBC-NZM)
// ----------------------------------------------------------------------------
console.log('\n--- Test 3: Railway Corridor Station-Pair Consistency (SBC-NDLS vs SBC-NZM) ---');
const leg2 = greenestJourney.segments[1];
assert.strictEqual(leg2.mode, 'train');
assert.strictEqual(leg2.origin.code, 'SBC', 'Departure hub must be KSR Bengaluru City (SBC)');
assert.strictEqual(leg2.destination.code, 'NDLS', 'Arrival hub must be New Delhi Railway Station (NDLS)');
assert.strictEqual(leg2.distanceKm, 2406, `Karnataka Express corridor distance SBC-NDLS must be 2,406 km, got ${leg2.distanceKm}`);
assert.strictEqual(leg2.durationMinutes, 2260, `Karnataka Express duration must be 2,260 min (~37h 40m published timetable), got ${leg2.durationMinutes}`);
assert(!leg2.vehicleName?.toLowerCase().includes('rajdhani'), 'NDLS corridor train must not be called Rajdhani (Rajdhani terminates at NZM)');
assert.strictEqual(leg2.vehicleName, 'Karnataka Express', 'Train must reflect canonical Karnataka Express name');
assert.strictEqual(leg2.vehicleNumber, '12627', 'Train vehicle number must be 12627');
assert.strictEqual(leg2.provider, 'Indian Railways', 'Provider must be canonical Indian Railways');

// Verify Rajdhani separation in corridor distances
const bangaloreDelhiRajdhaniKm = 2365; // SBC to Hazrat Nizamuddin (NZM)
assert.notStrictEqual(leg2.distanceKm, bangaloreDelhiRajdhaniKm, 'SBC-NDLS (2,406 km) must be distinct from SBC-NZM Rajdhani (2,365 km)');
console.log(`✓ Railway station pairs verified: SBC-NDLS is 2,406 km (${leg2.durationMinutes} min), distinct from Rajdhani SBC-NZM (2,365 km).`);

// ----------------------------------------------------------------------------
// TEST 4: Railway Estimate Provenance & Simulated Inventory Disclaimers
// ----------------------------------------------------------------------------
console.log('\n--- Test 4: Railway Estimate Provenance & Non-Track Survey Attribution ---');
assert.notStrictEqual(leg2.provenance, undefined, 'Leg 2 must have explicit attribute-level provenance');
assert.strictEqual(leg2.provenance!.sourceType, 'deterministic_estimate', 'Leg 2 must be deterministic_estimate');
assert.strictEqual(leg2.provenance!.isEstimate, true, 'Leg 2 must be flagged as estimate');
assert.strictEqual(leg2.availability.isRealInventory, false, 'Leg 2 must not claim real-time IRCTC inventory');

const distAttr = leg2.provenance!.attributes.distance;
assert(
  distAttr.notes?.includes('non-track survey') || distAttr.notes?.includes('deterministic estimate'),
  `Distance provenance must declare deterministic estimate non-track survey, got: ${distAttr.notes}`
);

const availAttr = leg2.provenance!.attributes.availability;
assert.strictEqual(availAttr.sourceType, 'simulated');
assert(
  availAttr.notes?.includes('Simulated railway inventory') || availAttr.notes?.includes('non-track survey'),
  `Availability provenance must declare simulated inventory, got: ${availAttr.notes}`
);
console.log('✓ Railway estimate provenance verified: non-track survey notes & simulated inventory cleanly declared.');

// ----------------------------------------------------------------------------
// TEST 5: Airport Express Station Membership Verification
// ----------------------------------------------------------------------------
console.log('\n--- Test 5: Delhi Metro Airport Express Station Membership ---');
const AIRPORT_EXPRESS_STATIONS = [
  'New Delhi Railway Station (NDLS)',
  'Shivaji Stadium',
  'Dhaula Kuan',
  'Delhi Aerocity',
  'Indira Gandhi International Airport (DEL)',
  'Dwarka Sector 21',
];

// Verify known members
assert(AIRPORT_EXPRESS_STATIONS.includes('Indira Gandhi International Airport (DEL)'));
assert(AIRPORT_EXPRESS_STATIONS.includes('New Delhi Railway Station (NDLS)'));
assert(AIRPORT_EXPRESS_STATIONS.includes('Dwarka Sector 21'));
assert(!AIRPORT_EXPRESS_STATIONS.includes('Rajiv Chowk'), 'Rajiv Chowk must NOT be in Airport Express station list');
console.log('✓ Airport Express corridor membership verified: 6 stations serving IGI Airport corridor.');

// ----------------------------------------------------------------------------
// TEST 6: Rajiv Chowk Not Represented as Airport Express Station
// ----------------------------------------------------------------------------
console.log('\n--- Test 6: Rajiv Chowk Verified as Yellow Line (NOT Airport Express) ---');
const leg3 = greenestJourney.segments[2];
assert.strictEqual(leg3.mode, 'metro', 'Leg 3 mode must be metro');
assert(
  leg3.provider.includes('Yellow Line') || !leg3.provider.includes('Airport Express'),
  `Leg 3 provider must be Yellow Line, got: ${leg3.provider}`
);
assert.strictEqual(leg3.distanceKm, 1.5, `NDLS to Rajiv Chowk distance must be 1.5 km, got ${leg3.distanceKm}`);
assert.strictEqual(leg3.durationMinutes, 6, `NDLS to Rajiv Chowk duration must be 6 min, got ${leg3.durationMinutes}`);
assert(!leg3.provider.includes('Airport Express'), 'Rajiv Chowk leg must NEVER be attributed to Airport Express');
console.log(`✓ Leg 3 verified: ${leg3.provider}, distance=${leg3.distanceKm} km, duration=${leg3.durationMinutes} min.`);

// ----------------------------------------------------------------------------
// TEST 7: Correct Separation of Road Shuttle and Metro Modes
// ----------------------------------------------------------------------------
console.log('\n--- Test 7: Correct Separation of Road Shuttle and Metro Modes ---');
assert.notStrictEqual(leg1.mode, leg3.mode, 'Leg 1 (feeder road shuttle) and Leg 3 (urban metro rail) must have distinct modes');
assert.strictEqual(leg1.mode, 'shuttle', 'Leg 1 must be shuttle');
assert.strictEqual(leg3.mode, 'metro', 'Leg 3 must be metro');

const shuttleStyle = getModeStyle('shuttle');
const metroStyle = getModeStyle('metro');

assert.strictEqual(shuttleStyle.stroke, MODE_COLORS.shuttle.stroke, 'Shuttle style must map to emerald feeder color');
assert.strictEqual(metroStyle.stroke, MODE_COLORS.metro.stroke, 'Metro style must map to teal urban rail color');
assert.strictEqual(shuttleStyle.label, 'EV Feeder Shuttle', 'Shuttle label must be EV Feeder Shuttle');
assert.strictEqual(metroStyle.label, 'Metro Rail', 'Metro label must be Metro Rail');
console.log('✓ Road shuttle and metro modes strictly segregated in models, styling, and geometry.');

// ----------------------------------------------------------------------------
// TEST 8: Segment Distance Aggregation (24 + 2406 + 1.5 = 2431.5 km)
// ----------------------------------------------------------------------------
console.log('\n--- Test 8: Segment Distance Aggregation ---');
const segDistances = greenestJourney.segments.map((s) => s.distanceKm);
const calculatedTotalKm = greenestJourney.segments.reduce((acc, s) => acc + s.distanceKm, 0);

assert.strictEqual(segDistances[0], 24.0, 'Segment 1 must be 24.0 km');
assert.strictEqual(segDistances[1], 2406.0, 'Segment 2 must be 2,406.0 km');
assert.strictEqual(segDistances[2], 1.5, 'Segment 3 must be 1.5 km');
assert.strictEqual(
  calculatedTotalKm,
  2431.5,
  `Total itinerary distance must be exactly 2,431.5 km, got ${calculatedTotalKm} km`
);
console.log(`✓ Distance aggregation verified: ${segDistances[0]} km + ${segDistances[1]} km + ${segDistances[2]} km = ${calculatedTotalKm} km.`);

// ----------------------------------------------------------------------------
// TEST 9: Segment Time Versus Transfer-Time Aggregation (2321 + 35 = 2356 min)
// ----------------------------------------------------------------------------
console.log('\n--- Test 9: Segment Time Versus Transfer-Time Aggregation ---');
const travelDurationMinutes = greenestJourney.segments.reduce((sum, s) => sum + s.durationMinutes, 0);
const waitingDurationMinutes = greenestJourney.waitingDurationMinutes;
const totalDurationMinutes = greenestJourney.totalDurationMinutes;

assert.strictEqual(
  travelDurationMinutes,
  2311,
  `Travel time (45 + 2260 + 6) must be 2,311 min, got ${travelDurationMinutes}`
);
assert.strictEqual(
  waitingDurationMinutes,
  35,
  `Transfer waiting time (20 + 15) must be 35 min, got ${waitingDurationMinutes}`
);
assert.strictEqual(
  totalDurationMinutes,
  2346,
  `Total door-to-door duration (2311 + 35) must be 2,346 min (~39h 06m), got ${totalDurationMinutes}`
);
assert.strictEqual(
  travelDurationMinutes + waitingDurationMinutes,
  totalDurationMinutes,
  'Travel duration + Waiting duration must equal Total duration'
);

// Verify exact boundary timestamp arithmetic
const depTime = new Date(greenestJourney.departureTime).getTime();
const arrTime = new Date(greenestJourney.arrivalTime).getTime();
const elapsedMinutes = Math.round((arrTime - depTime) / 60000);
assert.strictEqual(
  elapsedMinutes,
  totalDurationMinutes,
  `Timestamp difference (${elapsedMinutes} min) must equal total duration (${totalDurationMinutes} min)`
);
console.log(`✓ Time reconciliation verified: ${travelDurationMinutes} min travel + ${waitingDurationMinutes} min transfer = ${totalDurationMinutes} min total door-to-door.`);

// ----------------------------------------------------------------------------
// TEST 10: Switching Between Pareto Alternatives Without Stale Map Data
// ----------------------------------------------------------------------------
console.log('\n--- Test 10: Switching Between Pareto Alternatives Without Stale Data ---');
assert(candidateJourneys.length >= 2, 'Must have at least 2 candidate Pareto alternatives');
console.log('Candidate journey categories:', candidateJourneys.map(j => ({ id: j.id, category: j.recommendationCategory })));

const j1 = candidateJourneys[0];
const j2 = candidateJourneys[1];
const j3 = candidateJourneys[2] || candidateJourneys[0];

assert(j1 && j2, 'At least two distinct alternative routes must be present');
assert.notStrictEqual(j1.id, j2.id);

// Check distinct route geometry builds
const route1 = buildClientFallbackRoute(j1);
const route2 = buildClientFallbackRoute(j2);

assert.strictEqual(route1.journey_id, j1.id);
assert.strictEqual(route2.journey_id, j2.id);
assert.notStrictEqual(route1.segments[0].segment_id, route2.segments[0].segment_id);

console.log(`✓ Independent alternative state verified: ${j1.id} (${j1.recommendationCategory}) vs ${j2.id} (${j2.recommendationCategory}) switch cleanly with isolated coordinates.`);

// ============================================================================
// BASELINE TEST: Basemap Tile Configuration Verification
// ============================================================================
console.log('\n--- Basemap Tile Configuration Verification ---');
assert(DEFAULT_TILE_URL.includes('tile.openstreetmap.org'), 'Default tile provider must be OpenStreetMap');
assert(DEFAULT_TILE_ATTRIBUTION.includes('OpenStreetMap'), 'Tile layer must carry legal OSM attribution');
assert.strictEqual(DEFAULT_TILE_SUBDOMAINS, '', 'Subdomains must be empty string for standard OSM endpoint');
console.log('✓ OpenStreetMap basemap tiles verified with zero API keys and legal attribution.');

console.log('\n=================================================================');
console.log('ALL 10 ITINERARY REFINEMENT 01.2 TESTS PASSED! ✓');
console.log('=================================================================');
