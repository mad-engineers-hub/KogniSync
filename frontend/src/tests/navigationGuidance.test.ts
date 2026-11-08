import assert from 'node:assert';
import {
  mapValhallaManeuverTypeToAction,
  formatDistanceMeters,
  formatDurationSeconds,
  normalizeManeuvers,
  getSegmentGuidance,
} from '../services/navigation/maneuverEngine';
import { calculateTransferReadiness } from '../services/navigation/transferReadiness';
import {
  createInitialProgress,
  markSegmentCompleted,
  undoSegmentCompleted,
  markManeuverCompleted,
  advanceToNextSegment,
  setActiveSegment,
  calculateOverallProgressPercent,
  loadStoredProgress,
  saveProgressToStorage,
  clearStoredProgress,
} from '../services/navigation/journeyProgressStore';
import {
  startForegroundLocationTracking,
  stopForegroundLocationTracking,
  createDemoPosition,
  isForegroundTrackingActive,
} from '../services/navigation/foregroundGps';
import type { JourneySegment } from '../types/journey';
import type { SegmentRouteGeometry } from '../types/route';

console.log('=================================================================');
console.log('RUNNING NAVIGATION GUIDANCE & JOURNEY PROGRESS TEST SUITE (M3.6)');
console.log('=================================================================');

// ============================================================================
// 1. MANEUVER NORMALIZATION & ROAD COSTING
// ============================================================================
console.log('\n--- 1. Maneuver Normalization & Road Costing ---');

// Test 1.1: Valhalla type code to action mapping (Official Valhalla enum)
assert.strictEqual(mapValhallaManeuverTypeToAction(1), 'depart', 'Type 1 must map to depart');
assert.strictEqual(mapValhallaManeuverTypeToAction(4), 'arrive', 'Type 4 must map to arrive');
assert.strictEqual(mapValhallaManeuverTypeToAction(7), 'continue', 'Type 7 (kBecomes) must map to continue');
assert.strictEqual(mapValhallaManeuverTypeToAction(8), 'continue', 'Type 8 (kContinue) must map to continue');
assert.strictEqual(mapValhallaManeuverTypeToAction(9), 'slight_right', 'Type 9 (kSlightRight) must map to slight_right');
assert.strictEqual(mapValhallaManeuverTypeToAction(10), 'right', 'Type 10 (kRight) must map to right');
assert.strictEqual(mapValhallaManeuverTypeToAction(11), 'sharp_right', 'Type 11 (kSharpRight) must map to sharp_right');
assert.strictEqual(mapValhallaManeuverTypeToAction(12), 'u_turn', 'Type 12 (kUturnRight) must map to u_turn');
assert.strictEqual(mapValhallaManeuverTypeToAction(13), 'u_turn', 'Type 13 (kUturnLeft) must map to u_turn');
assert.strictEqual(mapValhallaManeuverTypeToAction(14), 'sharp_left', 'Type 14 (kSharpLeft) must map to sharp_left');
assert.strictEqual(mapValhallaManeuverTypeToAction(15), 'left', 'Type 15 (kLeft) must map to left');
assert.strictEqual(mapValhallaManeuverTypeToAction(16), 'slight_left', 'Type 16 (kSlightLeft) must map to slight_left');
assert.strictEqual(mapValhallaManeuverTypeToAction(17), 'ramp', 'Type 17 (kRampStraight) must map to ramp');
assert.strictEqual(mapValhallaManeuverTypeToAction(22), 'continue', 'Type 22 (kStayStraight) must map to continue');
assert.strictEqual(mapValhallaManeuverTypeToAction(23), 'slight_right', 'Type 23 (kStayRight) must map to slight_right');
assert.strictEqual(mapValhallaManeuverTypeToAction(24), 'slight_left', 'Type 24 (kStayLeft) must map to slight_left');
assert.strictEqual(mapValhallaManeuverTypeToAction(25), 'merge', 'Type 25 (kMerge) must map to merge');
assert.strictEqual(mapValhallaManeuverTypeToAction(26), 'roundabout', 'Type 26 (kRoundaboutEnter) must map to roundabout');
assert.strictEqual(mapValhallaManeuverTypeToAction(27), 'roundabout', 'Type 27 (kRoundaboutExit) must map to roundabout');
assert.strictEqual(mapValhallaManeuverTypeToAction(28), 'ferry', 'Type 28 (kFerryEnter) must map to ferry');
assert.strictEqual(mapValhallaManeuverTypeToAction(37), 'merge', 'Type 37 (kMergeRight) must map to merge');
assert.strictEqual(mapValhallaManeuverTypeToAction(undefined), 'generic', 'Undefined type must map to generic');
assert.strictEqual(mapValhallaManeuverTypeToAction(999), 'generic', 'Unknown type must map to generic');
console.log('✓ Valhalla maneuver type codes successfully mapped to standardized navigation actions.');

// Test 1.2: Distance and Duration formatting
assert.strictEqual(formatDistanceMeters(0), '0 m');
assert.strictEqual(formatDistanceMeters(350), '350 m');
assert.strictEqual(formatDistanceMeters(1200), '1.2 km');
assert.strictEqual(formatDistanceMeters(18500), '19 km');
assert.strictEqual(formatDistanceMeters(-5), '0 m');

assert.strictEqual(formatDurationSeconds(0), '0 min');
assert.strictEqual(formatDurationSeconds(45), '1 min');
assert.strictEqual(formatDurationSeconds(300), '5 min');
assert.strictEqual(formatDurationSeconds(3600), '1h');
assert.strictEqual(formatDurationSeconds(5400), '1h 30m');
console.log('✓ Distance and duration formatting units verified.');

// Test 1.3: Normalizing raw Valhalla maneuvers
const rawValhallaManeuvers = [
  {
    instruction: 'Drive southwest on Anna Salai.',
    distance_meters: 450,
    time_seconds: 45,
    type: 1,
    street_names: ['Anna Salai'],
    begin_shape_index: 0,
    end_shape_index: 3,
  },
  {
    instruction: 'Turn right onto Mount Road.',
    distance_meters: 1800,
    time_seconds: 180,
    type: 10, // Valhalla kRight = 10
    street_names: ['Mount Road'],
    begin_shape_index: 4,
    end_shape_index: 12,
  },
];

const normalized = normalizeManeuvers(rawValhallaManeuvers, [0]);
assert.strictEqual(normalized.length, 2, 'Must normalize exactly 2 maneuvers');
assert.strictEqual(normalized[0].action, 'depart');
assert.strictEqual(normalized[0].formattedDistance, '450 m');
assert.strictEqual(normalized[0].formattedDuration, '1 min');
assert.strictEqual(normalized[0].isCompleted, true, 'First maneuver should be marked completed');
assert.strictEqual(normalized[1].action, 'right');
assert.strictEqual(normalized[1].formattedDistance, '1.8 km');
assert.strictEqual(normalized[1].formattedDuration, '3 min');
assert.strictEqual(normalized[1].isCompleted, false, 'Second maneuver should not be completed');
console.log('✓ Raw Valhalla maneuvers normalized with correct actions, formatting, and completion states.');

// Test 1.4: Missing or invalid maneuver response handling and bounds checks
assert.deepStrictEqual(normalizeManeuvers(undefined), [], 'Undefined maneuvers must return empty array');
assert.deepStrictEqual(normalizeManeuvers([]), [], 'Empty maneuvers must return empty array');
const malformedManeuver = normalizeManeuvers([{ instruction: '', distance_meters: undefined, time_seconds: undefined } as any]);
assert.strictEqual(malformedManeuver.length, 1);
assert.strictEqual(malformedManeuver[0].distanceMeters, 0);
assert.strictEqual(malformedManeuver[0].durationSeconds, 0);

// Test 1.5: begin_shape_index polyline bounds guard (negative or beyond length)
const mockCoords = [{ latitude: 12.97, longitude: 77.59 }, { latitude: 12.98, longitude: 77.60 }];
const oobManeuvers = [
  { instruction: 'Turn left', type: 15, begin_shape_index: 999 }, // out of bounds
  { instruction: 'Turn slight left', type: 16, begin_shape_index: -1 }, // negative index
];
const normalizedOob = normalizeManeuvers(oobManeuvers, [], mockCoords);
assert.strictEqual(normalizedOob[0].location, undefined, 'Out of bounds index must safely yield undefined location without throw');
assert.strictEqual(normalizedOob[1].location, undefined, 'Negative index must safely yield undefined location');
console.log('✓ Maneuver normalization bounds checks verified (negative & out-of-bounds indices safe).');

// ============================================================================
// 2. MULTIMODAL SEGMENT GUIDANCE & PROVENANCE
// ============================================================================
console.log('\n--- 2. Multimodal Segment Guidance & Provenance ---');

const roadSegment: JourneySegment = {
  segmentId: 'seg-cab-01',
  sequence: 1,
  mode: 'cab',
  provider: 'SyncCab City Priority',
  origin: { id: 'orig', name: 'Chennai Central', city: 'Chennai', type: 'railway_station', coordinates: { lat: 13.082, lng: 80.27 } },
  destination: { id: 'dest', name: 'Chennai Airport (MAA)', city: 'Chennai', type: 'airport', coordinates: { lat: 12.99, lng: 80.17 } },
  departureTime: '2026-11-08T08:00:00Z',
  arrivalTime: '2026-11-08T08:40:00Z',
  durationMinutes: 40,
  price: 550,
  currency: 'INR',
  availability: { status: 'available' },
  distanceKm: 18.5,
  carbonKg: 3.2,
  comfortScore: 8,
  transferBufferMinutes: 35,
};

const liveRoadGeometry: SegmentRouteGeometry = {
  segment_id: 'seg-cab-01',
  mode: 'cab',
  origin_title: 'Chennai Central',
  origin_city: 'Chennai',
  destination_title: 'Chennai Airport (MAA)',
  destination_city: 'Chennai',
  origin_coords: { latitude: 13.082, longitude: 80.27 },
  destination_coords: { latitude: 12.99, longitude: 80.17 },
  coordinates: [{ latitude: 13.082, longitude: 80.27 }, { latitude: 12.99, longitude: 80.17 }],
  distance_meters: 18500,
  duration_seconds: 2400,
  is_live_geometry: true,
  source: 'valhalla_live',
  maneuvers: rawValhallaManeuvers,
};

// Test 2.1: Road segment with live Valhalla maneuvers
const roadGuidance = getSegmentGuidance(roadSegment, 1, liveRoadGeometry);
assert.strictEqual(roadGuidance.isLiveManeuvers, true, 'Road segment with live geometry must have isLiveManeuvers: true');
assert.strictEqual(roadGuidance.provenanceBadge, 'Valhalla OSM Live');
assert.strictEqual(roadGuidance.maneuvers.length, 2);
assert.strictEqual(roadGuidance.independentVerificationRequired, false);
console.log('✓ Road segment with verified Valhalla maneuvers properly receives live navigation state.');

// Test 2.2: Train segment must NEVER have turn-by-turn maneuvers, even if geometry exists
const trainSegment: JourneySegment = {
  segmentId: 'seg-train-02',
  sequence: 2,
  mode: 'train',
  provider: 'Indian Railways',
  vehicleNumber: '12658',
  vehicleName: 'Chennai Mail Express',
  origin: { id: 'orig', name: 'Chennai Central', city: 'Chennai', type: 'railway_station', coordinates: { lat: 13.082, lng: 80.27 } },
  destination: { id: 'dest', name: 'KSR Bengaluru', city: 'Bengaluru', type: 'railway_station', coordinates: { lat: 12.978, lng: 77.57 } },
  departureTime: '2026-11-08T09:15:00Z',
  arrivalTime: '2026-11-08T14:00:00Z',
  durationMinutes: 285,
  price: 450,
  currency: 'INR',
  availability: { status: 'available' },
  distanceKm: 360,
  carbonKg: 9.5,
  comfortScore: 7,
  transferBufferMinutes: 20,
};

const trainGeometry: SegmentRouteGeometry = {
  segment_id: 'seg-train-02',
  mode: 'train',
  origin_title: 'Chennai Central',
  origin_city: 'Chennai',
  destination_title: 'KSR Bengaluru',
  destination_city: 'Bengaluru',
  origin_coords: { latitude: 13.082, longitude: 80.27 },
  destination_coords: { latitude: 12.978, longitude: 77.57 },
  coordinates: [{ latitude: 13.082, longitude: 80.27 }, { latitude: 12.978, longitude: 77.57 }],
  distance_meters: 360000,
  duration_seconds: 17100,
  is_live_geometry: false,
  source: 'deterministic_train_corridor',
  maneuvers: [], // No maneuvers for trains
};

const trainGuidance = getSegmentGuidance(trainSegment, 2, trainGeometry);
assert.strictEqual(trainGuidance.isLiveManeuvers, false, 'Train corridor must never claim live maneuvers');
assert.strictEqual(trainGuidance.hasManeuvers, false, 'Train corridor must have 0 maneuvers');
assert.strictEqual(trainGuidance.independentVerificationRequired, true, 'Train must require independent verification');
assert(trainGuidance.independentVerificationNotice?.includes('Platform'), 'Must advise independent platform verification');
console.log('✓ Non-road train segment correctly enforces independent platform verification and zero fabricated maneuvers.');

// Test 2.3: Flight segment must require terminal/gate verification
const flightSegment: JourneySegment = {
  ...trainSegment,
  segmentId: 'seg-flight-03',
  mode: 'flight',
  provider: 'IndiGo Air',
  vehicleNumber: '6E-452',
};
const flightGuidance = getSegmentGuidance(flightSegment, 3);
assert.strictEqual(flightGuidance.isLiveManeuvers, false);
assert.strictEqual(flightGuidance.independentVerificationRequired, true);
assert(flightGuidance.independentVerificationNotice?.includes('Terminal') || flightGuidance.independentVerificationNotice?.includes('gate'));
console.log('✓ Flight segment correctly enforces airline terminal and gate verification notice.');

// ============================================================================
// 3. TRANSFER READINESS & CONNECTION COUNTDOWN
// ============================================================================
console.log('\n--- 3. Transfer Readiness & Connection Countdown ---');

const baseIncoming: JourneySegment = {
  ...roadSegment,
  arrivalTime: '2026-11-08T10:00:00Z',
  transferBufferMinutes: 30,
};

const baseOutgoing: JourneySegment = {
  ...trainSegment,
  departureTime: '2026-11-08T10:30:00Z',
};

// Test 3.1: Upcoming state (arrival is 45 minutes in the future)
const refTimeUpcoming = new Date('2026-11-08T09:15:00Z').getTime();
const readinessUpcoming = calculateTransferReadiness(baseIncoming, baseOutgoing, refTimeUpcoming);
assert.strictEqual(readinessUpcoming.state, 'upcoming');
assert.strictEqual(readinessUpcoming.availableBufferMinutes, 30);
assert.strictEqual(readinessUpcoming.minutesUntilTransfer, 45);
assert.strictEqual(readinessUpcoming.badgeColor, 'emerald');
console.log('✓ State "upcoming" correctly calculated for future transfer.');

// Test 3.2: Prepare state (arrival is within 10 minutes)
const refTimePrepare = new Date('2026-11-08T09:50:00Z').getTime();
const readinessPrepare = calculateTransferReadiness(baseIncoming, baseOutgoing, refTimePrepare);
assert.strictEqual(readinessPrepare.state, 'prepare');
assert.strictEqual(readinessPrepare.minutesUntilTransfer, 10);
assert.strictEqual(readinessPrepare.badgeColor, 'amber');
console.log('✓ State "prepare" correctly triggered when arrival is within 15 minutes.');

// Test 3.3: Tight Connection state (available buffer is only 7 minutes)
const tightIncoming: JourneySegment = {
  ...baseIncoming,
  arrivalTime: '2026-11-08T10:23:00Z',
  transferBufferMinutes: 20,
};
const readinessTight = calculateTransferReadiness(tightIncoming, baseOutgoing, refTimeUpcoming);
assert.strictEqual(readinessTight.state, 'tight_connection');
assert.strictEqual(readinessTight.availableBufferMinutes, 7);
assert.strictEqual(readinessTight.badgeColor, 'amber');
console.log('✓ State "tight_connection" triggered when available buffer < 10m or < required buffer.');

// Test 3.4: In-progress state (incoming segment completed, waiting at hub)
const completedSetIncoming = new Set([baseIncoming.segmentId]);
const readinessInProgress = calculateTransferReadiness(baseIncoming, baseOutgoing, refTimePrepare, completedSetIncoming);
assert.strictEqual(readinessInProgress.state, 'in_progress');
assert.strictEqual(readinessInProgress.badgeColor, 'blue');
assert(readinessInProgress.stateTitle.includes('Transfer In Progress'));
console.log('✓ State "in_progress" verified when incoming segment is marked completed.');

// Test 3.5: Completed state (both segments completed)
const completedSetBoth = new Set([baseIncoming.segmentId, baseOutgoing.segmentId]);
const readinessCompleted = calculateTransferReadiness(baseIncoming, baseOutgoing, refTimePrepare, completedSetBoth);
assert.strictEqual(readinessCompleted.state, 'completed');
assert.strictEqual(readinessCompleted.badgeColor, 'emerald');
console.log('✓ State "completed" verified when both incoming and outgoing segments are finished.');

// Test 3.6: Missed Estimated state (current time has elapsed past outgoing departure time)
const refTimePast = new Date('2026-11-08T10:35:00Z').getTime();
const readinessMissed = calculateTransferReadiness(baseIncoming, baseOutgoing, refTimePast, new Set());
assert.strictEqual(readinessMissed.state, 'missed_estimated');
assert.strictEqual(readinessMissed.badgeColor, 'rose');
console.log('✓ State "missed_estimated" correctly flagged when scheduled departure has elapsed without completion.');

// Test 3.7: Unknown state (missing or malformed timestamps)
const malformedIncoming: JourneySegment = { ...baseIncoming, arrivalTime: '' };
const readinessUnknown = calculateTransferReadiness(malformedIncoming, baseOutgoing, refTimeUpcoming);
assert.strictEqual(readinessUnknown.state, 'unknown');
assert.strictEqual(readinessUnknown.badgeColor, 'slate');
console.log('✓ State "unknown" returned safely for missing/invalid timestamps.');

// Test 3.8: Overnight journey transfer safety
const overnightIncoming: JourneySegment = {
  ...baseIncoming,
  arrivalTime: '2026-11-08T23:45:00Z',
};
const overnightOutgoing: JourneySegment = {
  ...baseOutgoing,
  departureTime: '2026-11-09T01:15:00Z', // Crosses midnight
};
const refTimeNight = new Date('2026-11-08T23:00:00Z').getTime();
const readinessOvernight = calculateTransferReadiness(overnightIncoming, overnightOutgoing, refTimeNight);
assert.strictEqual(readinessOvernight.state, 'upcoming');
assert.strictEqual(readinessOvernight.availableBufferMinutes, 90, 'Overnight buffer must be 90 minutes across midnight');
assert.strictEqual(readinessOvernight.minutesUntilTransfer, 45);
console.log('✓ Overnight journey crossing midnight boundary correctly calculated without negative buffer.');

// Test 3.9: Precedence: elapsed departure must yield missed_estimated even if buffer is tight
const tightElapsed = calculateTransferReadiness(tightIncoming, baseOutgoing, refTimePast, new Set());
assert.strictEqual(tightElapsed.state, 'missed_estimated', 'Elapsed departure must report missed_estimated rather than tight_connection');
assert.strictEqual(tightElapsed.badgeColor, 'rose');
console.log('✓ Precedence verified: missed_estimated takes priority over tight_connection when departure elapsed.');

// Test 3.10: Completed state is immutable and never overwritten by elapsed time
const completedAfterDeparture = calculateTransferReadiness(baseIncoming, baseOutgoing, refTimePast, completedSetBoth);
assert.strictEqual(completedAfterDeparture.state, 'completed', 'Completed state must never be overwritten by elapsed time');
console.log('✓ Completed progress immutability verified (never overwritten by elapsed-time calculations).');

// ============================================================================
// 4. JOURNEY PROGRESS STATE MACHINE & STORAGE
// ============================================================================
console.log('\n--- 4. Journey Progress State Machine & Storage ---');

const journeyId = 'jny-test-journey-progress';
let state = createInitialProgress(journeyId);
assert.strictEqual(state.journeyId, journeyId);
assert.strictEqual(state.activeSegmentIndex, 0);
assert.strictEqual(state.completedSegmentIds.length, 0);
assert.strictEqual(state.isDeviceLocal, true);
assert.strictEqual(calculateOverallProgressPercent(state, 3), 0);

// Test 4.1: Mark segment 1 completed
state = markSegmentCompleted(state, 'seg-1', 3);
assert.strictEqual(state.completedSegmentIds.includes('seg-1'), true);
assert.strictEqual(state.activeSegmentIndex, 1, 'Active index should advance to 1');
assert.strictEqual(calculateOverallProgressPercent(state, 3), 33);

// Test 4.2: Mark maneuver 2 of segment 2 completed
state = markManeuverCompleted(state, 'seg-2', 2);
assert.deepStrictEqual(state.completedManeuverIndices['seg-2'], [2]);

// Test 4.3: Advance next segment manually
state = advanceToNextSegment(state, 3);
assert.strictEqual(state.activeSegmentIndex, 2);

// Test 4.4: Mark segment 2 completed
state = markSegmentCompleted(state, 'seg-2', 3);
assert.strictEqual(calculateOverallProgressPercent(state, 3), 67);

// Test 4.5: Undo segment 1 completion
state = undoSegmentCompleted(state, 'seg-1');
assert.strictEqual(state.completedSegmentIds.includes('seg-1'), false);
assert.strictEqual(state.completedSegmentIds.includes('seg-2'), true);
assert.strictEqual(calculateOverallProgressPercent(state, 3), 33);

// Test 4.6: Explicit segment selection
state = setActiveSegment(state, 0, 3);
assert.strictEqual(state.activeSegmentIndex, 0);

// Test 4.7: LocalStorage mock test
let mockStorage: Record<string, string> = {};
(globalThis as any).window = {
  localStorage: {
    getItem: (key: string) => mockStorage[key] || null,
    setItem: (key: string, val: string) => { mockStorage[key] = val; },
    removeItem: (key: string) => { delete mockStorage[key]; },
  },
};

saveProgressToStorage(state);
const loaded = loadStoredProgress(journeyId);
assert(loaded !== null, 'Saved progress must be recoverable');
assert.strictEqual(loaded?.journeyId, journeyId);
assert.strictEqual(loaded?.activeSegmentIndex, 0);
assert.strictEqual(loaded?.completedSegmentIds.includes('seg-2'), true);

clearStoredProgress(journeyId);
const cleared = loadStoredProgress(journeyId);
assert.strictEqual(cleared, null, 'Progress must be null after clearing');
console.log('✓ Journey progress state machine, percentage, undo, and device-local storage verified.');

// ============================================================================
// 5. FOREGROUND GPS LIFECYCLE
// ============================================================================
console.log('\n--- 5. Foreground GPS Lifecycle ---');

// Test 5.1: Demo position simulation
const demoCoords = { latitude: 12.978, longitude: 77.572 };
const demoPos = createDemoPosition(demoCoords, 10);
assert.strictEqual(demoPos.status, 'demo_position', 'Must be explicitly labeled demo_position');
assert.strictEqual(demoPos.accuracyMeters, 10);
assert.strictEqual(demoPos.coords?.latitude, 12.978);
assert.strictEqual(demoPos.coords?.longitude, 77.572);
console.log('✓ Demo position simulation generates truth-labeled non-GPS state.');

// Test 5.2: Geolocation browser mock & foreground tracking
let mockWatchCallback: any = null;
let mockErrorCallback: any = null;
let clearedWatchId: number | null = null;

const mockNavigator = {
  geolocation: {
    watchPosition: (success: any, error: any) => {
      mockWatchCallback = success;
      mockErrorCallback = error;
      return 101;
    },
    clearWatch: (id: number) => {
      clearedWatchId = id;
    },
  },
};

Object.defineProperty(globalThis, 'navigator', {
  value: mockNavigator,
  configurable: true,
  writable: true,
});

let capturedState: any = null;
const stopWatch = startForegroundLocationTracking((s) => {
  capturedState = s;
});

assert.strictEqual(capturedState.status, 'requesting');
assert.strictEqual(isForegroundTrackingActive(), true);

// Trigger location update
mockWatchCallback({
  coords: {
    latitude: 13.0827,
    longitude: 80.2707,
    accuracy: 8,
    heading: 90,
    speed: 5.5,
  },
});

assert.strictEqual(capturedState.status, 'live_position');
assert.strictEqual(capturedState.accuracyMeters, 8);
assert.strictEqual(capturedState.coords.latitude, 13.0827);

// Stop tracking
stopWatch();
assert.strictEqual(clearedWatchId, 101, 'clearWatch must be invoked with watch ID');
assert.strictEqual(isForegroundTrackingActive(), false);
console.log('✓ Foreground GPS tracking cleanly starts, captures live fixes, and stops without background leakage.');

// Test 5.3: Geolocation failure modes and error handling
let errorState: any = null;
startForegroundLocationTracking((s) => {
  errorState = s;
});
mockErrorCallback({ code: 1, PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 });
assert.strictEqual(errorState.status, 'permission_denied');
assert(errorState.errorMessage?.includes('permission was denied'));

startForegroundLocationTracking((s) => {
  errorState = s;
});
mockErrorCallback({ code: 2, PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 });
assert.strictEqual(errorState.status, 'unavailable');

startForegroundLocationTracking((s) => {
  errorState = s;
});
mockErrorCallback({ code: 3, PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 });
assert.strictEqual(errorState.status, 'unavailable');
stopForegroundLocationTracking();
console.log('✓ GPS permission denied, unavailable, and timeout failure modes handle gracefully.');

console.log('\n=================================================================');
console.log('ALL NAVIGATION GUIDANCE & JOURNEY PROGRESS TESTS PASSED (M3.6) ✓');
console.log('=================================================================');
