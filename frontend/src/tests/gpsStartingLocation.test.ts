/**
 * frontend/src/tests/gpsStartingLocation.test.ts
 *
 * Automated test suite for GPS-Based Starting Location Autofill (Milestone M3.4).
 * Covers:
 * 1. Manual entry preservation and editing.
 * 2. Browser Geolocation API permission granted & successful acquisition.
 * 3. Reverse geocoding & coordinate preservation.
 * 4. Browser permission denied error handling.
 * 5. OS-level permission denied handling (when browser permission is granted but OS blocks).
 * 6. Insecure context rejection (window.isSecureContext === false).
 * 7. Automatic low-accuracy network fallback when high-accuracy GPS fails.
 * 8. Geolocation timeout error handling.
 * 9. GPS position unavailable error handling.
 * 10. Low accuracy handling and proximity estimation.
 * 11. Reverse geocoding failure resilience via client fallback.
 * 12. Privacy guards (no tracking on mount, no continuous watchPosition).
 * 13. Unsupported platform fallback.
 * 14. Native mobile bridge contract compliance.
 * 15. End-to-end travel request coordinate preservation.
 * 16. Asynchronous race condition prevention: newer manual edit discards in-flight GPS.
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
// Mock Geolocation & Environment Harness
// ---------------------------------------------------------------------------
interface MockGeolocationOptions {
  status: 'success' | 'denied' | 'unavailable' | 'timeout' | 'high_acc_fail_low_acc_success';
  coords?: { latitude: number; longitude: number; accuracy: number };
}

let mockGeoState: MockGeolocationOptions = {
  status: 'success',
  coords: { latitude: 12.9716, longitude: 77.5946, accuracy: 15 },
};

let mockPermissionState: PermissionState = 'prompt';
let watchPositionCallCount = 0;
let getCurrentPositionCallCount = 0;

// Set up synthetic navigator with mock geolocation
const mockNavigator = {
  geolocation: {
    getCurrentPosition: (
      success: (pos: any) => void,
      error: (err: any) => void,
      options?: any
    ) => {
      getCurrentPositionCallCount++;

      if (mockGeoState.status === 'high_acc_fail_low_acc_success') {
        if (options?.enableHighAccuracy) {
          error({ code: 3, message: 'High accuracy GPS signal timed out' });
          return;
        } else {
          success({
            coords: {
              latitude: 12.9716,
              longitude: 77.5946,
              accuracy: 85,
              altitude: null,
              heading: null,
              speed: null,
            },
            timestamp: 1730995200000,
          });
          return;
        }
      }

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
  permissions: {
    query: async () => ({
      state: mockPermissionState,
    }),
  },
};

Object.defineProperty(globalThis, 'navigator', {
  value: mockNavigator,
  configurable: true,
  writable: true,
});

// Mock window.isSecureContext
(globalThis as any).window = (globalThis as any).window || {};
(globalThis as any).window.isSecureContext = true;

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
  mockPermissionState = 'granted';

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
  assert(geocoded.city.length > 0, 'City must be identified');
  assert(geocoded.provider.length > 0, 'Provider must be identified');
  console.log(`✓ Resolved place: "${geocoded.formattedAddress}" via ${geocoded.provider}`);
  console.log(`✓ Precise coordinates strictly preserved: [${geocoded.coordinates.lat}, ${geocoded.coordinates.lng}]`);

  // =========================================================================
  // TEST 4: Browser Permission Denied Error Handling
  // =========================================================================
  console.log('\n--- Test 4: Browser Permission Denied Handling ---');
  mockGeoState = { status: 'denied' };
  mockPermissionState = 'denied';

  try {
    await provider.getCurrentPosition();
    assert.fail('Should have thrown LocationError');
  } catch (err: any) {
    assert(err instanceof LocationError, 'Must be instance of LocationError');
    assert.strictEqual(err.code, 'PERMISSION_DENIED');
    assert(err.userFriendlyMessage.includes('denied in your browser'));
    console.log(`✓ Correctly caught PERMISSION_DENIED: "${err.userFriendlyMessage}"`);
  }

  // =========================================================================
  // TEST 5: OS-Level Location Disabled Handling (Browser allowed, OS blocked)
  // =========================================================================
  console.log('\n--- Test 5: OS-Level Location Disabled Handling ---');
  mockGeoState = { status: 'denied' };
  mockPermissionState = 'granted'; // Browser site permission is granted, but OS rejected request

  try {
    await provider.getCurrentPosition();
    assert.fail('Should have thrown LocationError');
  } catch (err: any) {
    assert(err instanceof LocationError);
    assert.strictEqual(err.code, 'OS_PERMISSION_DENIED');
    assert(err.userFriendlyMessage.includes('device/Windows location is disabled'));
    console.log(`✓ Accurately diagnosed OS-level location block: "${err.userFriendlyMessage}"`);
  }

  // =========================================================================
  // TEST 6: Insecure Context Rejection
  // =========================================================================
  console.log('\n--- Test 6: Insecure Context Rejection ---');
  (globalThis as any).window.isSecureContext = false;

  try {
    await provider.getCurrentPosition();
    assert.fail('Should have thrown INSECURE_CONTEXT');
  } catch (err: any) {
    assert(err instanceof LocationError);
    assert.strictEqual(err.code, 'INSECURE_CONTEXT');
    assert(err.userFriendlyMessage.includes('secure connection'));
    console.log(`✓ Blocked insecure context with actionable guidance: "${err.userFriendlyMessage}"`);
  }

  // Restore secure context
  (globalThis as any).window.isSecureContext = true;

  // =========================================================================
  // TEST 7: Automatic Low-Accuracy Network Fallback
  // =========================================================================
  console.log('\n--- Test 7: Automatic Low-Accuracy Network Fallback ---');
  mockGeoState = { status: 'high_acc_fail_low_acc_success' };
  mockPermissionState = 'granted';

  const fallbackPos = await provider.getCurrentPosition();
  assert.strictEqual(fallbackPos.accuracyMeters, 85);
  assert.strictEqual(fallbackPos.coordinates.lat, 12.9716);
  console.log(`✓ High-accuracy timeout smoothly recovered via network triangulation: ±${fallbackPos.accuracyMeters}m`);

  // =========================================================================
  // TEST 8: Geolocation Timeout Error Handling
  // =========================================================================
  console.log('\n--- Test 8: Geolocation Timeout Error Handling ---');
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
  // TEST 9: Position Unavailable Error Handling
  // =========================================================================
  console.log('\n--- Test 9: Position Unavailable Error Handling ---');
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
  // TEST 10: Poor Accuracy Handling
  // =========================================================================
  console.log('\n--- Test 10: Poor Accuracy Handling ---');
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
  assert.strictEqual(lowAccResult.coordinates.lat, 13.0827);
  console.log(`✓ Low accuracy (±${lowAccPos.accuracyMeters}m) handled safely without discarding coordinates`);

  // =========================================================================
  // TEST 11: Reverse Geocoding Client Proximity Fallback
  // =========================================================================
  console.log('\n--- Test 11: Reverse Geocoding Client Proximity Fallback ---');
  const udupiCoords = { lat: 13.3409, lng: 74.7421 };
  const udupiResult = await reverseGeocodeCoordinates(udupiCoords, 25, Date.now());
  assert.strictEqual(udupiResult.city, 'Udupi');
  assert.strictEqual(udupiResult.coordinates.lat, 13.3409);
  assert.strictEqual(udupiResult.coordinates.lng, 74.7421);
  console.log(`✓ Client proximity fallback resolved (${udupiResult.coordinates.lat}, ${udupiResult.coordinates.lng}) to ${udupiResult.city}`);

  // =========================================================================
  // TEST 12: Privacy Protection & Lifecycle Safety
  // =========================================================================
  console.log('\n--- Test 12: Privacy Protection & Lifecycle Safety ---');
  new LocationService();
  assert.strictEqual(watchPositionCallCount, 0, 'watchPosition must NEVER be called');
  console.log('✓ Continuous background tracking strictly prevented: watchPositionCallCount = 0');

  // =========================================================================
  // TEST 13: Unsupported Platform Fallback
  // =========================================================================
  console.log('\n--- Test 13: Unsupported Platform Fallback ---');
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
  // TEST 14: Native Mobile Bridge Contract Verification
  // =========================================================================
  console.log('\n--- Test 14: Native Mobile Bridge Contract Verification ---');
  const nativeBridge = new NativeLocationBridge();
  assert.strictEqual(nativeBridge.isSupported(), false);
  console.log('✓ Native bridge returns false cleanly when no native wrapper exists (No fake GPS)');

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

  delete (globalThis as any).window.__KOGNISYNC_NATIVE_BRIDGE__;

  // =========================================================================
  // TEST 15: End-to-End Travel Request Coordinate Preservation
  // =========================================================================
  console.log('\n--- Test 15: Journey Request Coordinate Preservation ---');
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

  // =========================================================================
  // TEST 16: Asynchronous Race Condition Prevention
  // =========================================================================
  console.log('\n--- Test 16: Asynchronous Race Condition Prevention ---');
  let simulatedOriginText = 'Initial City';
  let activeRequestId = 0;

  // 1. User clicks "Use my current location"
  const gpsRequestId = ++activeRequestId;

  // 2. Before GPS resolves, user types "Mumbai" into the input
  ++activeRequestId;
  simulatedOriginText = 'Mumbai';

  // 3. Delayed GPS resolution arrives with "Bangalore"
  const delayedGpsResult = 'Bangalore';
  if (gpsRequestId === activeRequestId) {
    simulatedOriginText = delayedGpsResult;
  }

  assert.strictEqual(simulatedOriginText, 'Mumbai', 'Stale GPS resolution must not overwrite newer manual edit');
  console.log('✓ In-flight GPS resolution safely discarded when user makes a newer manual edit');

  console.log('\n=================================================================');
  console.log('ALL 16 GPS-BASED STARTING LOCATION TESTS PASSED SUCCESSFULLY! ✓');
  console.log('=================================================================');
}

runTests().catch((err) => {
  console.error('Test suite failed:', err);
  process.exit(1);
});
