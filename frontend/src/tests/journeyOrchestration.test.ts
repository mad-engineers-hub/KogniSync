import assert from 'node:assert';
import { composeMultiModalJourneys } from '../api/orchestrationEngine';
import { validateJourneyAgainstRequest } from '../api/mockData';
import { TravelRequest } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING MULTI-MODAL JOURNEY ORCHESTRATION TEST SUITE');
console.log('=================================================================');

const sampleRequest: TravelRequest = {
  origin: 'Udayapalya',
  destination: 'Chennai',
  departureDate: '2026-10-30',
  preferredArrivalBefore: '17:00',
  budgetMax: 5000,
  passengersCount: 1,
  weights: { cost: 0.2, duration: 0.5, comfort: 0.2, carbon: 0.1 }, // Speed preference
};

const journeys = composeMultiModalJourneys(sampleRequest);
console.log(`Generated ${journeys.length} journeys for Udayapalya -> Chennai under ₹5,000.`);

// ---------------------------------------------------------------------------
// TEST 1: Multiple Segments (At least 3 legs for locality -> city: first-mile, main, last-mile)
// ---------------------------------------------------------------------------
console.log('\n--- Test 1: Multiple Segments Architecture ---');
for (const j of journeys) {
  assert(
    j.segments.length >= 3,
    `Journey ${j.id} must have >= 3 segments, found ${j.segments.length}`
  );
  assert(
    j.totalTransfers >= 2,
    `Journey ${j.id} must model at least 2 transfers, found ${j.totalTransfers}`
  );
  console.log(`✓ ${j.recommendationCategory.toUpperCase()}: ${j.segments.length} segments, ${j.totalTransfers} transfers`);
}

// ---------------------------------------------------------------------------
// TEST 2: Correct Total Price (sum of segment prices)
// ---------------------------------------------------------------------------
console.log('\n--- Test 2: Correct Total Price Summation ---');
for (const j of journeys) {
  const sumPrice = j.segments.reduce((acc, seg) => acc + seg.price, 0);
  assert.strictEqual(
    j.totalPrice,
    sumPrice,
    `Total price ₹${j.totalPrice} does not match sum of segments ₹${sumPrice}`
  );
  console.log(`✓ ${j.id}: Total ₹${j.totalPrice} matches sum of segments (${j.segments.map(s => `₹${s.price}`).join(' + ')})`);
}

// ---------------------------------------------------------------------------
// TEST 3: Correct Total Duration (includes transfer/wait time)
// ---------------------------------------------------------------------------
console.log('\n--- Test 3: Correct Total Duration & Transfer Wait Calculation ---');
for (const j of journeys) {
  const depTime = new Date(j.departureTime).getTime();
  const arrTime = new Date(j.arrivalTime).getTime();
  const calculatedDuration = Math.round((arrTime - depTime) / 60000);
  assert.strictEqual(
    j.totalDurationMinutes,
    calculatedDuration,
    `Journey total duration ${j.totalDurationMinutes}m must match elapsed time ${calculatedDuration}m`
  );
  const transitOnly = j.segments.reduce((acc, s) => acc + s.durationMinutes, 0);
  assert(
    j.totalDurationMinutes > transitOnly,
    `Total duration (${j.totalDurationMinutes}m) must be strictly greater than transit time (${transitOnly}m) due to transfer buffers`
  );
  console.log(`✓ ${j.id}: Elapsed ${j.totalDurationMinutes}m = transit ${transitOnly}m + transfer wait ${j.waitingDurationMinutes}m`);
}

// ---------------------------------------------------------------------------
// TEST 4: Budget Constraint Enforcement
// ---------------------------------------------------------------------------
console.log('\n--- Test 4: Budget Constraint (All Journeys <= ₹5,000) ---');
for (const j of journeys) {
  assert(
    j.totalPrice <= 5000,
    `Journey ${j.id} price ₹${j.totalPrice} exceeds budget of ₹5,000`
  );
  console.log(`✓ ${j.id}: ₹${j.totalPrice} <= ₹5,000 budget`);
}

// ---------------------------------------------------------------------------
// TEST 5: Arrival Deadline (All Journeys Arrive <= 5:00 PM / 17:00)
// ---------------------------------------------------------------------------
console.log('\n--- Test 5: Arrival Deadline Enforcement ---');
for (const j of journeys) {
  const arrDate = new Date(j.arrivalTime);
  const arrHour = arrDate.getUTCHours();
  const arrMin = arrDate.getUTCMinutes();
  const totalMinutes = arrHour * 60 + arrMin;
  const deadlineMinutes = 17 * 60; // 17:00

  assert(
    totalMinutes <= deadlineMinutes,
    `Journey ${j.id} arrives at ${arrHour}:${arrMin} UTC, exceeding deadline of 17:00`
  );
  console.log(`✓ ${j.id}: Arrives at ${String(arrHour).padStart(2, '0')}:${String(arrMin).padStart(2, '0')} before 17:00 deadline`);
}

// ---------------------------------------------------------------------------
// TEST 6: Transfer Feasibility (segment[i].arr + buffer <= segment[i+1].dep)
// ---------------------------------------------------------------------------
console.log('\n--- Test 6: Intermodal Transfer Feasibility ---');
for (const j of journeys) {
  for (let i = 0; i < j.segments.length - 1; i++) {
    const s1 = j.segments[i];
    const s2 = j.segments[i + 1];
    const s1Arr = new Date(s1.arrivalTime).getTime();
    const s2Dep = new Date(s2.departureTime).getTime();
    const gapMinutes = Math.round((s2Dep - s1Arr) / 60000);

    assert(
      s2Dep > s1Arr,
      `Impossible transfer in ${j.id}: segment ${i + 1} arrives at ${s1.arrivalTime} but segment ${i + 2} departs at ${s2.departureTime}`
    );
    assert(
      gapMinutes >= (s1.transferBufferMinutes || 10),
      `Transfer buffer ${gapMinutes}m between leg ${i + 1} and ${i + 2} is less than required buffer ${s1.transferBufferMinutes}m`
    );
  }
  console.log(`✓ ${j.id}: All ${j.segments.length - 1} transfers are strictly feasible with positive buffers`);
}

// ---------------------------------------------------------------------------
// TEST 7: Correct Origin (Udayapalya is actually the first segment origin)
// ---------------------------------------------------------------------------
console.log('\n--- Test 7: Correct Origin Anchoring ---');
for (const j of journeys) {
  const firstSegOrigName = j.segments[0].origin.name.toLowerCase();
  assert(
    firstSegOrigName.includes('udayapalya'),
    `First segment origin '${j.segments[0].origin.name}' must be Udayapalya`
  );
  console.log(`✓ ${j.id}: First leg begins at ${j.segments[0].origin.name}`);
}

// ---------------------------------------------------------------------------
// TEST 8: Correct Destination (Final segment terminates at Chennai)
// ---------------------------------------------------------------------------
console.log('\n--- Test 8: Correct Destination Anchoring ---');
for (const j of journeys) {
  const lastSeg = j.segments[j.segments.length - 1];
  const lastSegDestName = lastSeg.destination.name.toLowerCase();
  const lastSegDestCity = lastSeg.destination.city.toLowerCase();
  assert(
    lastSegDestName.includes('chennai') || lastSegDestCity.includes('chennai'),
    `Final segment destination '${lastSeg.destination.name}' must terminate at Chennai`
  );
  console.log(`✓ ${j.id}: Final leg terminates at ${lastSeg.destination.name}`);
}

// ---------------------------------------------------------------------------
// TEST 9: Category Ranking Alignment
// ---------------------------------------------------------------------------
console.log('\n--- Test 9: Category Optimization Ranking ---');
const fastest = journeys.find(j => j.recommendationCategory === 'fastest')!;
const cheapest = journeys.find(j => j.recommendationCategory === 'cheapest')!;
const greenest = journeys.find(j => j.recommendationCategory === 'greenest')!;

assert(fastest, 'Fastest journey must exist');
assert(cheapest, 'Cheapest journey must exist');
assert(greenest, 'Greenest journey must exist');

// Fastest must have the lowest duration among all
for (const j of journeys) {
  assert(
    fastest.totalDurationMinutes <= j.totalDurationMinutes,
    `Fastest duration (${fastest.totalDurationMinutes}m) is not <= ${j.id} (${j.totalDurationMinutes}m)`
  );
}
console.log(`✓ Fastest has minimum duration: ${fastest.totalDurationMinutes}m`);

// Cheapest must have the lowest total price
for (const j of journeys) {
  assert(
    cheapest.totalPrice <= j.totalPrice,
    `Cheapest price (₹${cheapest.totalPrice}) is not <= ${j.id} (₹${j.totalPrice})`
  );
}
console.log(`✓ Cheapest has minimum price: ₹${cheapest.totalPrice}`);

// Greenest must have the lowest carbon footprint
for (const j of journeys) {
  assert(
    greenest.carbonKg <= j.carbonKg,
    `Greenest carbon (${greenest.carbonKg}kg) is not <= ${j.id} (${j.carbonKg}kg)`
  );
}
console.log(`✓ Greenest has lowest carbon: ${greenest.carbonKg} kg CO2`);

// ---------------------------------------------------------------------------
// TEST 10: No Single-Segment Regression
// ---------------------------------------------------------------------------
console.log('\n--- Test 10: No Single-Segment Regression ---');
for (const j of journeys) {
  assert.notStrictEqual(
    j.segments.length,
    1,
    `Regression detected: journey ${j.id} collapsed into a single transport segment!`
  );
  // Ensure mode diversity
  const uniqueModes = new Set(j.segments.map(s => s.mode));
  assert(
    uniqueModes.size >= 2,
    `Journey ${j.id} must be intermodal across multiple modes, found: ${Array.from(uniqueModes).join(', ')}`
  );
}
console.log('✓ All journeys verified multi-modal with distinct first-mile and last-mile legs.');

// ---------------------------------------------------------------------------
// TEST 11: Validation Function Integration
// ---------------------------------------------------------------------------
console.log('\n--- Test 11: Validation Function Integration ---');
for (const j of journeys) {
  const result = validateJourneyAgainstRequest(j, sampleRequest);
  assert.strictEqual(
    result.valid,
    true,
    `validateJourneyAgainstRequest failed for ${j.id}: ${result.reason}`
  );
}
console.log('✓ All composed journeys pass validateJourneyAgainstRequest.');

console.log('\n=================================================================');
console.log('ALL 11 VALIDATION TESTS PASSED SUCCESSFULLY! ✓');
console.log('=================================================================');
