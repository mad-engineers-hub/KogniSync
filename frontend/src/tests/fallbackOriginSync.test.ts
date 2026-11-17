import assert from 'node:assert';
import { searchJourneys, getLastSearchSource, setLastSearchSource } from '../api/journey';
import { composeMultiModalJourneys, resolveHubContext } from '../api/orchestrationEngine';
import { buildClientFallbackRoute } from '../api/routes';
import { validateJourneyAgainstRequest } from '../api/mockData';
import { TravelRequest } from '../types/journey';

console.log('================================================================');
console.log('M4.0.4 Regression Test Suite: Client Fallback Origin Sync');
console.log('================================================================');

// Save original fetch
const originalFetch = globalThis.fetch;

async function runAllTests() {
  // -------------------------------------------------------------------------
  // TEST A: Client Fallback: Tumkur -> Goa
  // -------------------------------------------------------------------------
  console.log('\n--- Test A: Client Fallback: Tumkur -> Goa ---');
  // Force backend offline to verify pure client fallback behavior
  globalThis.fetch = async () => {
    throw new Error('Connection refused (simulating offline backend orchestrator)');
  };

  const tumkurGoaReq: TravelRequest = {
    origin: 'Tumkur',
    destination: 'Goa',
    departureDate: '2026-11-21',
    passengersCount: 1,
    budgetMax: 3000,
    weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
  };

  const fallbackResults = await searchJourneys(tumkurGoaReq);
  assert.strictEqual(getLastSearchSource(), 'client_fallback', 'Fallback must activate when backend is unreachable');
  assert(fallbackResults.length > 0, 'Must produce candidate journeys in client fallback mode');

  for (const j of fallbackResults) {
    // 1. Origin must be Tumkur
    assert(j.origin.name.includes('Tumkur'), `Journey origin name must contain Tumkur, got: ${j.origin.name}`);
    assert(j.origin.city.includes('Tumkur'), `Journey origin city must contain Tumkur, got: ${j.origin.city}`);
    assert(
      Math.abs(j.origin.coordinates.lat - 13.34) < 0.05,
      `Origin lat must be near Tumkur (13.34), got: ${j.origin.coordinates.lat}`
    );
    assert(
      Math.abs(j.origin.coordinates.lng - 77.10) < 0.05,
      `Origin lng must be near Tumkur (77.10), got: ${j.origin.coordinates.lng}`
    );

    // 2. Destination must be Goa
    assert(j.destination.name.includes('Goa'), `Journey dest name must contain Goa, got: ${j.destination.name}`);
    assert(
      Math.abs(j.destination.coordinates.lat - 15.30) < 0.08,
      `Dest lat must be near Goa (15.30), got: ${j.destination.coordinates.lat}`
    );
    assert(
      Math.abs(j.destination.coordinates.lng - 74.12) < 0.08,
      `Dest lng must be near Goa (74.12), got: ${j.destination.coordinates.lng}`
    );

    // 3. First route coordinate must be near Tumkur, not Bangalore (~12.97, 77.59)
    const route = buildClientFallbackRoute(j);
    assert(route.segments.length > 0, 'Route must contain geometry segments');
    const firstCoord = route.segments[0].coordinates[0];
    assert(
      Math.abs(firstCoord.latitude - 13.34) < 0.05,
      `First route coordinate lat must be near Tumkur, got: ${firstCoord.latitude}`
    );
    assert(
      Math.abs(firstCoord.longitude - 77.10) < 0.05,
      `First route coordinate lng must be near Tumkur, got: ${firstCoord.longitude}`
    );

    // Ensure first coordinate is at least 30 km away from Bangalore center (12.9716, 77.5946)
    const distFromBangalore = Math.hypot(firstCoord.latitude - 12.9716, firstCoord.longitude - 77.5946) * 111;
    assert(
      distFromBangalore > 30,
      `First route coordinate must NOT be in Bengaluru! Distance: ${distFromBangalore.toFixed(1)} km`
    );

    // 4. Validate journey passes contract validation
    const val = validateJourneyAgainstRequest(j, tumkurGoaReq);
    assert.strictEqual(val.valid, true, `Journey must pass validation: ${val.reason}`);
  }
  console.log('✓ Test A passed: Client fallback Tumkur -> Goa activates, resolves to Tumkur (~13.33, 77.09), zero Bangalore contamination');

  // -------------------------------------------------------------------------
  // TEST B: Backend Orchestration Mock Simulation: Tumkur -> Goa
  // -------------------------------------------------------------------------
  console.log('\n--- Test B: Backend Orchestration: Tumkur -> Goa ---');
  // Restore live-like mock response for backend search
  globalThis.fetch = async (url: any, opts: any) => {
    const urlStr = String(url);
    if (urlStr.includes('/api/v1/journeys/search')) {
      const generated = composeMultiModalJourneys(tumkurGoaReq);
      return new Response(
        JSON.stringify({
          search_id: 'srch-m404-b-01',
          journeys: generated,
          total_count: generated.length,
          execution_time_ms: 12,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    }
    return originalFetch(url, opts);
  };

  const backendResults = await searchJourneys(tumkurGoaReq);
  assert.strictEqual(getLastSearchSource(), 'backend_orchestrator', 'Must use backend orchestrator source');
  assert(backendResults.length > 0, 'Backend must return journeys');
  assert(backendResults[0].origin.name.includes('Tumkur'), 'Backend journey origin must be Tumkur');
  assert(
    Math.abs(backendResults[0].origin.coordinates.lat - 13.34) < 0.05,
    'Backend journey origin must be at Tumkur coordinates'
  );
  console.log('✓ Test B passed: Backend orchestration correctly handles Tumkur -> Goa endpoints');

  // Force offline again for remaining client fallback tests
  globalThis.fetch = async () => {
    throw new Error('Offline fallback test');
  };

  // -------------------------------------------------------------------------
  // TEST C: Client Fallback: Bengaluru -> Goa
  // -------------------------------------------------------------------------
  console.log('\n--- Test C: Client Fallback: Bengaluru -> Goa ---');
  const blrGoaReq: TravelRequest = {
    origin: 'Bengaluru',
    destination: 'Goa',
    departureDate: '2026-11-21',
    passengersCount: 1,
    budgetMax: 5000,
    weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
  };
  const blrResults = await searchJourneys(blrGoaReq);
  assert(blrResults.length > 0, 'Must produce journeys for Bengaluru -> Goa');
  const blrFirst = blrResults[0];
  assert(
    blrFirst.origin.name.includes('Bengaluru') || blrFirst.origin.name.includes('Bangalore'),
    `Origin must reflect Bengaluru, got: ${blrFirst.origin.name}`
  );
  assert(
    Math.abs(blrFirst.origin.coordinates.lat - 12.97) < 0.05,
    `Origin lat must be near Bangalore (12.97), got: ${blrFirst.origin.coordinates.lat}`
  );
  assert(
    Math.abs(blrFirst.origin.coordinates.lng - 77.59) < 0.05,
    `Origin lng must be near Bangalore (77.59), got: ${blrFirst.origin.coordinates.lng}`
  );
  console.log('✓ Test C passed: Bengaluru is accurately preserved when explicitly requested');

  // -------------------------------------------------------------------------
  // TEST D: Client Fallback: Hubli -> Chennai
  // -------------------------------------------------------------------------
  console.log('\n--- Test D: Client Fallback: Hubli -> Chennai ---');
  const hubliChennaiReq: TravelRequest = {
    origin: 'Hubli',
    destination: 'Chennai',
    departureDate: '2026-11-21',
    passengersCount: 1,
    weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
  };
  const hubliResults = await searchJourneys(hubliChennaiReq);
  assert(hubliResults.length > 0, 'Must produce journeys for Hubli -> Chennai');
  const hcFirst = hubliResults[0];
  assert(
    hcFirst.origin.name.includes('Hubli') || hcFirst.origin.name.includes('Hubballi'),
    `Origin must reflect Hubli, got: ${hcFirst.origin.name}`
  );
  assert(
    Math.abs(hcFirst.origin.coordinates.lat - 15.36) < 0.05,
    `Hubli lat expected ~15.36, got: ${hcFirst.origin.coordinates.lat}`
  );
  assert(
    Math.abs(hcFirst.destination.coordinates.lat - 13.08) < 0.05,
    `Chennai lat expected ~13.08, got: ${hcFirst.destination.coordinates.lat}`
  );
  console.log('✓ Test D passed: Both endpoints resolve independently (Hubli ~15.36, Chennai ~13.08)');

  // -------------------------------------------------------------------------
  // TEST E: Change Origin Without Changing Destination
  // -------------------------------------------------------------------------
  console.log('\n--- Test E: Change Origin Without Changing Destination ---');
  // First query: Tumkur -> Goa
  const jnyTumkur = (await searchJourneys(tumkurGoaReq))[0];
  // Second query: Bengaluru -> Goa
  const jnyBlr = (await searchJourneys(blrGoaReq))[0];

  assert(
    Math.abs(jnyTumkur.origin.coordinates.lat - jnyBlr.origin.coordinates.lat) > 0.3,
    'Origin coordinate must shift significantly when changing from Tumkur to Bengaluru'
  );
  assert(
    Math.abs(jnyTumkur.destination.coordinates.lat - jnyBlr.destination.coordinates.lat) < 0.01,
    'Destination coordinates must remain identical (Goa)'
  );
  console.log('✓ Test E passed: Origin changes independently from Tumkur (13.33) to Bengaluru (12.96) while destination stays at Goa');

  // -------------------------------------------------------------------------
  // TEST F: Change Destination Without Changing Origin
  // -------------------------------------------------------------------------
  console.log('\n--- Test F: Change Destination Without Changing Origin ---');
  const tumkurChennaiReq: TravelRequest = {
    origin: 'Tumkur',
    destination: 'Chennai',
    departureDate: '2026-11-21',
    passengersCount: 1,
    weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
  };
  const jnyTumkurChennai = (await searchJourneys(tumkurChennaiReq))[0];

  assert(
    Math.abs(jnyTumkur.origin.coordinates.lat - jnyTumkurChennai.origin.coordinates.lat) < 0.01,
    'Origin coordinates must remain in Tumkur'
  );
  assert(
    Math.abs(jnyTumkur.destination.coordinates.lng - jnyTumkurChennai.destination.coordinates.lng) > 4.0,
    'Destination coordinates must shift significantly from West Coast (Goa ~74.12) to East Coast (Chennai ~80.27)'
  );
  console.log('✓ Test F passed: Destination updates from Goa (74.14) to Chennai (80.27) while origin stays at Tumkur');

  // -------------------------------------------------------------------------
  // TEST G: Pareto Alternative Selection
  // -------------------------------------------------------------------------
  console.log('\n--- Test G: Pareto Alternative Selection ---');
  const alternatives = await searchJourneys({
    origin: 'Tumkur',
    destination: 'Goa',
    departureDate: '2026-11-21',
    passengersCount: 1,
    budgetMax: 5000,
    weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
  });
  assert(alternatives.length >= 3, 'Must have at least 3 Pareto alternatives');
  for (const alt of alternatives) {
    assert(alt.origin.name.includes('Tumkur'), `Alternative ${alt.id} origin must be Tumkur`);
    assert(
      Math.abs(alt.origin.coordinates.lat - 13.34) < 0.05,
      `Alternative ${alt.id} origin lat must be Tumkur, got: ${alt.origin.coordinates.lat}`
    );
    assert(
      Math.abs(alt.destination.coordinates.lat - 15.30) < 0.08,
      `Alternative ${alt.id} dest lat must be Goa, got: ${alt.destination.coordinates.lat}`
    );
    const altRoute = buildClientFallbackRoute(alt);
    const startPt = altRoute.segments[0].coordinates[0];
    assert(
      Math.abs(startPt.latitude - 13.34) < 0.05,
      `Alternative ${alt.id} route geometry must start at Tumkur, got: ${startPt.latitude}`
    );
  }
  console.log(`✓ Test G passed: All ${alternatives.length} Pareto alternatives preserve Tumkur -> Goa endpoints`);

  // -------------------------------------------------------------------------
  // TEST H: Geocoding Failure / Unknown Location Handling
  // -------------------------------------------------------------------------
  console.log('\n--- Test H: Geocoding Failure Handling ---');
  let errorCaught = false;
  try {
    resolveHubContext('NonExistentCityX123', true);
  } catch (err: any) {
    errorCaught = true;
    assert(
      err.message.includes('Unable to resolve coordinates'),
      `Error message must indicate failure to resolve coordinates, got: ${err.message}`
    );
  }
  assert.strictEqual(errorCaught, true, 'resolveHubContext must throw an explicit error for unknown locations without customCoordinates');
  console.log('✓ Test H passed: Unknown locations fail with explicit error rather than silently fabricating Bengaluru coordinates');

  // -------------------------------------------------------------------------
  // TEST I: Deep Link & Refresh Simulation
  // -------------------------------------------------------------------------
  console.log('\n--- Test I: Deep Link & Refresh Simulation ---');
  // Simulate parsing URL: /plan?origin=Tumkur&destination=Goa&date=2026-11-21&passengers=1&budgetMax=3000
  const deepLinkParams = new URLSearchParams('origin=Tumkur&destination=Goa&date=2026-11-21&passengers=1&budgetMax=3000');
  const reconstructedReq: TravelRequest = {
    origin: deepLinkParams.get('origin')!,
    destination: deepLinkParams.get('destination')!,
    departureDate: deepLinkParams.get('date')!,
    passengersCount: parseInt(deepLinkParams.get('passengers')!, 10),
    budgetMax: parseInt(deepLinkParams.get('budgetMax')!, 10),
    weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
  };

  const deepLinkResults = await searchJourneys(reconstructedReq);
  assert(deepLinkResults.length > 0, 'Deep linked URL search must produce valid journeys');
  assert(deepLinkResults[0].origin.name.includes('Tumkur'), 'Deep link origin must be Tumkur');
  assert(
    Math.abs(deepLinkResults[0].origin.coordinates.lat - 13.34) < 0.05,
    'Deep link origin coords must be Tumkur'
  );
  console.log('✓ Test I passed: Deep link URL restores Tumkur -> Goa cleanly in client fallback mode');

  // Clean up
  globalThis.fetch = originalFetch;
  console.log('\n================================================================');
  console.log('All M4.0.4 Regression Tests Passed Successfully!');
  console.log('================================================================\n');
}

runAllTests().catch((err) => {
  console.error('\n❌ Test Failure in M4.0.4 Suite:', err);
  process.exit(1);
});
