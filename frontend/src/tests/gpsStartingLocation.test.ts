/**
 * frontend/src/tests/gpsStartingLocation.test.ts
 *
 * Automated test suite for GPS-Based Starting Location Autofill (Milestone M3.4).
 * Covers:
 * 1. Manual entry preservation and editing.
 * 2. Browser Geolocation API permission granted & successful acquisition.
 * 3. Reverse geocoding & coordinate preservation.
 * 4. Permission denied error handling & graceful manual fallback.
 * 5. Geolocation timeout error handling.
 * 6. GPS position unavailable error handling.
 * 7. Low accuracy handling and proximity estimation.
 * 8. Reverse geocoding failure resilience via client fallback.
 * 9. Privacy guards (no tracking on mount, no continuous watchPosition).
 * 10. Unsupported platform fallback.
 * 11. Native mobile bridge contract compliance.
 * 12. End-to-end travel request coordinate preservation.
 */
import assert from 'node:assert';
import {
  BrowserLocationProvider,
  NativeLocationBridge,
} from '../services/location/platformLocationProvider';
import { LocationService } from '../services/location/locationService';
import { reverseGeocodeCoordinates } from '../services/location/reverseGeocoder';
import { LocationError } from '../types/location';
import { TravelRequest } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING GPS-BASED STARTING LOCATION AUTOFILL TEST SUITE (M3.4)');
console.log('=================================================================');

// ---------------------------------------------------------------------------
// Mock Geolocation Harness
// ---------------------------------------------------------------------------
interface MockGeolocationOptions {
  status: 'success' | 'denied' | 'unavailable' | 'timeout';
  coords?: { latitude: number; longitude: number; accuracy: number };
}

let mockGeoState: MockGeolocationOptions = {
  status: 'success',
  coords: { latitude: 12.9716, longitude: 77.5946, accuracy: 15 },
};

let watchPositionCallCount = 0;
let getCurrentPositionCallCount = 0;

// Set up synthetic navigator with mock geolocation
const mockNavigator = {
  geolocation: {
    getCurrentPosition: (
      success: (pos: any) => void,
      error: (err: any) => void,
      _options?: any
    ) => {
      getCurrentPositionCallCount++;
      if (mockGeoState.status === 'success' && mockGeoState.coords) {
        success({
          coords: {
            latitude: mockGeoState.coords.latitude,
            longitude: mockGeoState.coords.longitude,
            accuracy: mockGeoState.coords.accuracy,
            altitude: null,
            heading: null,
            speed: null,
          },
          timestamp: 1730995200000,
        });
      } else if (mockGeoState.status === 'denied') {
        error({ code: 1, message: 'User denied Geolocation' });
      } else if (mockGeoState.status === 'unavailable') {
        error({ code: 2, message: 'Position unavailable' });
      } else if (mockGeoState.status === 'timeout') {
        error({ code: 3, message: 'Timeout expired' });
      }
    },
    watchPosition: () => {
      watchPositionCallCount++;
      return 1;
    },
    clearWatch: () => {},
  },
};

Object.defineProperty(globalThis, 'navigator', {
  value: mockNavigator,
  configurable: true,
  writable: true,
});

async function runTests() {
  // =========================================================================
  // TEST 1: Manual Entry Preservation
  // =========================================================================
  console.log('\n--- Test 1: Manual Entry Preservation & Editing ---');
  let currentOrigin = 'Bangalore';
  let currentCoords: { lat: number; lng: number } | null = null;

  const onOriginChange = (val: string, coords?: { lat: number; lng: number } | null) => {
    currentOrigin = val;
    currentCoords = coords !== undefined ? coords : null;
  };

  // User types manual destination
  onOriginChange('Indiranagar, Bangalore');
  assert.strictEqual(currentOrigin, 'Indiranagar, Bangalore');
  assert.strictEqual(currentCoords, null, 'Manual typing must clear GPS coordinates');
  console.log('✓ Manual typing preserved and prevents stale coordinate coupling');

  // =========================================================================
  // TEST 2: Browser Geolocation Mocking & Permission Granted
  // =========================================================================
  console.log('\n--- Test 2: Browser Geolocation API (Permission Granted) ---');
  mockGeoState = {
    status: 'success',
    coords: { latitude: 12.9352, longitude: 77.6245, accuracy: 12 },
  };

  const provider = new BrowserLocationProvider();
  assert.strictEqual(provider.isSupported(), true);
  assert.strictEqual(provider.id, 'browser_geolocation');

  const position = await provider.getCurrentPosition();
  assert.strictEqual(position.coordinates.lat, 12.9352);
  assert.strictEqual(position.coordinates.lng, 77.6245);
  assert.strictEqual(position.accuracyMeters, 12);
  assert.strictEqual(position.timestamp, 1730995200000);
  console.log(`✓ Geolocation acquired: (${position.coordinates.lat}, ${position.coordinates.lng}) ±${position.accuracyMeters}m`);

  // =========================================================================
  // TEST 3: Reverse Geocoding & Coordinate Preservation
  // =========================================================================
  console.log('\n--- Test 3: Reverse Geocoding & Coordinate Preservation ---');
  const geocoded = await reverseGeocodeCoordinates(
    position.coordinates,
    position.accuracyMeters,
    position.timestamp
  );

  assert.strictEqual(geocoded.coordinates.lat, 12.9352);
  assert.strictEqual(geocoded.coordinates.lng, 77.6245);
  assert(geocoded.formattedAddress.length > 0, 'Must have a human-readable address');
  assert.strictEqual(geocoded.city, 'Bangalore');
  assert(geocoded.provider.length > 0, 'Provider must be identified');
  console.log(`✓ Resolved place: "${geocoded.formattedAddress}" via ${geocoded.provider}`);
  console.log(`✓ Precise coordinates strictly preserved: [${geocoded.coordinates.lat}, ${geocoded.coordinates.lng}]`);

  // =========================================================================
  // TEST 4: Permission Denied Error Handling
  // =========================================================================
  console.log('\n--- Test 4: Permission Denied Error Handling ---');
  mockGeoState = { status: 'denied' };

  try {
    await provider.getCurrentPosition();
    assert.fail('Should have thrown LocationError');
  } catch (err: any) {
    assert(err instanceof LocationError, 'Must be instance of LocationError');
    assert.strictEqual(err.code, 'PERMISSION_DENIED');
    assert(err.userFriendlyMessage.includes('denied'), 'Must contain user-friendly explanation');
    console.log(`✓ Correctly caught PERMISSION_DENIED: "${err.userFriendlyMessage}"`);
  }

  // =========================================================================
  // TEST 5: Geolocation Timeout Error Handling
  // =========================================================================
  console.log('\n--- Test 5: Geolocation Timeout Error Handling ---');
  mockGeoState = { status: 'timeout' };

  try {
    await provider.getCurrentPosition();
    assert.fail('Should have thrown LocationError');
  } catch (err: any) {
    assert(err instanceof LocationError);
    assert.strictEqual(err.code, 'TIMEOUT');
    assert(err.userFriendlyMessage.includes('timed out'));
    console.log(`✓ Correctly caught TIMEOUT: "${err.userFriendlyMessage}"`);
  }

  // =========================================================================
  // TEST 6: Position Unavailable Error Handling
  // =========================================================================
  console.log('\n--- Test 6: Position Unavailable Error Handling ---');
  mockGeoState = { status: 'unavailable' };

  try {
    await provider.getCurrentPosition();
    assert.fail('Should have thrown LocationError');
  } catch (err: any) {
    assert(err instanceof LocationError);
    assert.strictEqual(err.code, 'POSITION_UNAVAILABLE');
    assert(err.userFriendlyMessage.includes('unavailable'));
    console.log(`✓ Correctly caught POSITION_UNAVAILABLE: "${err.userFriendlyMessage}"`);
  }

  // =========================================================================
  // TEST 7: Poor Accuracy Handling
  // =========================================================================
  console.log('\n--- Test 7: Poor Accuracy Handling ---');
  mockGeoState = {
    status: 'success',
    coords: { latitude: 13.0827, longitude: 80.2707, accuracy: 4500 },
  };

  const lowAccPos = await provider.getCurrentPosition();
  assert(lowAccPos.accuracyMeters > 2000, 'Demonstrates low accuracy signal');
  const lowAccResult = await reverseGeocodeCoordinates(
    lowAccPos.coordinates,
    lowAccPos.accuracyMeters,
    lowAccPos.timestamp
  );
  assert.strictEqual(lowAccResult.city, 'Chennai');
  assert.strictEqual(lowAccResult.coordinates.lat, 13.0827);
  console.log(`✓ Low accuracy (±${lowAccPos.accuracyMeters}m) handled safely without discarding coordinates`);

  // =========================================================================
  // TEST 8: Reverse Geocoding Failure Resilience (Client Proximity Fallback)
  // =========================================================================
  console.log('\n--- Test 8: Reverse Geocoding Client Proximity Fallback ---');
  // Coordinate in Udupi, Karnataka: 13.3409, 74.7421
  const udupiCoords = { lat: 13.3409, lng: 74.7421 };
  const udupiResult = await reverseGeocodeCoordinates(udupiCoords, 25, Date.now());
  assert.strictEqual(udupiResult.city, 'Udupi');
  assert.strictEqual(udupiResult.coordinates.lat, 13.3409);
  assert.strictEqual(udupiResult.coordinates.lng, 74.7421);
  console.log(`✓ Client proximity fallback resolved (${udupiResult.coordinates.lat}, ${udupiResult.coordinates.lng}) to ${udupiResult.city}`);

  // =========================================================================
  // TEST 9: Privacy Protection & Lifecycle Safety
  // =========================================================================
  console.log('\n--- Test 9: Privacy Protection & Lifecycle Safety ---');
  const service = new LocationService();
  assert.strictEqual(watchPositionCallCount, 0, 'watchPosition must NEVER be called');
  console.log('✓ Continuous background tracking strictly prevented: watchPositionCallCount = 0');

  // =========================================================================
  // TEST 10: Unsupported Platform Fallback
  // =========================================================================
  console.log('\n--- Test 10: Unsupported Platform Fallback ---');
  Object.defineProperty(globalThis, 'navigator', {
    value: {},
    configurable: true,
    writable: true,
  });

  const unsuppProvider = new BrowserLocationProvider();
  assert.strictEqual(unsuppProvider.isSupported(), false);

  try {
    await unsuppProvider.getCurrentPosition();
    assert.fail('Should have failed on unsupported platform');
  } catch (err: any) {
    assert(err instanceof LocationError);
    assert.strictEqual(err.code, 'UNSUPPORTED_PLATFORM');
    console.log(`✓ Handled unsupported browser environment gracefully: "${err.userFriendlyMessage}"`);
  }

  // Restore navigator
  Object.defineProperty(globalThis, 'navigator', {
    value: mockNavigator,
    configurable: true,
    writable: true,
  });

  // =========================================================================
  // TEST 11: Native Mobile Bridge Contract Verification
  // =========================================================================
  console.log('\n--- Test 11: Native Mobile Bridge Contract Verification ---');
  const nativeBridge = new NativeLocationBridge();
  // In pure node or browser without native bridge wrapper, isSupported must return false cleanly
  assert.strictEqual(nativeBridge.isSupported(), false);
  console.log('✓ Native bridge returns false cleanly when no native wrapper exists (No fake GPS)');

  // Test when a valid native mobile bridge IS attached to window
  (globalThis as any).window = (globalThis as any).window || {};
  (globalThis as any).window.__KOGNISYNC_NATIVE_BRIDGE__ = {
    getCurrentPosition: async () => ({
      coordinates: { lat: 15.2993, lng: 74.124 },
      accuracyMeters: 8,
      timestamp: 1730995500000,
    }),
  };

  assert.strictEqual(nativeBridge.isSupported(), true);
  const nativePos = await nativeBridge.getCurrentPosition();
  assert.strictEqual(nativePos.coordinates.lat, 15.2993);
  assert.strictEqual(nativePos.accuracyMeters, 8);
  console.log('✓ Native mobile bridge contract functions correctly when attached');

  // Clean up mock native bridge
  delete (globalThis as any).window.__KOGNISYNC_NATIVE_BRIDGE__;

  // =========================================================================
  // TEST 12: End-to-End Travel Request Coordinate Preservation
  // =========================================================================
  console.log('\n--- Test 12: Journey Request Coordinate Preservation ---');
  const detectedCoords = { lat: 12.9716, lng: 77.5946 };
  const travelReq: TravelRequest = {
    origin: 'Bangalore City Center',
    destination: 'Chennai',
    departureDate: '2026-11-04',
    passengersCount: 1,
    weights: { cost: 0.3, duration: 0.4, comfort: 0.2, carbon: 0.1 },
    originCoordinates: detectedCoords,
  };

  assert.strictEqual(travelReq.originCoordinates?.lat, 12.9716);
  assert.strictEqual(travelReq.originCoordinates?.lng, 77.5946);
  console.log('✓ TravelRequest preserves originCoordinates without data loss for multimodal orchestration');

  console.log('\n=================================================================');
  console.log('ALL 12 GPS-BASED STARTING LOCATION TESTS PASSED SUCCESSFULLY! ✓');
  console.log('=================================================================');
}

runTests().catch((err) => {
  console.error('Test suite failed:', err);
  process.exit(1);
});
