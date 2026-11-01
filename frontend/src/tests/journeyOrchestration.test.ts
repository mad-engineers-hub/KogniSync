import assert from 'node:assert';
import { composeMultiModalJourneys } from '../api/orchestrationEngine';
import { validateJourneyAgainstRequest } from '../api/mockData';
import { TravelRequest } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING COMPREHENSIVE REQUEST-AWARE MULTI-MODAL TEST SUITE');
console.log('=================================================================');

// ============================================================================
// TEST 1: Chennai -> Udupi (before 8 PM, budget ₹5000, speed preference)
// ============================================================================
console.log('\n--- Test 1: Route Chennai -> Udupi (Speed Preference, Budget ₹5000) ---');
const udupiReq: TravelRequest = {
  origin: 'Chennai',
  destination: 'Udupi',
  departureDate: '2026-11-02',
  preferredArrivalBefore: '20:00',
  budgetMax: 5000,
  passengersCount: 1,
  weights: { cost: 0.15, duration: 0.55, comfort: 0.2, carbon: 0.1 },
  naturalLanguageQuery: 'I need to reach Udupi from Chennai tomorrow before 8 PM. My budget is ₹5000 and I prefer speed.',
};

const udupiJourneys = composeMultiModalJourneys(udupiReq);
assert(udupiJourneys.length > 0, 'Must generate journeys for Chennai -> Udupi');
for (const j of udupiJourneys) {
  assert(j.segments.length >= 3, `Must have >= 3 segments, found ${j.segments.length}`);
  assert.strictEqual(j.origin.city.toLowerCase().includes('chennai'), true, 'Origin must be Chennai');
  assert.strictEqual(j.destination.city.toLowerCase().includes('udupi'), true, 'Destination must be Udupi');
  assert.strictEqual(j.segments[0].origin.city.toLowerCase().includes('chennai'), true, 'First leg starts in Chennai');
  assert.strictEqual(j.segments[j.segments.length - 1].destination.city.toLowerCase().includes('udupi'), true, 'Last leg ends in Udupi');
  assert(j.totalPrice <= 5000, `Journey ${j.id} price ₹${j.totalPrice} exceeds budget ₹5000`);
}
// Speed preference ranking: Fastest should rank #1
assert.strictEqual(udupiJourneys[0].recommendationCategory, 'fastest', 'Fastest journey must rank #1 for speed preference');
console.log(`✓ Chennai -> Udupi generated ${udupiJourneys.length} complete multi-modal journeys.`);
console.log(`✓ Top ranked journey: ${udupiJourneys[0].title} (Score: ${udupiJourneys[0].aiExplanation.score})`);

// ============================================================================
// TEST 2: Udayapalya -> Chennai (Locality to Intercity Metro)
// ============================================================================
console.log('\n--- Test 2: Route Udayapalya -> Chennai (Door-to-Door Locality) ---');
const udayapalyaReq: TravelRequest = {
  origin: 'Udayapalya',
  destination: 'Chennai',
  departureDate: '2026-10-30',
  preferredArrivalBefore: '20:00',
  budgetMax: 5000,
  passengersCount: 1,
  weights: { cost: 0.35, duration: 0.35, comfort: 0.2, carbon: 0.1 },
};

const udayapalyaJourneys = composeMultiModalJourneys(udayapalyaReq);
assert(udayapalyaJourneys.length > 0, 'Must generate journeys for Udayapalya -> Chennai');
for (const j of udayapalyaJourneys) {
  assert(j.origin.name.includes('Udayapalya'), `Origin must include Udayapalya, found ${j.origin.name}`);
  assert(j.destination.name.includes('Chennai'), `Destination must include Chennai, found ${j.destination.name}`);
  assert(j.segments[0].origin.name.includes('Udayapalya'), 'First leg starts at Udayapalya');
}
console.log(`✓ Udayapalya -> Chennai door-to-door anchored correctly with 3 legs.`);

// ============================================================================
// TEST 3: Bangalore -> Goa (this weekend under ₹6000)
// ============================================================================
console.log('\n--- Test 3: Route Bangalore -> Goa (Budget ₹6000, Localized Operators) ---');
const goaReq: TravelRequest = {
  origin: 'Bangalore',
  destination: 'Goa',
  departureDate: '2026-11-07',
  preferredArrivalBefore: '20:00',
  budgetMax: 6000,
  passengersCount: 1,
  weights: { cost: 0.4, duration: 0.3, comfort: 0.2, carbon: 0.1 },
  naturalLanguageQuery: 'Bangalore to Goa this weekend under ₹6000.',
};

const goaJourneys = composeMultiModalJourneys(goaReq);
assert(goaJourneys.length > 0, 'Must generate journeys for Bangalore -> Goa');
for (const j of goaJourneys) {
  assert(j.destination.city.toLowerCase().includes('goa'), 'Destination must be Goa');
  assert(j.segments[j.segments.length - 1].destination.city.toLowerCase().includes('goa'), 'Final leg ends in Goa');
  assert(j.totalPrice <= 6000, `Price ₹${j.totalPrice} must be <= ₹6000`);
  // Ensure last mile operator is localized to Goa (e.g. GoaMiles, Goa Coastal, Kadamba)
  const lastOp = j.segments[j.segments.length - 1].provider;
  assert(
    lastOp.includes('Goa') || lastOp.includes('Kadamba') || lastOp.includes('Coastal'),
    `Last mile operator must be localized to Goa, found '${lastOp}'`
  );
}
console.log(`✓ Bangalore -> Goa correctly generated with Goa-localized last-mile transit.`);

// ============================================================================
// TEST 4: Delhi -> Mumbai (Corridor Distance & Timing)
// ============================================================================
console.log('\n--- Test 4: Route Delhi -> Mumbai (1,385 km Long-Distance Corridor) ---');
const delhiMumbaiReq: TravelRequest = {
  origin: 'Delhi',
  destination: 'Mumbai',
  departureDate: '2026-11-05',
  preferredArrivalBefore: '20:00',
  budgetMax: 8000,
  passengersCount: 1,
  weights: { cost: 0.3, duration: 0.4, comfort: 0.2, carbon: 0.1 },
};

const dmJourneys = composeMultiModalJourneys(delhiMumbaiReq);
assert(dmJourneys.length > 0, 'Must generate journeys for Delhi -> Mumbai');
for (const j of dmJourneys) {
  assert(j.origin.city.toLowerCase().includes('delhi'), 'Origin must be Delhi');
  assert(j.destination.city.toLowerCase().includes('mumbai'), 'Destination must be Mumbai');
  // Distance should realistically reflect the ~1,385 km corridor, not 360 km
  assert(j.segments[1].distanceKm > 1000, `Intercity corridor must be > 1000 km, found ${j.segments[1].distanceKm} km`);
}
console.log(`✓ Delhi -> Mumbai distance correctly modeled (${dmJourneys[0].segments[1].distanceKm} km).`);

// ============================================================================
// TEST 5: Strict Budget Ceiling Filtering
// ============================================================================
console.log('\n--- Test 5: Budget Constraint Enforcement (₹2,000 Cap) ---');
const budgetReq: TravelRequest = {
  origin: 'Bangalore',
  destination: 'Chennai',
  departureDate: '2026-10-30',
  preferredArrivalBefore: '20:00',
  budgetMax: 2000,
  passengersCount: 1,
  weights: { cost: 0.5, duration: 0.2, comfort: 0.2, carbon: 0.1 },
};

const budgetJourneys = composeMultiModalJourneys(budgetReq);
for (const j of budgetJourneys) {
  assert(j.totalPrice <= 2000, `Journey ${j.id} price ₹${j.totalPrice} exceeds budget limit ₹2000`);
}
// Flights cost > ₹3000, so flight-based fastest journey should have been filtered out
const hasFlight = budgetJourneys.some((j) => j.modes.includes('flight'));
assert.strictEqual(hasFlight, false, 'Flight options exceeding budget must be excluded');
console.log(`✓ All ${budgetJourneys.length} returned journeys strictly respect ₹2,000 budget cap.`);

// ============================================================================
// TEST 6: Arrival Deadline Compliance
// ============================================================================
console.log('\n--- Test 6: Arrival Deadline Enforcement ---');
const deadlineReq: TravelRequest = {
  origin: 'Chennai',
  destination: 'Udupi',
  departureDate: '2026-11-02',
  preferredArrivalBefore: '20:00',
  budgetMax: 6000,
  passengersCount: 1,
  weights: { cost: 0.3, duration: 0.4, comfort: 0.2, carbon: 0.1 },
};

const deadlineJourneys = composeMultiModalJourneys(deadlineReq);
for (const j of deadlineJourneys) {
  const arrDate = new Date(j.arrivalTime);
  const arrHour = arrDate.getUTCHours();
  const arrMin = arrDate.getUTCMinutes();
  const totalMin = arrHour * 60 + arrMin;
  const deadlineMin = 20 * 60; // 20:00
  assert(totalMin <= deadlineMin, `Journey ${j.id} arrives at ${arrHour}:${arrMin}, which exceeds 20:00 deadline`);
}
console.log(`✓ All journeys arrive safely before the requested 20:00 deadline.`);

// ============================================================================
// TEST 7: Cheapest Preference Ranking
// ============================================================================
console.log('\n--- Test 7: Cheapest Preference Ranking ---');
const cheapReq: TravelRequest = {
  origin: 'Bangalore',
  destination: 'Chennai',
  departureDate: '2026-10-30',
  preferredArrivalBefore: '20:00',
  budgetMax: 5000,
  passengersCount: 1,
  weights: { cost: 0.6, duration: 0.15, comfort: 0.15, carbon: 0.1 },
  naturalLanguageQuery: 'I prefer saving money over speed.',
};

const cheapJourneys = composeMultiModalJourneys(cheapReq);
assert.strictEqual(cheapJourneys[0].recommendationCategory, 'cheapest', 'Cheapest journey must rank #1 when saving money is requested');
console.log(`✓ Cheapest option '${cheapJourneys[0].title}' ranked #1 for cost priority.`);

// ============================================================================
// TEST 8: Intermodal Segment Connectivity
// ============================================================================
console.log('\n--- Test 8: Intermodal Segment Connectivity ---');
for (const j of udupiJourneys) {
  for (let i = 0; i < j.segments.length - 1; i++) {
    const curDest = j.segments[i].destination.name;
    const nextOrig = j.segments[i + 1].origin.name;
    assert.strictEqual(
      curDest,
      nextOrig,
      `Segment ${i + 1} destination (${curDest}) must equal Segment ${i + 2} origin (${nextOrig})`
    );
  }
}
console.log(`✓ All intermodal transfer nodes connect seamlessly from origin to destination.`);

// ============================================================================
// TEST 9: Positive Transfer Timing Buffers
// ============================================================================
console.log('\n--- Test 9: Positive Transfer Timing Buffers ---');
for (const j of udupiJourneys) {
  for (let i = 0; i < j.segments.length - 1; i++) {
    const curArr = new Date(j.segments[i].arrivalTime).getTime();
    const nextDep = new Date(j.segments[i + 1].departureTime).getTime();
    const transferWaitMin = Math.round((nextDep - curArr) / 60000);
    assert(
      transferWaitMin >= 10,
      `Transfer wait between leg ${i + 1} and ${i + 2} must be >= 10 min, found ${transferWaitMin}m`
    );
  }
}
console.log(`✓ All transfers have positive, realistic connection buffers (15-50 min).`);

// ============================================================================
// TEST 10: Total Price Summation Accuracy
// ============================================================================
console.log('\n--- Test 10: Total Price Summation Accuracy ---');
for (const j of goaJourneys) {
  const sumPrice = j.segments.reduce((acc, s) => acc + s.price, 0);
  assert.strictEqual(j.totalPrice, sumPrice, `Total price ₹${j.totalPrice} does not match sum ₹${sumPrice}`);
}
console.log(`✓ Total price strictly matches sum of individual segment fares.`);

// ============================================================================
// TEST 11: Total Duration Math
// ============================================================================
console.log('\n--- Test 11: Total Duration Math ---');
for (const j of goaJourneys) {
  const depTime = new Date(j.departureTime).getTime();
  const arrTime = new Date(j.arrivalTime).getTime();
  const elapsed = Math.round((arrTime - depTime) / 60000);
  assert.strictEqual(j.totalDurationMinutes, elapsed, `Total duration ${j.totalDurationMinutes}m must match elapsed ${elapsed}m`);
}
console.log(`✓ Total duration strictly matches elapsed departure-to-arrival time.`);

// ============================================================================
// TEST 12: Wrong Destination Exclusion Validation
// ============================================================================
console.log('\n--- Test 12: Wrong Destination Exclusion Validation ---');
const wrongReq: TravelRequest = {
  origin: 'Bangalore',
  destination: 'Goa',
  departureDate: '2026-11-07',
  passengersCount: 1,
  weights: { cost: 0.3, duration: 0.4, comfort: 0.2, carbon: 0.1 },
};

// Test that a journey ending in Chennai is correctly flagged as invalid for a Goa request
const chennaiJourney = udupiJourneys.find(j => j.destination.city.includes('Udupi'))!;
const fakeInvalidJourney = {
  ...chennaiJourney,
  destination: { ...chennaiJourney.destination, name: 'Chennai Central', city: 'Chennai' },
};

const validationResult = validateJourneyAgainstRequest(fakeInvalidJourney, wrongReq);
assert.strictEqual(validationResult.valid, false, 'Validation must reject journeys with mismatched destinations');
console.log(`✓ validateJourneyAgainstRequest correctly rejected mismatched destination: ${validationResult.reason}`);

console.log('\n=================================================================');
console.log('ALL 12 TESTS PASSED SUCCESSFULLY! ✓');
console.log('=================================================================');
