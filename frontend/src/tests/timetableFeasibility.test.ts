import assert from 'node:assert';
import {
  composeMultiModalJourneys,
  KARNATAKA_EXPRESS_TIMETABLE,
  PLANNED_REGULATION_REGISTRY,
} from '../api/orchestrationEngine';
import {
  istToUtcInstant,
  utcToIstComponents,
  formatIstTime,
  formatIstDateTime,
  IST_OFFSET_MINUTES,
  isPastInstant,
  evaluateDepartureTiming,
  propagateDownstreamWindow,
  evaluateIntersegmentConnection,
} from '../utils/timezone';
import { TravelRequest } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING OPERATIONAL TIMETABLE RECONCILIATION & FEASIBILITY TEST SUITE (UI-01.2.3)');
console.log('=================================================================');

// Fixed evaluation instant for deterministic testing: 14-Nov-2026 08:34:50 IST
const AUDIT_NOW_INSTANT = '2026-11-14T03:04:50.000Z'; // 08:34:50 IST

// ----------------------------------------------------------------------------
// TEST 1: Karnataka Express Cannot Depart at 05:29 When Published is 19:20
// ----------------------------------------------------------------------------
console.log('\n--- Test 1: Real Train 12627 Departure Integrity (Fixed 19:20 IST, Never 05:29) ---');
const test1Req: TravelRequest = {
  origin: 'Udayapura',
  destination: 'Delhi',
  departureDate: '2026-11-15',
  preferredArrivalBefore: '20:00', // User asks for 20:00 arrival
  budgetMax: 10000,
  passengersCount: 1,
  weights: { cost: 0.1, duration: 0.1, comfort: 0.1, carbon: 0.7 },
  naturalLanguageQuery: 'Udayapura to Delhi greenest train',
  referenceNowInstant: AUDIT_NOW_INSTANT,
};

const test1Journeys = composeMultiModalJourneys(test1Req);
const karnatakaJourney = test1Journeys.find(
  (j) => j.segments.some((s) => s.vehicleNumber === '12627')
);
assert(karnatakaJourney, 'Karnataka Express journey must be produced');

const trainSeg = karnatakaJourney.segments.find((s) => s.vehicleNumber === '12627')!;
const trainDepIst = utcToIstComponents(trainSeg.departureTime);

console.log(`Reported Train 12627 Departure: ${trainDepIst.dateStr} at ${trainDepIst.timeStr} IST (${trainSeg.departureTime})`);
assert.strictEqual(
  trainDepIst.timeStr,
  '19:20',
  `Train 12627 departure must strictly match published timetable 19:20 IST, got ${trainDepIst.timeStr}`
);
assert.notStrictEqual(
  trainDepIst.timeStr,
  '05:29',
  'Train 12627 must NEVER depart at arbitrary backward-scheduled 05:29'
);
console.log('✓ Test 1 Passed: Train 12627 departs at published 19:20 IST; arbitrary 05:29 departure strictly eliminated.');

// ----------------------------------------------------------------------------
// TEST 2: Deadline Before Actual Train Arrival Produces Infeasible Result
// ----------------------------------------------------------------------------
console.log('\n--- Test 2: Infeasible Deadline Evaluation (Arrival After Deadline) ---');
// User departs Nov 15 and asks for arrival before 20:00 on Nov 15. Train arrives Day 3 (Nov 17 at 09:21).
assert.strictEqual(
  karnatakaJourney.isConnectionFeasible,
  false,
  'Journey arriving on Day 3 (Nov 17) must be flagged infeasible for same-day Nov 15 20:00 deadline'
);
assert(
  karnatakaJourney.connectionFeasibilityNotes && karnatakaJourney.connectionFeasibilityNotes.length > 0,
  'Infeasible journey must provide descriptive feasibility notes'
);
const deadlineExceededNote = karnatakaJourney.connectionFeasibilityNotes.find((n) =>
  n.includes('Arrival deadline missed') || n.includes('exceeding requested deadline')
);
assert(deadlineExceededNote, 'Feasibility notes must state that deadline was missed');
console.log(`✓ Test 2 Passed: Infeasible journey correctly flagged with note: "${deadlineExceededNote}"`);

// ----------------------------------------------------------------------------
// TEST 3: Deadline After Actual Arrival Permits the Service (Historical Fixture)
// ----------------------------------------------------------------------------
console.log('\n--- Test 3: Feasible Deadline Evaluation (Historical Test Fixture) ---');
// User departs Nov 13, so train arrives Nov 15 at 09:21 IST. Requested deadline is Nov 15 20:00 IST.
const test3Req: TravelRequest = {
  origin: 'Udayapura',
  destination: 'Delhi',
  departureDate: '2026-11-13', // Depart 2 days earlier
  preferredArrivalBefore: '2026-11-15T20:00', // Target arrival by 20:00 on Nov 15 (Day 3)
  budgetMax: 10000,
  passengersCount: 1,
  weights: { cost: 0.1, duration: 0.1, comfort: 0.1, carbon: 0.7 },
  naturalLanguageQuery: 'Udayapura to Delhi greenest train departing Nov 13',
  allowHistoricalFixtures: true, // Preserve historical test fixture
  referenceNowInstant: '2026-11-13T06:00:00.000Z', // Frozen time prior to Nov 13 departure
};

const test3Journeys = composeMultiModalJourneys(test3Req);
const karnatakaJourneyFeasible = test3Journeys.find(
  (j) => j.segments.some((s) => s.vehicleNumber === '12627')
);
assert(karnatakaJourneyFeasible, 'Karnataka Express journey for Nov 13 departure must exist');
const arrIstNov15 = utcToIstComponents(karnatakaJourneyFeasible.arrivalTime);

console.log(`Departure: ${utcToIstComponents(karnatakaJourneyFeasible.departureTime).dateStr} ${utcToIstComponents(karnatakaJourneyFeasible.departureTime).timeStr} IST`);
console.log(`Arrival: ${arrIstNov15.dateStr} ${arrIstNov15.timeStr} IST`);
assert.strictEqual(arrIstNov15.dateStr, '2026-11-15', 'Must arrive on Nov 15');
assert.strictEqual(
  karnatakaJourneyFeasible.isConnectionFeasible,
  true,
  'Journey arriving at 09:21 IST must be feasible for a 20:00 IST deadline on the same day'
);
console.log('✓ Test 3 Passed: Train arriving before requested deadline is fully feasible (historical fixture preserved).');

// ----------------------------------------------------------------------------
// TEST 4: Running Day Verification (Non-Running Day Rejection)
// ----------------------------------------------------------------------------
console.log('\n--- Test 4: Running Day Verification ---');
assert.strictEqual(
  KARNATAKA_EXPRESS_TIMETABLE.runningDays.length,
  7,
  'Karnataka Express 12627 must operate daily (all 7 days)'
);
for (let d = 0; d < 7; d++) {
  assert(
    KARNATAKA_EXPRESS_TIMETABLE.runningDays.includes(d),
    `Day ${d} must be included in running days`
  );
}
console.log('✓ Test 4 Passed: Running days verified daily across Mon-Sun.');

// ----------------------------------------------------------------------------
// TEST 5: Estimated Alternative Cannot Falsely Inherit Train 12627 Identity
// ----------------------------------------------------------------------------
console.log('\n--- Test 5: Isolation of Real Train Identity from Estimated Connections ---');
for (const j of test1Journeys) {
  if (j.id !== karnatakaJourney.id) {
    for (const seg of j.segments) {
      assert.notStrictEqual(
        seg.vehicleNumber,
        '12627',
        `Estimated archetype ${j.id} must not hijack real train number 12627`
      );
      assert.notStrictEqual(
        seg.vehicleName,
        'Karnataka Express',
        `Estimated archetype ${j.id} must not hijack real train name Karnataka Express`
      );
    }
  }
}
console.log('✓ Test 5 Passed: No estimated alternative falsely inherits Karnataka Express (12627) identity.');

// ----------------------------------------------------------------------------
// TEST 6: Timetable Source Disagreement Preserved in Provenance Notes
// ----------------------------------------------------------------------------
console.log('\n--- Test 6: Source Disagreement Preservation in Provenance ---');
const distProv = trainSeg.provenance!.attributes.distance;
const durProv = trainSeg.provenance!.attributes.duration;
const depProv = trainSeg.provenance!.attributes.departure;
const arrProv = trainSeg.provenance!.attributes.arrival;

assert(
  distProv.notes?.includes('2,406 km') && distProv.notes?.includes('2,395 km'),
  `Distance provenance must disclose both published tariff (2,406 km) and track survey (2,395 km), got: ${distProv.notes}`
);
assert(
  durProv.notes?.includes('2,260 min') && durProv.notes?.includes('2,350 min'),
  `Duration provenance must disclose published (2,260 min) and secondary slowdown (2,350 min), got: ${durProv.notes}`
);
assert(
  depProv.notes?.includes('19:20 IST'),
  `Departure provenance must declare published timetable departure 19:20 IST, got: ${depProv.notes}`
);
assert(
  arrProv.notes?.includes('09:00 IST') && arrProv.notes?.includes('10:30 IST'),
  `Arrival provenance must declare published 09:00 IST and secondary 10:30 IST, got: ${arrProv.notes}`
);
console.log('✓ Test 6 Passed: Multi-source discrepancy matrix transparently preserved in provenance attributes.');

// ----------------------------------------------------------------------------
// TEST 7: Timezone Conversions for Asia/Kolkata (Bengaluru and Delhi)
// ----------------------------------------------------------------------------
console.log('\n--- Test 7: Timezone Conversion Contract (Asia/Kolkata / UTC+05:30) ---');
const instant2000 = istToUtcInstant('2026-11-15', '20:00');
assert.strictEqual(
  instant2000.toISOString(),
  '2026-11-15T14:30:00.000Z',
  `20:00 IST on 2026-11-15 must convert to 2026-11-15T14:30:00.000Z, got ${instant2000.toISOString()}`
);

const istComp = utcToIstComponents('2026-11-15T14:30:00.000Z');
assert.strictEqual(istComp.dateStr, '2026-11-15');
assert.strictEqual(istComp.timeStr, '20:00');
assert.strictEqual(istComp.displayTime, '8:00 PM');
assert.strictEqual(istComp.isoWithOffset, '2026-11-15T20:00:00+05:30');
console.log('✓ Test 7 Passed: Timezone conversions for Asia/Kolkata (+05:30) verified across instant boundaries.');

// ----------------------------------------------------------------------------
// TEST 8: Mathematical Duration & Transfer Buffer Reconciliation
// ----------------------------------------------------------------------------
console.log('\n--- Test 8: Mathematical Duration & Transfer Buffer Reconciliation ---');
const seg1Dur = karnatakaJourney.segments[0].durationMinutes; // 45 min
const seg2Dur = karnatakaJourney.segments[1].durationMinutes; // 2260 min
const seg3Dur = karnatakaJourney.segments[2].durationMinutes; // 6 min
const wait1 = karnatakaJourney.segments[0].transferBufferMinutes!; // 20 min
const wait2 = karnatakaJourney.segments[1].transferBufferMinutes!; // 15 min

const expectedTravelTime = seg1Dur + seg2Dur + seg3Dur; // 2311 min
const expectedWaitTime = wait1 + wait2; // 35 min
const expectedTotalDuration = expectedTravelTime + expectedWaitTime; // 2346 min

assert.strictEqual(karnatakaJourney.travelDurationMinutes, expectedTravelTime);
assert.strictEqual(karnatakaJourney.waitingDurationMinutes, expectedWaitTime);
assert.strictEqual(karnatakaJourney.totalDurationMinutes, expectedTotalDuration);

const depMillis = new Date(karnatakaJourney.departureTime).getTime();
const arrMillis = new Date(karnatakaJourney.arrivalTime).getTime();
const diffMinutes = Math.round((arrMillis - depMillis) / 60000);
assert.strictEqual(diffMinutes, expectedTotalDuration);
console.log(`✓ Test 8 Passed: Duration arithmetic reconciled: ${seg1Dur}m + ${wait1}m + ${seg2Dur}m + ${wait2}m + ${seg3Dur}m = ${expectedTotalDuration}m.`);

// ----------------------------------------------------------------------------
// TEST 9: Pareto Optimizer Handling of Infeasible vs Feasible Journeys
// ----------------------------------------------------------------------------
console.log('\n--- Test 9: Pareto Optimizer Handling of Infeasible vs Feasible Journeys ---');
const topJourney = test1Journeys[0];
console.log(`Top recommended journey for same-day deadline: ${topJourney.title} (Category: ${topJourney.recommendationCategory})`);
assert.strictEqual(topJourney.isConnectionFeasible, true);
assert.notStrictEqual(topJourney.recommendationCategory, 'greenest');
assert.strictEqual(karnatakaJourney.isParetoOptimal, false);
console.log('✓ Test 9 Passed: Optimizer penalizes infeasible journeys and promotes feasible alternatives.');

// ----------------------------------------------------------------------------
// TEST 10: Immutability of Real Service Timetable Under Strict Deadlines
// ----------------------------------------------------------------------------
console.log('\n--- Test 10: Immutability of Real Service Timetable Under Strict Deadlines ---');
const deadlines = ['12:00', '16:00', '20:00', '23:59'];
for (const dl of deadlines) {
  const req: TravelRequest = {
    origin: 'Udayapura',
    destination: 'Delhi',
    departureDate: '2026-11-15',
    preferredArrivalBefore: dl,
    passengersCount: 1,
    weights: { cost: 0.25, duration: 0.25, comfort: 0.25, carbon: 0.25 },
    referenceNowInstant: AUDIT_NOW_INSTANT,
  };
  const journeys = composeMultiModalJourneys(req);
  const train = journeys.find((j) => j.segments.some((s) => s.vehicleNumber === '12627'));
  assert(train, `Train 12627 must exist for deadline ${dl}`);
  const trainSegDep = train.segments.find((s) => s.vehicleNumber === '12627')!;
  const depTime = utcToIstComponents(trainSegDep.departureTime).timeStr;
  assert.strictEqual(depTime, '19:20');
}
console.log('✓ Test 10 Passed: Train 12627 departure is strictly invariant at 19:20 IST across all deadlines; zero backward-shifting.');

// ----------------------------------------------------------------------------
// TEST 11: Official November 15 Railway Regulation Notice (SWR PR 1404 / NR PR 1568)
// ----------------------------------------------------------------------------
console.log('\n--- Test 11: Official November 15 Railway Regulation Notice Association ---');
assert(PLANNED_REGULATION_REGISTRY.length > 0, 'Planned regulation registry must contain active notices');
const regNotice = PLANNED_REGULATION_REGISTRY.find(
  (r) => r.trainNumber === '12627' && r.departureDate === '2026-11-15'
);
assert(regNotice, 'Notice for 12627 on 2026-11-15 must be registered');
assert.strictEqual(regNotice.regulationMinutes, 130, 'Regulation must be 130 min (2h 10m)');
assert(regNotice.affectedSection.includes('Daund'), 'Affected section must include Daund');
assert(regNotice.affectedSection.includes('Manmad'), 'Affected section must include Manmad');
assert(regNotice.sourceUrls.swr.includes('preview/1404'), 'SWR URL must link to PR 1404');
assert(regNotice.sourceUrls.nr.includes('preview/1568'), 'NR URL must link to PR 1568');

// Journey departing Nov 15 must expose this operational notice
assert(karnatakaJourney.operationalNotice, 'Journey for Nov 15 departure must have operationalNotice');
assert(
  karnatakaJourney.operationalNotice.headline.includes('PR No. 1404'),
  'Headline must mention PR No. 1404'
);
assert(
  karnatakaJourney.operationalNotice.details.includes('130 min'),
  'Notice details must disclose 130 min en-route regulation'
);
assert.strictEqual(
  karnatakaJourney.operationalNotice.sourceUrl,
  'https://swr.indianrailways.gov.in/documents/press-release/preview/1404'
);

// Segment 2 must reflect scheduleState
const leg2 = karnatakaJourney.segments[1];
assert(leg2.scheduleState, 'Leg 2 must possess structured scheduleState');
assert.strictEqual(leg2.scheduleState.scheduledDeparture, '19:20 IST');
assert.strictEqual(leg2.scheduleState.scheduledArrival, '10:30 IST (Day 3)');
assert(leg2.scheduleState.plannedRegulation, 'Leg 2 must reference plannedRegulation');
assert.strictEqual(leg2.scheduleState.liveRunningStatus, 'unavailable');
assert(
  leg2.scheduleState.estimatedArrival?.includes('Subject to operational delay'),
  'Estimated arrival must declare subject to operational delay, not guaranteed arrival delay'
);

// Verify that terminal delay is NOT automatically added as guaranteed
const expectedTimetableArrMillis = new Date(leg2.departureTime).getTime() + 2260 * 60000;
assert.strictEqual(
  new Date(leg2.arrivalTime).getTime(),
  expectedTimetableArrMillis,
  'Leg 2 arrival time must reflect published timetable, NOT timetable + 130m guaranteed delay'
);

// Provenance attributes must separate planned_regulation and live_status
const leg2Prov = leg2.provenance!.attributes;
assert(leg2Prov.plannedRegulation, 'Provenance must contain plannedRegulation attribute');
assert.strictEqual(leg2Prov.plannedRegulation.sourceType, 'deterministic_estimate');
assert(leg2Prov.plannedRegulation.notes?.includes('SWR Press Release No. 1404'));
assert(leg2Prov.liveStatus, 'Provenance must contain liveStatus attribute');
assert.strictEqual(leg2Prov.liveStatus.sourceType, 'unknown');
console.log('✓ Test 11 Passed: Official planned regulation notice verified with SWR PR 1404 / NR PR 1568 without guaranteed delay inflation.');

// ----------------------------------------------------------------------------
// TEST 12: Isolation of Regulation Notice (Zero Cross-Date / Cross-Train Contamination)
// ----------------------------------------------------------------------------
console.log('\n--- Test 12: Isolation of Regulation Notice from Other Dates and Trains ---');
// Departure on Nov 14 (day before)
const reqNov14: TravelRequest = {
  origin: 'Udayapura',
  destination: 'Delhi',
  departureDate: '2026-11-14',
  preferredArrivalBefore: '20:00',
  budgetMax: 10000,
  passengersCount: 1,
  weights: { cost: 0.25, duration: 0.25, comfort: 0.25, carbon: 0.25 },
  allowHistoricalFixtures: true,
  referenceNowInstant: '2026-11-14T00:00:00.000Z',
};
const journeysNov14 = composeMultiModalJourneys(reqNov14);
const karnatakaNov14 = journeysNov14.find((j) => j.segments.some((s) => s.vehicleNumber === '12627'))!;
assert.strictEqual(
  karnatakaNov14.operationalNotice,
  undefined,
  'Regulation notice for Nov 15 must NOT contaminate Nov 14 journey'
);
assert.strictEqual(
  karnatakaNov14.segments[1].scheduleState?.plannedRegulation,
  undefined,
  'ScheduleState plannedRegulation must NOT appear on Nov 14 departure'
);

// Departure on Nov 16 (day after)
const reqNov16: TravelRequest = {
  origin: 'Udayapura',
  destination: 'Delhi',
  departureDate: '2026-11-16',
  preferredArrivalBefore: '20:00',
  budgetMax: 10000,
  passengersCount: 1,
  weights: { cost: 0.25, duration: 0.25, comfort: 0.25, carbon: 0.25 },
  referenceNowInstant: AUDIT_NOW_INSTANT,
};
const journeysNov16 = composeMultiModalJourneys(reqNov16);
const karnatakaNov16 = journeysNov16.find((j) => j.segments.some((s) => s.vehicleNumber === '12627'))!;
assert.strictEqual(
  karnatakaNov16.operationalNotice,
  undefined,
  'Regulation notice for Nov 15 must NOT contaminate Nov 16 journey'
);

// Other non-12627 journeys on Nov 15
for (const j of test1Journeys) {
  if (j.id !== karnatakaJourney.id) {
    assert.strictEqual(
      j.operationalNotice,
      undefined,
      `Non-12627 journey ${j.id} must NOT have regulation notice`
    );
  }
}
console.log('✓ Test 12 Passed: Regulation notice cleanly isolated to train 12627 on 2026-11-15 with zero contamination.');

// ----------------------------------------------------------------------------
// TEST 13: Past Departure Detection & Removal of Actionable Past Recommendations
// ----------------------------------------------------------------------------
console.log('\n--- Test 13: Past Departure Timing & Actionable Recommendation Validation ---');
// 1. Departure already in the past (Nov 13 at 18:15 IST evaluated against Nov 14 at 08:34 IST)
const depPastInstant = istToUtcInstant('2026-11-13', '18:15');
const evalPast = evaluateDepartureTiming(depPastInstant, AUDIT_NOW_INSTANT);
assert.strictEqual(evalPast.isPast, true, 'Nov 13 18:15 IST must be recognized as past');
assert.strictEqual(evalPast.isFuture, false);

// 2. Departure later today (Nov 14 at 20:00 IST evaluated against Nov 14 at 08:34 IST)
const depTodayInstant = istToUtcInstant('2026-11-14', '20:00');
const evalToday = evaluateDepartureTiming(depTodayInstant, AUDIT_NOW_INSTANT);
assert.strictEqual(evalToday.isPast, false, 'Nov 14 20:00 IST must not be past');
assert.strictEqual(evalToday.isToday, true, 'Nov 14 20:00 IST must be recognized as today');
assert.strictEqual(evalToday.isFuture, true);

// 3. Departure tomorrow (Nov 15 at 18:15 IST evaluated against Nov 14 at 08:34 IST)
const depTomorrowInstant = istToUtcInstant('2026-11-15', '18:15');
const evalTomorrow = evaluateDepartureTiming(depTomorrowInstant, AUDIT_NOW_INSTANT);
assert.strictEqual(evalTomorrow.isPast, false);
assert.strictEqual(evalTomorrow.isTomorrow, true, 'Nov 15 18:15 IST must be recognized as tomorrow');
assert.strictEqual(evalTomorrow.isFuture, true);

// 4. Infeasible Nov 15 train recommendation notes must NOT recommend past Nov 13 departure
const pastAdviceNote = karnatakaJourney.connectionFeasibilityNotes?.find((n) =>
  n.includes('must be scheduled 2 days earlier')
);
assert.strictEqual(
  pastAdviceNote,
  undefined,
  'Engine must NEVER advise user to depart on a past date (Nov 13)'
);

const pastDetectedNote = karnatakaJourney.connectionFeasibilityNotes?.find((n) =>
  n.includes('has already passed relative to current time and is not an actionable option')
);
assert(
  pastDetectedNote,
  `Engine must explicitly declare that an earlier train has passed, got: ${JSON.stringify(karnatakaJourney.connectionFeasibilityNotes)}`
);

const actionableFutureNote = karnatakaJourney.connectionFeasibilityNotes?.find((n) =>
  n.includes('Actionable future recommendation: Select the Fastest flight archetype')
);
assert(actionableFutureNote, 'Engine must promote actionable future alternative');
console.log('✓ Test 13 Passed: Past departures correctly flagged; past date recommendations eliminated in favor of actionable future alternatives.');

// ----------------------------------------------------------------------------
// TEST 14: Expired Alternative Filtered Out Before Pareto Ranking
// ----------------------------------------------------------------------------
console.log('\n--- Test 14: Expired Alternative Removed Before Pareto Ranking ---');
// Query departing in the past without allowHistoricalFixtures
const reqExpired: TravelRequest = {
  origin: 'Udayapura',
  destination: 'Delhi',
  departureDate: '2026-11-13',
  preferredArrivalBefore: '20:00',
  budgetMax: 10000,
  passengersCount: 1,
  weights: { cost: 0.25, duration: 0.25, comfort: 0.25, carbon: 0.25 },
  referenceNowInstant: AUDIT_NOW_INSTANT, // Now is Nov 14, so Nov 13 is expired
  allowHistoricalFixtures: false, // Default user behavior
};
const journeysExpired = composeMultiModalJourneys(reqExpired);
assert.strictEqual(
  journeysExpired.length,
  0,
  'Expired departures must be filtered out before Pareto ranking when historical fixtures not permitted'
);

// When allowHistoricalFixtures: true, journeys are preserved
const reqHistorical: TravelRequest = {
  ...reqExpired,
  allowHistoricalFixtures: true,
};
const journeysHistorical = composeMultiModalJourneys(reqHistorical);
assert(journeysHistorical.length > 0, 'Historical fixtures must remain accessible when explicitly requested');
assert(
  journeysHistorical[0].isExpiredDeparture,
  'Historical journey must be tagged with isExpiredDeparture: true'
);
console.log('✓ Test 14 Passed: Expired departures filtered from ranking by default while preserved for historical audits.');

// ----------------------------------------------------------------------------
// TEST 15: Timetable Conflict Discrepancy & Uncertainty Window Verification
// ----------------------------------------------------------------------------
console.log('\n--- Test 15: Timetable Conflict & Uncertainty Range Verification ---');
assert.strictEqual(
  KARNATAKA_EXPRESS_TIMETABLE.publishedArrivalIST,
  '10:30',
  'Official Indian Railways NTES schedule arrival must be 10:30 IST'
);
assert.strictEqual(
  KARNATAKA_EXPRESS_TIMETABLE.secondaryArrivalIST,
  '09:00',
  'Secondary published timetable arrival must be 09:00 IST'
);
assert.strictEqual(
  KARNATAKA_EXPRESS_TIMETABLE.arrivalWindowIST.earliest,
  '09:00',
  'Earliest arrival in window must be 09:00'
);
assert.strictEqual(
  KARNATAKA_EXPRESS_TIMETABLE.arrivalWindowIST.latest,
  '10:30',
  'Latest arrival in window must be 10:30'
);
assert.strictEqual(
  KARNATAKA_EXPRESS_TIMETABLE.tariffDistanceKm,
  2406,
  'Chargeable tariff distance must be 2,406 km'
);
assert.strictEqual(
  KARNATAKA_EXPRESS_TIMETABLE.engineeringTrackDistanceKm,
  2395,
  'Track survey distance must be 2,395 km'
);
assert(
  KARNATAKA_EXPRESS_TIMETABLE.sourceAuthority.officialListing.sourceUrl.includes('enquiry.indianrailways.gov.in'),
  'Official listing URL must be enquiry.indianrailways.gov.in'
);
assert(
  KARNATAKA_EXPRESS_TIMETABLE.sourceAuthority.secondaryListing.sourceUrl.includes('indiarailinfo.com'),
  'Secondary listing URL must be indiarailinfo.com'
);
console.log('✓ Test 15 Passed: Timetable conflicts, uncertainty window (09:00 - 10:30), and exact source citations verified.');

// ============================================================================
// UI REFINEMENT 01.2.4: ARRIVAL UNCERTAINTY PROPAGATION & CONNECTION FEASIBILITY
// ============================================================================
console.log('\n=================================================================');
console.log('RUNNING ARRIVAL UNCERTAINTY PROPAGATION & CONNECTION TESTS (UI-01.2.4)');
console.log('=================================================================');

// Base query for UI 01.2.4 tests: Nov 15 departure from Udayapura to Delhi
const testPropReq: TravelRequest = {
  origin: 'Udayapura',
  destination: 'Delhi',
  departureDate: '2026-11-15',
  preferredArrivalBefore: '20:00',
  budgetMax: 10000,
  passengersCount: 1,
  weights: { cost: 0.1, duration: 0.1, comfort: 0.1, carbon: 0.7 },
  naturalLanguageQuery: 'Udayapura to Delhi rail connection propagation',
  referenceNowInstant: AUDIT_NOW_INSTANT,
};

const journeysProp = composeMultiModalJourneys(testPropReq);
const railJourney = journeysProp.find((j) => j.segments.some((s) => s.vehicleNumber === '12627'));
assert(railJourney, 'Rail journey with Karnataka Express must be produced');

const leg1Shuttle = railJourney.segments[0];
const leg2Train = railJourney.segments[1];
const leg3Metro = railJourney.segments[2];

// ----------------------------------------------------------------------------
// TEST 16: Arrival Uncertainty Window of 09:00–10:30 IST Propagates Downstream
// ----------------------------------------------------------------------------
console.log('\n--- Test 16: Arrival Uncertainty Window (09:00–10:30 IST) Propagates Downstream ---');
assert(leg2Train.scheduleState?.arrivalWindow, 'Train leg must have arrivalWindow defined');
assert.strictEqual(
  leg2Train.scheduleState.arrivalWindow.earliestIST,
  '09:00',
  'Train arrival window earliest must be 09:00 IST'
);
assert.strictEqual(
  leg2Train.scheduleState.arrivalWindow.latestIST,
  '10:30',
  'Train arrival window latest must be 10:30 IST'
);

// Verify propagation helper produces correct window with and without waiting time
// Baseline: Zero additional wait produces 09:15 departure and 09:21 arrival
const testZeroWait = propagateDownstreamWindow(
  {
    earliestInstantUTC: leg2Train.scheduleState.arrivalWindow.earliestInstantUTC!,
    latestInstantUTC: leg2Train.scheduleState.arrivalWindow.latestInstantUTC!,
  },
  15, // 15 min buffer at NDLS
  6,  // 6 min metro duration to Rajiv Chowk
  { min: 0, max: 0 }
);
assert.strictEqual(testZeroWait.departureWindow.earliestIST, '09:15');
assert.strictEqual(testZeroWait.departureWindow.latestIST, '10:45');
assert.strictEqual(testZeroWait.arrivalWindow.earliestIST, '09:21');
assert.strictEqual(testZeroWait.arrivalWindow.latestIST, '10:51');

// With 0–5 min waiting time: Earliest departure 09:15, latest departure 10:50; earliest arrival 09:21, latest arrival 10:56
const testFiveMinWait = propagateDownstreamWindow(
  {
    earliestInstantUTC: leg2Train.scheduleState.arrivalWindow.earliestInstantUTC!,
    latestInstantUTC: leg2Train.scheduleState.arrivalWindow.latestInstantUTC!,
  },
  15, // 15 min buffer at NDLS
  6,  // 6 min metro duration to Rajiv Chowk
  { min: 0, max: 5 }
);
assert.strictEqual(testFiveMinWait.passengerReadinessWindow.earliestIST, '09:15');
assert.strictEqual(testFiveMinWait.passengerReadinessWindow.latestIST, '10:45');
assert.strictEqual(testFiveMinWait.departureWindow.earliestIST, '09:15');
assert.strictEqual(testFiveMinWait.departureWindow.latestIST, '10:50');
assert.strictEqual(testFiveMinWait.arrivalWindow.earliestIST, '09:21');
assert.strictEqual(testFiveMinWait.arrivalWindow.latestIST, '10:56');
console.log('✓ Test 16 Passed: Arrival uncertainty window (09:00–10:30 IST) propagates through transfer buffer (15m), waiting time (0–5m), and metro ride (6m) to yield 09:21–10:56 IST.');

// ----------------------------------------------------------------------------
// TEST 17: Estimated Onward Connection Departure Is Represented as 09:15–10:50 IST, Not Fixed 09:15
// ----------------------------------------------------------------------------
console.log('\n--- Test 17: Estimated Onward Connection Departure Window (09:15–10:50 IST) ---');
assert(leg3Metro.scheduleState?.departureWindow, 'Metro leg must have departureWindow defined');
assert.strictEqual(
  leg3Metro.scheduleState.departureWindow.earliestIST,
  '09:15',
  'Metro earliest departure bound must be 09:15 IST'
);
assert.strictEqual(
  leg3Metro.scheduleState.departureWindow.latestIST,
  '10:50',
  'Metro latest departure bound must be 10:50 IST (readiness 10:45 + 5m wait)'
);
assert(
  leg3Metro.scheduleState.scheduledDeparture.includes('09:15 – 10:50 IST (Estimated)'),
  `Scheduled departure must state estimated window, got: ${leg3Metro.scheduleState.scheduledDeparture}`
);
assert.notStrictEqual(
  leg3Metro.scheduleState.scheduledDeparture,
  '09:15 IST',
  'Metro departure must NEVER be represented as fixed guaranteed 09:15 IST'
);
console.log('✓ Test 17 Passed: Onward connection departure correctly represented as 09:15–10:50 IST window tracking passenger readiness and 0–5m wait.');

// ----------------------------------------------------------------------------
// TEST 18: Final Arrival at Rajiv Chowk Is Represented as 09:21–10:56 IST
// ----------------------------------------------------------------------------
console.log('\n--- Test 18: Final Arrival Window at Rajiv Chowk (09:21–10:56 IST) ---');
assert(railJourney.arrivalWindow, 'Journey must have arrivalWindow defined');
assert.strictEqual(
  railJourney.arrivalWindow.earliestIST,
  '09:21',
  'Final arrival earliest bound must be 09:21 IST'
);
assert.strictEqual(
  railJourney.arrivalWindow.latestIST,
  '10:56',
  'Final arrival latest bound must be 10:56 IST'
);
assert.strictEqual(
  railJourney.arrivalWindowIST,
  '09:21 – 10:56 IST',
  'Journey arrivalWindowIST must be "09:21 – 10:56 IST"'
);
assert.strictEqual(
  railJourney.isArrivalUncertain,
  true,
  'Journey must be tagged with isArrivalUncertain: true'
);
assert(leg3Metro.scheduleState?.arrivalWindow, 'Metro leg must have arrivalWindow defined');
assert.strictEqual(
  leg3Metro.scheduleState.arrivalWindow.earliestIST,
  '09:21',
  'Metro leg arrival earliest bound must be 09:21 IST'
);
assert.strictEqual(
  leg3Metro.scheduleState.arrivalWindow.latestIST,
  '10:56',
  'Metro leg arrival latest bound must be 10:56 IST'
);
console.log('✓ Test 18 Passed: Destination arrival accurately represented as 09:21–10:56 IST range across journey and segment metadata.');

// ----------------------------------------------------------------------------
// TEST 19: Transfer Buffer Is Applied Exactly Once Per Transfer
// ----------------------------------------------------------------------------
console.log('\n--- Test 19: Transfer Buffer Applied Exactly Once Per Transfer ---');
// Transfer 1: Feeder to Rail at SBC
const sbcBufferMinutes = (new Date(leg2Train.departureTime).getTime() - new Date(leg1Shuttle.arrivalTime).getTime()) / 60000;
assert.strictEqual(sbcBufferMinutes, 20, 'Transfer buffer at SBC must be exactly 20 minutes');

// Transfer 2: Rail to Metro at NDLS
// Readiness is train arrival + 15m transfer buffer
// Earliest: 09:00 train arr + 15m buffer = 09:15 passenger readiness
// Latest: 10:30 train arr + 15m buffer = 10:45 passenger readiness
assert.strictEqual(leg2Train.scheduleState?.passengerReadinessWindowIST, '09:15 – 10:45 IST');

// Metro departure window includes 0–5m platform wait
assert.strictEqual(leg3Metro.scheduleState?.departureWindow?.earliestIST, '09:15');
assert.strictEqual(leg3Metro.scheduleState?.departureWindow?.latestIST, '10:50');

// Metro travel duration: exactly 6 minutes from departure to arrival
const metroDurationEarliest = (new Date(leg3Metro.scheduleState!.arrivalWindow!.earliestInstantUTC!).getTime() - new Date(leg3Metro.scheduleState!.departureWindow!.earliestInstantUTC!).getTime()) / 60000;
const metroDurationLatest = (new Date(leg3Metro.scheduleState!.arrivalWindow!.latestInstantUTC!).getTime() - new Date(leg3Metro.scheduleState!.departureWindow!.latestInstantUTC!).getTime()) / 60000;
assert.strictEqual(metroDurationEarliest, 6, 'Metro travel duration must be exactly 6 minutes');
assert.strictEqual(metroDurationLatest, 6, 'Metro travel duration must be exactly 6 minutes');
console.log('✓ Test 19 Passed: Transfer buffer applied exactly once per transfer (20m at SBC, 15m at NDLS; no double-buffer).');

// ----------------------------------------------------------------------------
// TEST 20: Infeasible Connection Evaluation: Fixed 09:15 Connection Rejected for 10:30 Arrival Bound
// ----------------------------------------------------------------------------
console.log('\n--- Test 20: Infeasible Connection Rejected When Incoming Arrival Bound Is 10:30 ---');
// Train arrival window: 09:00 - 10:30 IST on 2026-11-17. Transfer buffer: 15 min.
// Passenger readiness latest bound: 10:45 IST.
// Hypothetical onward fixed scheduled departure: 09:15 IST (03:45 UTC).
const hypotheticalFixedDepUTC = istToUtcInstant('2026-11-17', '09:15');
const infeasibleEval = evaluateIntersegmentConnection(
  {
    earliestInstantUTC: leg2Train.scheduleState!.arrivalWindow!.earliestInstantUTC!,
    latestInstantUTC: leg2Train.scheduleState!.arrivalWindow!.latestInstantUTC!,
  },
  {
    connectionType: 'scheduled',
    scheduledDepartureInstantUTC: hypotheticalFixedDepUTC,
    scheduledDepartureIST: '09:15',
    isScheduleVerified: true,
  },
  15 // 15m transfer buffer
);

assert.strictEqual(
  infeasibleEval.isFeasible,
  false,
  'Fixed 09:15 connection must be rejected as infeasible when train may arrive up to 10:30'
);
assert.strictEqual(
  infeasibleEval.status,
  'infeasible',
  'Evaluation status must be "infeasible"'
);
assert.strictEqual(
  infeasibleEval.bufferDeficitMinutes,
  90,
  `Buffer deficit must be exactly 90 minutes (10:45 readiness vs 09:15 departure), got ${infeasibleEval.bufferDeficitMinutes}`
);
assert(
  infeasibleEval.reason.includes('deficit: 90m'),
  `Reason must explain 90m deficit, got: "${infeasibleEval.reason}"`
);
console.log(`✓ Test 20 Passed: Fixed 09:15 connection authoritatively rejected with 90 min deficit: "${infeasibleEval.reason}".`);

// ----------------------------------------------------------------------------
// TEST 21: Urban Transit Designated as Frequency-Based Estimate
// ----------------------------------------------------------------------------
console.log('\n--- Test 21: Urban Transit Designated as Frequency-Based Estimate ---');
assert.strictEqual(
  leg3Metro.scheduleState?.connectionType,
  'frequency_based_estimate',
  'Delhi Metro must be designated as frequency_based_estimate'
);
assert.strictEqual(
  leg3Metro.scheduleState?.connectionStatus,
  'feasible',
  'Frequency-based connection tracking passenger readiness must be feasible'
);
assert(
  leg3Metro.scheduleState?.connectionNotes?.includes('High-frequency urban transit'),
  'Metro connectionNotes must document high-frequency transit'
);

const freqEval = evaluateIntersegmentConnection(
  {
    earliestInstantUTC: leg2Train.scheduleState!.arrivalWindow!.earliestInstantUTC!,
    latestInstantUTC: leg2Train.scheduleState!.arrivalWindow!.latestInstantUTC!,
  },
  {
    connectionType: 'frequency_based_estimate',
  },
  15
);
assert.strictEqual(freqEval.isFeasible, true);
assert.strictEqual(freqEval.connectionType, 'frequency_based_estimate');
assert(freqEval.reason.includes('tracks passenger readiness'));
console.log('✓ Test 21 Passed: Urban transit correctly designated as frequency-based estimate without asserting unverified fixed departure.');

// ----------------------------------------------------------------------------
// TEST 22: Headway Assumption (~3–5 min) Is Explicitly Documented
// ----------------------------------------------------------------------------
console.log('\n--- Test 22: Headway Assumption (~3–5 min) Explicitly Documented ---');
assert(
  leg3Metro.scheduleState?.connectionNotes?.includes('3–5 min headway') ||
  leg3Metro.scheduleState?.connectionNotes?.includes('~3–5 min headway'),
  `Metro connection notes must state 3–5 min headway, got: ${leg3Metro.scheduleState?.connectionNotes}`
);
assert(
  leg3Metro.scheduleState?.liveRunningStatusMessage?.includes('3–5 min headway') ||
  leg3Metro.scheduleState?.liveRunningStatusMessage?.includes('~3–5 min headway'),
  `Metro live running message must state headway assumption, got: ${leg3Metro.scheduleState?.liveRunningStatusMessage}`
);
assert(
  leg3Metro.notes?.includes('~3–5m headway') || leg3Metro.notes?.includes('3–5 min headway'),
  `Metro segment notes must document headway assumption, got: ${leg3Metro.notes}`
);
console.log('✓ Test 22 Passed: Headway assumption (~3–5 min) explicitly documented across notes and schedule state.');

// ----------------------------------------------------------------------------
// TEST 23: Operational Regulation Preserved Without Double-Counting
// ----------------------------------------------------------------------------
console.log('\n--- Test 23: Planned Operational Regulation Preserved Without Double-Counting ---');
const nov15Regulation = PLANNED_REGULATION_REGISTRY.find(
  (r) => r.trainNumber === '12627' && r.departureDate === '2026-11-15'
);
assert(nov15Regulation, 'SWR PR 1404 regulation record must be present for Nov 15 departure');
assert.strictEqual(nov15Regulation.regulationMinutes, 130);
assert(
  nov15Regulation.affectedSection.includes('Daund') && nov15Regulation.affectedSection.includes('Manmad'),
  'Affected section must include Daund and Manmad'
);

// Regulation banner is populated
assert(railJourney.operationalNotice, 'Journey must present operationalNotice banner');
assert.strictEqual(railJourney.operationalNotice.plannedRegulation?.regulationMinutes, 130);

// Regulation is NOT double-counted in timetable arrival window:
// Earliest remains 09:00, latest remains 10:30 (NOT shifted to 11:10 - 12:40)
assert.strictEqual(
  leg2Train.scheduleState?.arrivalWindow?.earliestIST,
  '09:00',
  'Train arrival window earliest must remain 09:00 (regulation not double-counted into baseline timetable)'
);
assert.strictEqual(
  leg2Train.scheduleState?.arrivalWindow?.latestIST,
  '10:30',
  'Train arrival window latest must remain 10:30 (regulation not double-counted into baseline timetable)'
);
assert(
  leg2Train.scheduleState?.estimatedArrival?.includes('en-route regulation 130m'),
  'Estimated arrival note must transparently describe en-route regulation without asserting terminal delay'
);
console.log('✓ Test 23 Passed: SWR PR No. 1404 operational regulation preserved; double-counting strictly avoided.');

// ----------------------------------------------------------------------------
// TEST 24: UI Component Consistency (Windows Match Across Segments and Journey)
// ----------------------------------------------------------------------------
console.log('\n--- Test 24: UI Consistency Across Journey and Segment Windows ---');
assert.strictEqual(leg2Train.scheduleState?.scheduledDeparture, '19:20 IST');
assert.strictEqual(leg2Train.scheduleState?.arrivalWindow?.earliestIST, '09:00');
assert.strictEqual(leg2Train.scheduleState?.arrivalWindow?.latestIST, '10:30');
assert.strictEqual(leg2Train.scheduleState?.passengerReadinessWindowIST, '09:15 – 10:45 IST');

assert.strictEqual(leg3Metro.scheduleState?.departureWindow?.earliestIST, '09:15');
assert.strictEqual(leg3Metro.scheduleState?.departureWindow?.latestIST, '10:50');
assert.strictEqual(leg3Metro.scheduleState?.arrivalWindow?.earliestIST, '09:21');
assert.strictEqual(leg3Metro.scheduleState?.arrivalWindow?.latestIST, '10:56');

assert.strictEqual(railJourney.arrivalWindow?.earliestIST, '09:21');
assert.strictEqual(railJourney.arrivalWindow?.latestIST, '10:56');
assert.strictEqual(railJourney.arrivalWindowIST, '09:21 – 10:56 IST');
console.log('✓ Test 24 Passed: Complete consistency across train departure (19:20), arrival window (09:00-10:30), readiness (09:15-10:45), metro departure (09:15-10:50), and final arrival (09:21-10:56).');

// ----------------------------------------------------------------------------
// TEST 25: Strict UTC / IST Arithmetic & Timezone Round-Trip Invariance
// ----------------------------------------------------------------------------
console.log('\n--- Test 25: Strict UTC / IST Arithmetic & Timezone Invariance ---');
// Verify propagation spanning midnight
const midnightDep = istToUtcInstant('2026-11-15', '23:45'); // 18:15 UTC
const midnightWindow = propagateDownstreamWindow(
  {
    earliestInstantUTC: midnightDep,
    latestInstantUTC: new Date(midnightDep.getTime() + 60 * 60000), // 00:45 IST (+1 day)
  },
  30, // 30 min buffer -> earliest dep 00:15 IST, latest dep 01:15 IST
  45, // 45 min onward -> earliest arr 01:00 IST, latest arr 02:00 IST
  { min: 0, max: 0 }
);

assert.strictEqual(midnightWindow.departureWindow.earliestIST, '00:15');
assert.strictEqual(midnightWindow.departureWindow.latestIST, '01:15');
assert.strictEqual(midnightWindow.departureWindow.dateStr, '2026-11-16');
assert.strictEqual(midnightWindow.arrivalWindow.earliestIST, '01:00');
assert.strictEqual(midnightWindow.arrivalWindow.latestIST, '02:00');
assert.strictEqual(midnightWindow.arrivalWindow.dateStr, '2026-11-16');
console.log('✓ Test 25 Passed: Downstream propagation across date boundaries maintains exact UTC and IST components without timezone skew.');

// ============================================================================
// UI REFINEMENT 01.2.4.1: FREQUENCY-BASED WAITING-TIME PROPAGATION SUITE
// ============================================================================
console.log('\n=================================================================');
console.log('RUNNING FREQUENCY-BASED WAITING-TIME PROPAGATION TESTS (UI-01.2.4.1)');
console.log('=================================================================');

// ----------------------------------------------------------------------------
// TEST 26: Zero Additional Wait Produces Existing Earliest Arrival (09:21 IST)
// ----------------------------------------------------------------------------
console.log('\n--- Test 26: Zero Additional Wait Invariant (09:21 IST Earliest Arrival) ---');
const zeroWaitCalc = propagateDownstreamWindow(
  {
    earliestInstantUTC: leg2Train.scheduleState!.arrivalWindow!.earliestInstantUTC!,
    latestInstantUTC: leg2Train.scheduleState!.arrivalWindow!.latestInstantUTC!,
  },
  15,
  6,
  { min: 0, max: 0 }
);
assert.strictEqual(zeroWaitCalc.arrivalWindow.earliestIST, '09:21', 'Zero wait must yield 09:21 earliest arrival');
assert.strictEqual(railJourney.arrivalWindow?.earliestIST, '09:21', 'Journey earliest arrival must remain 09:21');
console.log('✓ Test 26 Passed: Zero additional wait strictly produces the existing earliest arrival of 09:21 IST.');

// ----------------------------------------------------------------------------
// TEST 27: Five-Minute Additional Wait Produces Latest Arrival of 10:56 IST
// ----------------------------------------------------------------------------
console.log('\n--- Test 27: Five-Minute Additional Wait Invariant (10:56 IST Latest Arrival) ---');
const fiveWaitCalc = propagateDownstreamWindow(
  {
    earliestInstantUTC: leg2Train.scheduleState!.arrivalWindow!.earliestInstantUTC!,
    latestInstantUTC: leg2Train.scheduleState!.arrivalWindow!.latestInstantUTC!,
  },
  15,
  6,
  { min: 0, max: 5 }
);
assert.strictEqual(fiveWaitCalc.arrivalWindow.latestIST, '10:56', '5m wait must yield 10:56 latest arrival');
assert.strictEqual(railJourney.arrivalWindow?.latestIST, '10:56', 'Journey latest arrival must be 10:56');
console.log('✓ Test 27 Passed: Five-minute additional wait strictly produces a latest arrival of 10:56 IST.');

// ----------------------------------------------------------------------------
// TEST 28: Waiting Time Is Never Applied Twice
// ----------------------------------------------------------------------------
console.log('\n--- Test 28: Waiting Time Idempotency (Never Applied Twice) ---');
const depLatestMs = new Date(leg3Metro.scheduleState!.departureWindow!.latestInstantUTC!).getTime();
const arrLatestMs = new Date(leg3Metro.scheduleState!.arrivalWindow!.latestInstantUTC!).getTime();
const rideDurationMin = Math.round((arrLatestMs - depLatestMs) / 60000);
assert.strictEqual(rideDurationMin, 6, 'Difference between metro departure and arrival must be exactly 6 minutes (waiting time not reapplied)');
assert.notStrictEqual(rideDurationMin, 11, 'Waiting time must NEVER be double-applied into ride duration');
console.log('✓ Test 28 Passed: Waiting time is applied to platform departure bound only, never double-counted into in-vehicle duration.');

// ----------------------------------------------------------------------------
// TEST 29: Clear Distinction Between Three Time Values (Transfer vs Wait vs Ride)
// ----------------------------------------------------------------------------
console.log('\n--- Test 29: Distinction Between Three Time Values (Transfer, Wait, Ride) ---');
assert.strictEqual(leg3Metro.scheduleState?.transferBufferMinutes, 15, 'Transfer buffer must be 15 min');
assert.deepStrictEqual(leg3Metro.scheduleState?.waitingMinutesRange, { min: 0, max: 5 }, 'Waiting range must be 0–5 min');
assert.strictEqual(leg3Metro.scheduleState?.rideDurationMinutes, 6, 'Ride duration must be 6 min');
assert.strictEqual(leg3Metro.scheduleState?.passengerReadinessWindowIST, '09:15 – 10:45 IST', 'Readiness window must be 09:15–10:45');
console.log('✓ Test 29 Passed: Clear distinction preserved between transfer buffer (15m), platform wait (0–5m), and metro ride (6m).');

// ----------------------------------------------------------------------------
// TEST 30: Frequency Assumption Labeled as Deterministic Estimate
// ----------------------------------------------------------------------------
console.log('\n--- Test 30: Frequency Assumption Provenance Labeling ---');
assert.strictEqual(
  leg3Metro.provenance?.attributes?.departure?.sourceType,
  'deterministic_estimate',
  'Metro departure must be labeled deterministic_estimate'
);
assert.strictEqual(
  leg3Metro.provenance?.attributes?.departure?.isEstimate,
  true,
  'Metro departure isEstimate must be true'
);
assert.notStrictEqual(
  leg3Metro.provenance?.sourceType,
  'provider_live',
  'Frequency-based metro must NEVER claim provider_live schedule'
);
assert.strictEqual(
  leg3Metro.scheduleState?.connectionType,
  'frequency_based_estimate',
  'connectionType must be frequency_based_estimate'
);
console.log('✓ Test 30 Passed: Frequency assumption correctly labeled as deterministic estimate, not provider-live schedule.');

console.log('\n=================================================================');
console.log('ALL 30 OPERATIONAL TIMETABLE & UNCERTAINTY PROPAGATION TESTS PASSED! ✓');
console.log('=================================================================');
