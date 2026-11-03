import { describe, it } from 'node:test';
import assert from 'node:assert';
import {
  matchJourneyXR,
  fetchXRScene,
  fetchXRScenes,
  fetchSceneWayfinding,
  fetchDeviceProfiles,
} from '../api/xr';
import { matchXRSceneForHub, getJourneyXRReferences } from '../utils/xrMatching';
import { STATIC_XR_SCENES } from '../api/xrData';
import { Journey, Location, JourneySegment } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING ORGANIZER XR CAPABILITY & INTEGRATION TEST SUITE');
console.log('=================================================================');

// Test 1: Canonical Organizer Enums Conformance
console.log('\n--- Test 1: Organizer Enums Conformance ---');
const sceneTypes = ['panorama_360', 'model_3d', 'photogrammetry', 'video_360'];
const assetFormats = ['jpg_equirect', 'gltf', 'glb', 'usdz', 'ktx2', 'mp4'];
const platforms = ['webxr', 'arcore', 'arkit', 'desktop_fallback'];
const deviceClasses = ['phone_ar', 'tablet_ar', 'headset_vr', 'desktop'];

for (const scene of Object.values(STATIC_XR_SCENES)) {
  assert.ok(sceneTypes.includes(scene.scene_type), `Invalid scene_type: ${scene.scene_type}`);
  for (const asset of scene.assets) {
    assert.ok(assetFormats.includes(asset.format), `Invalid asset format: ${asset.format}`);
  }
  for (const plat of scene.supported_platforms) {
    assert.ok(platforms.includes(plat), `Invalid platform: ${plat}`);
  }
}
console.log('✓ All static XR scenes strictly comply with canonical organizer enums.');

// Test 2: Scenario 1 (Chennai -> Udupi) Match
console.log('\n--- Test 2: Scenario 1 (Chennai -> Udupi) XR Match ---');
const match1 = await matchJourneyXR({
  origin: 'Chennai',
  destination: 'Udupi',
  transfer_hubs: ['Chennai Airport', 'Mangalore Airport'],
});
assert.ok(match1.scenes.length >= 2, `Expected at least 2 scenes, got ${match1.scenes.length}`);
const sceneIds1 = match1.scenes.map((s) => s.scene_id);
assert.ok(sceneIds1.includes('xrs_mangalore_udupi_transit'), 'Missing Mangalore/Udupi transit link');
assert.ok(sceneIds1.includes('xrs_chennai_central_concourse'), 'Missing Chennai hub');
console.log('✓ Scenario 1 matched Chennai and Mangalore/Udupi arrival concourses.');

// Test 3: Scenario 2 (Udayapalya -> Chennai) Match
console.log('\n--- Test 3: Scenario 2 (Udayapalya -> Chennai) XR Match ---');
const match2 = await matchJourneyXR({
  origin: 'Udayapalya',
  destination: 'Chennai',
  transfer_hubs: ['KSR Bangalore', 'Chennai Central'],
});
assert.ok(match2.scenes.length >= 2, `Expected at least 2 scenes, got ${match2.scenes.length}`);
const sceneIds2 = match2.scenes.map((s) => s.scene_id);
assert.ok(sceneIds2.includes('xrs_ksr_bengaluru_interchange'), 'Missing KSR Bengaluru interchange');
assert.ok(sceneIds2.includes('xrs_chennai_central_concourse'), 'Missing Chennai Central');
console.log('✓ Scenario 2 door-to-door matched KSR Bengaluru and Chennai Central hubs.');

// Test 4: Scenario 3 (Bangalore -> Goa) Match
console.log('\n--- Test 4: Scenario 3 (Bangalore -> Goa) XR Match ---');
const match3 = await matchJourneyXR({
  origin: 'Bangalore',
  destination: 'Goa',
  transfer_hubs: ['Madgaon Junction'],
});
assert.ok(match3.scenes.length >= 1, `Expected at least 1 scene, got ${match3.scenes.length}`);
const sceneIds3 = match3.scenes.map((s) => s.scene_id);
assert.ok(sceneIds3.includes('xrs_goa_madgaon_hub'), 'Missing Goa Madgaon transit hub');
console.log('✓ Scenario 3 matched Goa Madgaon concourse.');

// Test 5: Canonical Hotel with has_xr_scene == True (htl_8179b205)
console.log('\n--- Test 5: Canonical Hotel (Grand Courtyard Chennai) XR Match ---');
const matchHotel = await matchJourneyXR({
  destination: 'Chennai',
  hotel_id: 'htl_8179b205',
});
const sceneIdsHotel = matchHotel.scenes.map((s) => s.scene_id);
assert.ok(sceneIdsHotel.includes('xrs_htl_8179b205'), 'Missing Grand Courtyard hotel XR scene');
console.log('✓ Canonical hotel htl_8179b205 resolved with virtual lobby and suite tour.');

// Test 6: AR Wayfinding Integrity
console.log('\n--- Test 6: AR Wayfinding Routes Integrity ---');
const wayfindingCases = await fetchSceneWayfinding('xrs_chennai_central_concourse');
assert.ok(wayfindingCases.length >= 2, 'Expected at least 2 wayfinding cases');
for (const c of wayfindingCases) {
  assert.ok(c.estimated_walking_minutes > 0, 'Estimated walk time must be positive');
  assert.ok(c.steps.length > 0, 'Must have at least one step');
  c.steps.forEach((step, idx) => {
    assert.strictEqual(step.step_number, idx + 1, 'Steps must be sequentially numbered');
    assert.ok(step.distance_meters > 0, 'Step distance must be positive');
    assert.ok(step.target_landmark.length > 0, 'Target landmark required');
  });
}
console.log('✓ AR wayfinding turn-by-turn routes validated with distances and landmarks.');

// Test 7: Hotspots Spherical Coordinates
console.log('\n--- Test 7: Spherical Coordinate Validation ---');
for (const scene of Object.values(STATIC_XR_SCENES)) {
  for (const h of scene.hotspots) {
    assert.ok(h.yaw >= 0 && h.yaw <= 360, `Invalid yaw ${h.yaw} for hotspot ${h.hotspot_id}`);
    assert.ok(h.pitch >= -90 && h.pitch <= 90, `Invalid pitch ${h.pitch} for hotspot ${h.hotspot_id}`);
    assert.ok(h.hotspot_id.startsWith('xrh_'), `Hotspot ID must start with xrh_: ${h.hotspot_id}`);
  }
}
console.log('✓ All 360 hotspots conform to valid spherical bounds and xrh_ ID prefixes.');

// Test 8: getJourneyXRReferences Helper
console.log('\n--- Test 8: Journey XR Reference Extraction ---');
const locOrigin: Location = {
  id: 'loc-udp',
  name: 'Udayapalya Hub',
  city: 'Bengaluru',
  type: 'address',
  coordinates: { lat: 12.9716, lng: 77.5946 },
};

const locIntermediate: Location = {
  id: 'loc-ksr',
  name: 'KSR Bengaluru Railway Station',
  city: 'Bengaluru',
  type: 'railway_station',
  coordinates: { lat: 12.978, lng: 77.569 },
};

const locDestination: Location = {
  id: 'loc-mas',
  name: 'Chennai Central Railway Station',
  city: 'Chennai',
  code: 'MAS',
  type: 'railway_station',
  coordinates: { lat: 13.0827, lng: 80.2707 },
};

const dummyJourney: Journey = {
  id: 'jny-test',
  title: 'Test Multimodal Journey',
  origin: locOrigin,
  destination: locDestination,
  departureTime: '2026-11-04T08:00:00Z',
  arrivalTime: '2026-11-04T15:00:00Z',
  totalDurationMinutes: 420,
  totalPrice: 1200,
  currency: 'INR',
  totalTransfers: 1,
  carbonKg: 12,
  comfortScore: 8,
  modes: ['bus', 'train'],
  recommendationCategory: 'fastest',
  aiExplanation: {
    rankReason: 'Optimal transit speed',
    summary: 'Clean transit link with minimal wait',
    tradeOffs: ['Slightly higher fare for guaranteed seat'],
    score: 95,
  },
  bookingFeasibility: {
    holdSupported: true,
    concurrencySafe: true,
    holdTtlSeconds: 600,
  },
  segments: [
    {
      segmentId: 'seg-1',
      mode: 'bus',
      provider: 'BMTC',
      vehicleName: 'Route 215',
      origin: locOrigin,
      destination: locIntermediate,
      departureTime: '2026-11-04T08:00:00Z',
      arrivalTime: '2026-11-04T08:40:00Z',
      durationMinutes: 40,
      price: 45,
      currency: 'INR',
      distanceKm: 15,
      carbonKg: 1.2,
      comfortScore: 7,
      availability: { status: 'available', remainingUnits: 30 },
      transferBufferMinutes: 15,
    },
    {
      segmentId: 'seg-2',
      mode: 'train',
      provider: 'Indian Railways',
      vehicleName: 'Superfast Express',
      vehicleNumber: '12640',
      origin: locIntermediate,
      destination: locDestination,
      departureTime: '2026-11-04T08:55:00Z',
      arrivalTime: '2026-11-04T14:15:00Z',
      durationMinutes: 320,
      price: 1155,
      currency: 'INR',
      distanceKm: 350,
      carbonKg: 10.8,
      comfortScore: 8,
      availability: { status: 'available', remainingUnits: 12 },
    },
  ],
};

const refs = getJourneyXRReferences(dummyJourney);
assert.ok(refs.length >= 2, `Expected at least 2 references, got ${refs.length}`);
const refIds = refs.map((r) => r.sceneId);
assert.ok(refIds.includes('xrs_ksr_bengaluru_interchange'), 'Missing KSR interchange');
assert.ok(refIds.includes('xrs_chennai_central_concourse'), 'Missing Chennai Central');
console.log('✓ Successfully extracted intermediate and arrival XR station references.');

// Test 9: Device Profiles
console.log('\n--- Test 9: Device Profiles & Honest Capabilities ---');
const profiles = await fetchDeviceProfiles();
assert.ok(profiles.length >= 4, 'Must return at least 4 device profiles');
const desktopProfile = profiles.find((p) => p.platform === 'desktop_fallback');
assert.ok(desktopProfile?.supported === true, 'Desktop fallback must be supported');
const webxrProfile = profiles.find((p) => p.platform === 'webxr');
assert.ok(webxrProfile?.supported === false, 'WebXR must not be falsely claimed as universally active');
console.log('✓ Device capability detection is honest without fake WebXR claims.');

console.log('\n=================================================================');
console.log('ALL 9 ORGANIZER XR CAPABILITY TESTS PASSED! ✓');
console.log('=================================================================');
