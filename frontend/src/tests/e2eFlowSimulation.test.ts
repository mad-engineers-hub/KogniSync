import assert from 'node:assert';
import { normalizeTravelIntent } from '../utils/travelUtils';
import { searchJourneys, getJourneyById, extractClientIntent } from '../api/journey';
import { createHold } from '../api/booking';
import { TravelRequestState } from '../context/TravelRequestContext';

console.log('=================================================================');
console.log('RUNNING FULL END-TO-END FLOW & REQUEST-SWITCHING TEST');
console.log('=================================================================');

const initialPlannerState: TravelRequestState = {
  origin: 'Bangalore',
  destination: 'Chennai',
  date: '2026-10-30',
  displayDate: 'Tomorrow',
  timeDeadlineText: 'Arrive by 2:00 PM',
  arrivalDeadline: '14:00',
  departureTime: null,
  passengers: 1,
  budget: 3000,
  currency: 'INR',
  weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
  selectedModes: {
    flight: true,
    train: true,
    bus: true,
    cab: true,
    metro: true,
    rapido: true,
    auto: true,
    walk: false,
  },
  naturalLanguageQuery: '',
  understoodMessage: null,
};

async function simulatePlannerToBooking(prompt: string) {
  console.log(`\n--- Simulating prompt: "${prompt}" ---`);
  // 1. Natural Language Intent Extraction
  const intent = extractClientIntent(prompt);
  assert(intent.origin, 'Intent must extract origin');
  assert(intent.destination, 'Intent must extract destination');
  console.log(`1. Extracted Intent: ${intent.origin} -> ${intent.destination} | Budget: ₹${intent.budget} | Arrival: ${intent.arrival_deadline} | TimePriority: ${intent.time_priority}`);

  // 2. Normalization to Planner State
  const plannerState = normalizeTravelIntent(intent, initialPlannerState);
  assert.strictEqual(plannerState.origin, intent.origin);
  assert.strictEqual(plannerState.destination, intent.destination);

  // 3. Build Search Request (as ResultsPage receives via URL)
  const request = {
    origin: plannerState.origin,
    destination: plannerState.destination,
    departureDate: plannerState.date,
    preferredArrivalBefore: plannerState.arrivalDeadline || undefined,
    budgetMax: plannerState.budget || undefined,
    passengersCount: plannerState.passengers,
    weights: plannerState.weights,
    naturalLanguageQuery: prompt,
  };

  // 4. Orchestration / Results Generation
  const results = await searchJourneys(request);
  assert(results.length > 0, 'Must produce multi-modal journeys');
  console.log(`2. Orchestration: Generated ${results.length} multi-modal options.`);

  // 5. Verify Results Constraints & Segments
  for (const j of results) {
    assert(j.segments.length >= 3, `Journey ${j.id} must have >= 3 segments, found ${j.segments.length}`);
    assert(j.origin.name.toLowerCase().includes(intent.origin.toLowerCase()), `Journey origin mismatch: ${j.origin.name} vs ${intent.origin}`);
    assert(j.destination.name.toLowerCase().includes(intent.destination.toLowerCase()), `Journey dest mismatch: ${j.destination.name} vs ${intent.destination}`);
    if (intent.budget) {
      assert(j.totalPrice <= intent.budget, `Price ₹${j.totalPrice} exceeds budget ₹${intent.budget}`);
    }
  }

  const topJourney = results[0];
  console.log(`3. ResultsPage Top Pick: [${topJourney.recommendationCategory.toUpperCase()}] ${topJourney.title} (₹${topJourney.totalPrice}, ${topJourney.totalDurationMinutes}m)`);

  // 6. Navigate to DetailsPage (Retrieve by Journey ID)
  const detailsJourney = await getJourneyById(topJourney.id);
  assert(detailsJourney !== null, 'Details page must retrieve journey by ID');
  assert.strictEqual(detailsJourney.id, topJourney.id, 'Details journey ID must match');
  assert.strictEqual(detailsJourney.totalPrice, topJourney.totalPrice, 'Details price must match');
  assert.strictEqual(detailsJourney.segments.length, topJourney.segments.length, 'Details segments count must match');
  console.log(`4. DetailsPage: Retrieved identical journey '${detailsJourney.id}' with ${detailsJourney.segments.length} segments.`);

  // 7. Proceed to Booking Flow (Acquire Inventory Hold)
  const hold = await createHold(topJourney.id);
  assert(hold !== null, 'Booking hold must succeed');
  assert.strictEqual(hold.journeyId, topJourney.id, 'Hold journeyId must match');
  assert(hold.expiresAt, 'Hold must have expiry');
  console.log(`5. BookingPage: Acquired hold ${hold.holdId} (Status: ${hold.status}, Expires: ${hold.expiresAt})`);

  return { intent, results, topJourney };
}

async function runAll() {
  // Scenario A
  const simA = await simulatePlannerToBooking(
    'I need to reach Udupi from Chennai tomorrow before 8 PM. My budget is ₹5000 and I prefer speed.'
  );
  assert.strictEqual(simA.topJourney.recommendationCategory, 'fastest');

  // Scenario B (Request Switching to Udayapalya -> Chennai)
  const simB = await simulatePlannerToBooking(
    'I want to travel from Udayapalya to Chennai tomorrow before 8 PM with a budget of ₹5,000.'
  );
  assert(simB.topJourney.origin.name.includes('Udayapalya'), 'Must start at Udayapalya');

  // Scenario C (Request Switching to Bangalore -> Goa)
  const simC = await simulatePlannerToBooking(
    'Bangalore to Goa this weekend under ₹6000.'
  );
  assert(simC.topJourney.destination.name.includes('Goa'), 'Must end in Goa');

  // Verify that journeys for A, B, and C are completely different
  console.log('\n--- Verifying Request Differentiation ---');
  assert.notStrictEqual(simA.topJourney.id, simB.topJourney.id, 'Scenario A and B must differ');
  assert.notStrictEqual(simB.topJourney.id, simC.topJourney.id, 'Scenario B and C must differ');
  assert.notStrictEqual(simA.topJourney.origin.name, simB.topJourney.origin.name, 'Origins must differ');
  assert.notStrictEqual(simA.topJourney.destination.name, simC.topJourney.destination.name, 'Destinations must differ');
  console.log('✓ All 3 scenarios produce completely different, request-specific multi-modal journeys!');

  console.log('\n=================================================================');
  console.log('FULL END-TO-END FLOW & SCENARIO VERIFICATION SUCCEEDED! ✓');
  console.log('=================================================================');
}

runAll().catch((err) => {
  console.error('Test failed with error:', err);
  process.exit(1);
});
