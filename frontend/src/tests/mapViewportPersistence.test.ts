/**
 * frontend/src/tests/mapViewportPersistence.test.ts
 *
 * Viewport Persistence & Intentional Fit Test Suite (M4.1).
 *
 * Verifies the 16 strict viewport persistence invariants:
 * 1.  Initial map load fits journey bounds (fitBoundsCallCount === 1).
 * 2.  User zoom survives a React re-render (custom zoom level retained, fitBounds not called).
 * 3.  User pan survives a React re-render (custom center retained, fitBounds not called).
 * 4.  Background journey-data refresh does not reset zoom.
 * 5.  Marker updates do not reset zoom.
 * 6.  Route geometry updates for the same journey do not reset zoom.
 * 7.  ResizeObserver / invalidateSize() does not reset zoom or geographic bounds.
 * 8.  Selecting a different journey triggers one intentional viewport fit (fitBoundsCallCount === 2).
 * 9.  Explicit Reset/Fit Route action works (handleFitRoute triggers fit and resets hasUserAdjustedViewport).
 * 10. Repeated renders do not cause repeated viewport fitting (fitBoundsCallCount remains unchanged).
 * 11. Changing journey object references without changing journey identity does not trigger fitting.
 * 12. Map instance is not unnecessarily recreated (and clean unmount/reset behavior).
 * 13. Programmatic movement lifecycle: moveend prompt clearing and user drag animation override.
 * 14. Programmatic motion suppression: internal movestart/zoomstart during fit do not misclassify as user interaction.
 * 15. Journey switching sequence (A -> B -> A) under default 'fresh_framing' corridor policy.
 * 16. Journey switching sequence (A -> B -> A) under opt-in 'restore_saved' custom viewport policy.
 */

import assert from 'node:assert';
import {
  MapViewportManager,
  type MapViewportTarget,
  type ViewportSnapshot,
} from '../utils/mapViewportManager';
import {
  composeMultiModalJourneys,
} from '../api/orchestrationEngine';
import type { TravelRequest, Journey } from '../types/journey';

console.log('=================================================================');
console.log('RUNNING MAP VIEWPORT PERSISTENCE & INTENTIONAL FIT TEST SUITE');
console.log('=================================================================');

// ----------------------------------------------------------------------------
// Mock Leaflet Map Implementation
// ----------------------------------------------------------------------------
class MockLeafletMap implements MapViewportTarget {
  public fitBoundsCalls: { bounds: any; options?: any }[] = [];
  public invalidateSizeCalls: { options?: any }[] = [];
  public stopCalls: number = 0;
  public zoom: number = 10;
  public center: [number, number] = [12.9716, 77.5946];
  public listeners: Record<string, ((...args: any[]) => void)[]> = {};
  public isRemoved: boolean = false;

  public fitBounds(bounds: any, options?: any): void {
    this.fitBoundsCalls.push({ bounds, options });
  }

  public invalidateSize(options?: { pan?: boolean; debounceMoveend?: boolean }): void {
    this.invalidateSizeCalls.push({ options });
  }

  public stop(): void {
    this.stopCalls++;
  }

  public zoomIn(delta: number = 1): void {
    this.zoom += delta;
    this.fire('zoomstart');
  }

  public zoomOut(delta: number = 1): void {
    this.zoom -= delta;
    this.fire('zoomstart');
  }

  public setView(center: [number, number], zoom?: number, _options?: any): void {
    this.center = center;
    if (typeof zoom === 'number') this.zoom = zoom;
    this.fire('movestart');
  }

  public getZoom(): number {
    return this.zoom;
  }

  public getCenter(): [number, number] {
    return this.center;
  }

  public on(event: string, fn: (...args: any[]) => void): void {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(fn);
  }

  public off(event: string, fn: (...args: any[]) => void): void {
    if (!this.listeners[event]) return;
    this.listeners[event] = this.listeners[event].filter((f) => f !== fn);
  }

  public fire(event: string, ...args: any[]): void {
    const list = this.listeners[event] || [];
    for (const fn of list) {
      fn(...args);
    }
  }

  public remove(): void {
    this.isRemoved = true;
    this.listeners = {};
  }
}

// ----------------------------------------------------------------------------
// Test Data Preparation
// ----------------------------------------------------------------------------
const blrCbeReq: TravelRequest = {
  origin: 'Bangalore',
  destination: 'Coimbatore',
  departureDate: '2026-11-25',
  passengersCount: 1,
  weights: { cost: 0.5, duration: 0.25, comfort: 0.15, carbon: 0.1 },
};
const blrCbeJourneys = composeMultiModalJourneys(blrCbeReq);
assert(blrCbeJourneys.length >= 2, 'Must produce at least 2 journeys for testing');

const journeyA: Journey = blrCbeJourneys[0];
const journeyB: Journey = blrCbeJourneys[1];

const pointsJourneyA: [number, number][] = [
  [journeyA.origin.coordinates.lat, journeyA.origin.coordinates.lng],
  ...journeyA.segments.map((s): [number, number] => [s.destination.coordinates.lat, s.destination.coordinates.lng]),
];

const pointsJourneyB: [number, number][] = [
  [journeyB.origin.coordinates.lat, journeyB.origin.coordinates.lng],
  ...journeyB.segments.map((s): [number, number] => [s.destination.coordinates.lat, s.destination.coordinates.lng]),
];

// Initialize Manager and Map
const manager = new MapViewportManager();
const mockMap = new MockLeafletMap();
manager.attachMap(mockMap);

// ============================================================================
// TEST 1: Initial map load fits journey bounds (fitBoundsCallCount === 1)
// ============================================================================
console.log('\n--- Test 1: Initial Map Load Viewport Fitting ---');
{
  const didFit = manager.onJourneyRender(journeyA.id, pointsJourneyA, mockMap, false);
  assert.strictEqual(didFit, true, 'Initial render of journeyA must trigger fitBounds');
  assert.strictEqual(mockMap.fitBoundsCalls.length, 1, 'fitBounds must be called exactly once');

  const snapshot: ViewportSnapshot = manager.getSnapshot(journeyA.id);
  assert.strictEqual(snapshot.fitBoundsCallCount, 1, 'fitBoundsCallCount must equal 1');
  assert.strictEqual(snapshot.autoFitCallCount, 1, 'autoFitCallCount must equal 1');
  assert.strictEqual(snapshot.explicitFitCallCount, 0, 'explicitFitCallCount must equal 0 on initial load');
  assert.strictEqual(snapshot.lastFittedJourneyId, journeyA.id, 'lastFittedJourneyId must be journeyA.id');
  assert.strictEqual(snapshot.hasUserAdjustedViewport, false, 'hasUserAdjustedViewport must be false on initial fit');

  // Verify bounding box coordinates match points JourneyA
  const fittedBounds = mockMap.fitBoundsCalls[0].bounds;
  const lats = pointsJourneyA.map((p) => p[0]);
  const lngs = pointsJourneyA.map((p) => p[1]);
  const expectedMinLat = Math.min(...lats);
  const expectedMaxLat = Math.max(...lats);
  const expectedMinLng = Math.min(...lngs);
  const expectedMaxLng = Math.max(...lngs);

  assert.strictEqual(fittedBounds[0][0], expectedMinLat, 'Min lat in bounds must match');
  assert.strictEqual(fittedBounds[1][0], expectedMaxLat, 'Max lat in bounds must match');
  assert.strictEqual(fittedBounds[0][1], expectedMinLng, 'Min lng in bounds must match');
  assert.strictEqual(fittedBounds[1][1], expectedMaxLng, 'Max lng in bounds must match');

  console.log('✓ Initial map load executed exactly one intentional fitBounds for journeyA.');
}

manager.clearProgrammaticFitting();

// ============================================================================
// TEST 2: User zoom survives a React re-render
// ============================================================================
console.log('\n--- Test 2: User Zoom Survives Component Re-render ---');
{
  // User zooms in via control
  manager.onUserZoom(mockMap, 'in');
  assert.strictEqual(mockMap.getZoom(), 11, 'Mock map zoom must increase to 11');
  assert.strictEqual(manager.getSnapshot().hasUserAdjustedViewport, true, 'hasUserAdjustedViewport must be true');

  // React component re-renders with the same journey
  const didFitOnRerender = manager.onJourneyRender(journeyA.id, pointsJourneyA, mockMap, true);
  assert.strictEqual(didFitOnRerender, false, 'Re-render of same journey must NOT fitBounds');
  assert.strictEqual(mockMap.fitBoundsCalls.length, 1, 'fitBounds call count must remain 1');
  assert.strictEqual(mockMap.getZoom(), 11, 'User zoom level 11 must be preserved');
  console.log('✓ User zoom level 11 preserved across React component re-render.');
}

// ============================================================================
// TEST 3: User pan survives a React re-render
// ============================================================================
console.log('\n--- Test 3: User Pan Survives Component Re-render ---');
{
  // User pans map to custom center
  const customCenter: [number, number] = [12.5000, 77.2000];
  manager.onUserRecenter(mockMap, customCenter[0], customCenter[1], 12);
  assert.deepStrictEqual(mockMap.getCenter(), customCenter, 'Map center must update to user pan location');
  assert.strictEqual(mockMap.getZoom(), 12, 'Map zoom must update to 12');

  // React component re-renders
  const didFitOnRerender = manager.onJourneyRender(journeyA.id, pointsJourneyA, mockMap, true);
  assert.strictEqual(didFitOnRerender, false, 'Re-render must NOT fitBounds');
  assert.strictEqual(mockMap.fitBoundsCalls.length, 1, 'fitBounds must NOT be called');
  assert.deepStrictEqual(mockMap.getCenter(), customCenter, 'User pan center must be preserved');
  console.log('✓ User pan coordinates preserved across component re-render.');
}

// ============================================================================
// TEST 4: Background journey-data refresh does not reset zoom
// ============================================================================
console.log('\n--- Test 4: Background Data Refresh Does Not Reset Zoom ---');
{
  // Simulate live transit polling updating journeyA duration/delay/price
  const updatedJourneyA: Journey = {
    ...journeyA,
    totalDurationMinutes: journeyA.totalDurationMinutes + 15,
    totalPrice: journeyA.totalPrice + 50,
  };

  const didFit = manager.onJourneyRender(updatedJourneyA.id, pointsJourneyA, mockMap, true);
  assert.strictEqual(didFit, false, 'Data polling for same journey identity must not fitBounds');
  assert.strictEqual(mockMap.fitBoundsCalls.length, 1, 'fitBounds count remains 1');
  assert.strictEqual(mockMap.getZoom(), 12, 'Zoom remains 12');
  console.log('✓ Background polling refresh preserved user viewport without resetting zoom.');
}

// ============================================================================
// TEST 5: Marker updates do not reset zoom
// ============================================================================
console.log('\n--- Test 5: Marker Updates Do Not Reset Zoom ---');
{
  // User clicks segment 1 (effectiveActiveSegmentIndex = 1), causing marker highlight re-render
  const didFit = manager.onJourneyRender(journeyA.id, pointsJourneyA, mockMap, true);
  assert.strictEqual(didFit, false, 'Marker update must not fitBounds');
  assert.strictEqual(mockMap.fitBoundsCalls.length, 1, 'fitBounds count remains 1');
  assert.strictEqual(mockMap.getZoom(), 12, 'Zoom remains 12');
  console.log('✓ Active segment marker click preserved user viewport.');
}

// ============================================================================
// TEST 6: Route geometry updates for the same journey do not reset zoom
// ============================================================================
console.log('\n--- Test 6: Route Geometry Enrichment Does Not Reset Zoom ---');
{
  // Dense polyline points arrive asynchronously from Valhalla for journeyA
  const densePoints: [number, number][] = [
    ...pointsJourneyA,
    [12.8, 77.4],
    [12.6, 77.3],
    [12.2, 77.1],
    [11.5, 77.0],
  ];

  const didFit = manager.onJourneyRender(journeyA.id, densePoints, mockMap, true);
  assert.strictEqual(didFit, false, 'Route geometry arrival for same journey must not fitBounds');
  assert.strictEqual(mockMap.fitBoundsCalls.length, 1, 'fitBounds count remains 1');
  assert.strictEqual(mockMap.getZoom(), 12, 'Zoom remains 12');
  console.log('✓ Async Valhalla route geometry enrichment preserved user zoom.');
}

// ============================================================================
// TEST 7: ResizeObserver / invalidateSize() does not reset zoom or bounds
// ============================================================================
console.log('\n--- Test 7: Container Resize via ResizeObserver Invalidation ---');
{
  const prevFitCalls = mockMap.fitBoundsCalls.length;
  const prevZoom = mockMap.getZoom();
  const prevCenter = mockMap.getCenter();

  // ResizeObserver fires
  manager.onResize(mockMap);

  assert.strictEqual(mockMap.invalidateSizeCalls.length, 1, 'invalidateSize must be called once');
  assert.deepStrictEqual(
    mockMap.invalidateSizeCalls[0].options,
    { pan: false },
    'invalidateSize must specify { pan: false }'
  );
  assert.strictEqual(mockMap.fitBoundsCalls.length, prevFitCalls, 'fitBounds must NOT be called on resize');
  assert.strictEqual(mockMap.getZoom(), prevZoom, 'Zoom must not change on resize');
  assert.deepStrictEqual(mockMap.getCenter(), prevCenter, 'Center must not change on resize');
  console.log('✓ ResizeObserver called invalidateSize({ pan: false }) without resetting zoom or pan.');
}

// ============================================================================
// TEST 8: Selecting a different journey triggers one intentional viewport fit
// ============================================================================
console.log('\n--- Test 8: Selecting Alternative Journey Triggers One Intentional Fit ---');
{
  assert.notStrictEqual(journeyB.id, journeyA.id, 'journeyB must have different ID than journeyA');

  const didFit = manager.onJourneyRender(journeyB.id, pointsJourneyB, mockMap, true);
  assert.strictEqual(didFit, true, 'Switching to journeyB must trigger fitBounds');
  assert.strictEqual(mockMap.fitBoundsCalls.length, 2, 'Total fitBounds calls must now be 2');

  const snapshot = manager.getSnapshot(journeyB.id);
  assert.strictEqual(snapshot.fitBoundsCallCount, 2, 'fitBoundsCallCount must be 2');
  assert.strictEqual(snapshot.autoFitCallCount, 2, 'autoFitCallCount must be 2');
  assert.strictEqual(snapshot.explicitFitCallCount, 0, 'explicitFitCallCount must be 0 before explicit fit');
  assert.strictEqual(snapshot.lastFittedJourneyId, journeyB.id, 'lastFittedJourneyId must be journeyB.id');
  assert.strictEqual(snapshot.hasUserAdjustedViewport, false, 'hasUserAdjustedViewport must be reset to false for new journey');

  // Verify bounding box for journeyB was fitted
  const boundsB = mockMap.fitBoundsCalls[1].bounds;
  const latsB = pointsJourneyB.map((p) => p[0]);
  const lngsB = pointsJourneyB.map((p) => p[1]);
  assert.strictEqual(boundsB[0][0], Math.min(...latsB), 'Min lat of journeyB must match');
  assert.strictEqual(boundsB[1][0], Math.max(...latsB), 'Max lat of journeyB must match');
  console.log('✓ Selecting alternative journey triggered exactly one intentional fitBounds.');
}

manager.clearProgrammaticFitting();

// ============================================================================
// TEST 9: Explicit Reset/Fit Route action works
// ============================================================================
console.log('\n--- Test 9: Explicit Fit Route Button Clears User Adjusted State ---');
{
  // User zooms in manually on journeyB
  manager.onUserZoom(mockMap, 'in');
  assert.strictEqual(manager.getSnapshot().hasUserAdjustedViewport, true);

  // User clicks "Fit Whole Route" button
  const fullBounds: [[number, number], [number, number]] = [[11.0, 76.5], [13.0, 77.8]];
  const didExplicitFit = manager.onExplicitFitRoute(mockMap, fullBounds);

  assert.strictEqual(didExplicitFit, true, 'onExplicitFitRoute must return true');
  assert.strictEqual(mockMap.fitBoundsCalls.length, 3, 'Total fitBounds calls must now be 3');
  assert.strictEqual(manager.getSnapshot().autoFitCallCount, 2, 'autoFitCallCount must remain 2');
  assert.strictEqual(manager.getSnapshot().explicitFitCallCount, 1, 'explicitFitCallCount must now be 1');
  assert.strictEqual(manager.getSnapshot().fitBoundsCallCount, 3, 'Total fitBoundsCallCount must equal 3');
  assert.strictEqual(manager.getSnapshot().hasUserAdjustedViewport, false, 'hasUserAdjustedViewport must reset to false');
  console.log('✓ Explicit "Fit Whole Route" button successfully fitted bounds and reset user-adjusted state.');
}

manager.clearProgrammaticFitting();

// ============================================================================
// TEST 10: Repeated renders do not cause repeated viewport fitting
// ============================================================================
console.log('\n--- Test 10: Repeated Renders Do Not Trigger Repeated fitBounds ---');
{
  const initialCallCount = mockMap.fitBoundsCalls.length; // 3

  for (let i = 0; i < 15; i++) {
    const didFit = manager.onJourneyRender(journeyB.id, pointsJourneyB, mockMap, true);
    assert.strictEqual(didFit, false, `Render ${i + 1} must not fitBounds`);
  }

  assert.strictEqual(mockMap.fitBoundsCalls.length, initialCallCount, 'fitBounds call count must remain unchanged at 3');
  console.log('✓ 15 rapid re-renders resulted in 0 additional fitBounds calls.');
}

// ============================================================================
// TEST 11: Changing journey object references without changing ID does not trigger fitting
// ============================================================================
console.log('\n--- Test 11: Object Reference Mutation Without ID Change ---');
{
  // Deep clone journey object to create a new object reference in memory
  const clonedJourneyB: Journey = JSON.parse(JSON.stringify(journeyB));
  assert.strictEqual(clonedJourneyB.id, journeyB.id, 'Cloned journey ID must be identical');
  assert.notStrictEqual(clonedJourneyB, journeyB, 'Object reference must be distinct');

  const didFit = manager.onJourneyRender(clonedJourneyB.id, pointsJourneyB, mockMap, true);
  assert.strictEqual(didFit, false, 'New object reference with same ID must not trigger fitting');
  assert.strictEqual(mockMap.fitBoundsCalls.length, 3, 'fitBounds call count must remain 3');
  console.log('✓ Object reference changes with stable journey ID preserve viewport.');
}

// ============================================================================
// TEST 12: Map instance is not unnecessarily recreated and clean reset
// ============================================================================
console.log('\n--- Test 12: Map Instance Retention & Clean Lifecycle Reset ---');
{
  // Attaching same map instance is an idempotent no-op
  manager.attachMap(mockMap);
  assert.strictEqual(manager.getSnapshot().lastFittedJourneyId, journeyB.id, 'State must be retained on duplicate attach');

  // Test map unmount / manager reset
  manager.reset();
  const resetSnapshot = manager.getSnapshot();
  assert.strictEqual(resetSnapshot.lastFittedJourneyId, null, 'lastFittedJourneyId must be reset to null');
  assert.strictEqual(resetSnapshot.fitBoundsCallCount, 0, 'fitBoundsCallCount must be reset to 0');
  assert.strictEqual(resetSnapshot.hasUserAdjustedViewport, false, 'hasUserAdjustedViewport must be false');

  // After reset, re-attaching map allows initial fit again
  const newMockMap = new MockLeafletMap();
  manager.attachMap(newMockMap);
  const didFitAfterReset = manager.onJourneyRender(journeyA.id, pointsJourneyA, newMockMap, false);
  assert.strictEqual(didFitAfterReset, true, 'After reset, new map render triggers initial fitBounds');
  assert.strictEqual(newMockMap.fitBoundsCalls.length, 1, 'New map fitBounds called once');
  console.log('✓ Clean lifecycle unmount/reset and re-initialization verified.');
}

// ============================================================================
// TEST 13: Programmatic Movement Lifecycle & Animation Interruption
// ============================================================================
console.log('\n--- Test 13: Programmatic Movement Lifecycle & Animation Interruption ---');
{
  const lifecycleMap = new MockLeafletMap();
  const lifecycleManager = new MapViewportManager();
  lifecycleManager.attachMap(lifecycleMap);

  // 13.1 Normal animated fit completes and clears lock upon moveend
  lifecycleManager.onJourneyRender('journey-anim-1', pointsJourneyA, lifecycleMap, true);
  assert.strictEqual(lifecycleManager.getSnapshot().isProgrammaticFitting, true, 'isProgrammaticFitting must be true during animation');

  // Leaflet fires moveend when animation finishes
  lifecycleMap.fire('moveend');
  assert.strictEqual(lifecycleManager.getSnapshot().isProgrammaticFitting, false, 'isProgrammaticFitting must be cleared promptly on moveend');
  assert.strictEqual(lifecycleManager.getSnapshot().hasUserAdjustedViewport, false, 'hasUserAdjustedViewport must be false');

  // 13.2 Interrupted animation: User pointer drag during in-flight animation
  lifecycleManager.onJourneyRender('journey-anim-2', pointsJourneyB, lifecycleMap, true);
  assert.strictEqual(lifecycleManager.getSnapshot().isProgrammaticFitting, true);

  const prevStopCalls = lifecycleMap.stopCalls;
  // User physically drags map while animation was running
  lifecycleMap.fire('dragstart');

  assert(lifecycleMap.stopCalls > prevStopCalls, 'map.stop() must be called to halt in-flight animation');
  assert.strictEqual(lifecycleManager.getSnapshot().isProgrammaticFitting, false, 'isProgrammaticFitting must be cleared immediately upon dragstart');
  assert.strictEqual(lifecycleManager.getSnapshot().hasUserAdjustedViewport, true, 'hasUserAdjustedViewport must be set to true on manual drag');

  console.log('✓ Programmatic movement lifecycle: moveend clearing and user drag animation override verified.');
}

// ============================================================================
// TEST 14: Programmatic Motion Event Suppression
// ============================================================================
console.log('\n--- Test 14: Programmatic Motion Event Suppression ---');
{
  const testMap = new MockLeafletMap();
  const testManager = new MapViewportManager();
  testManager.attachMap(testMap);

  testManager.onJourneyRender('journey-suppress-1', pointsJourneyA, testMap, true);
  assert.strictEqual(testManager.getSnapshot().isProgrammaticFitting, true);

  // During fitBounds, Leaflet emits internal movestart and zoomstart
  testMap.fire('movestart');
  testMap.fire('zoomstart');

  assert.strictEqual(
    testManager.getSnapshot().hasUserAdjustedViewport,
    false,
    'Internal programmatic movestart/zoomstart must NOT set hasUserAdjustedViewport to true'
  );

  // When animation finishes, moveend fires
  testMap.fire('moveend');
  assert.strictEqual(testManager.getSnapshot().isProgrammaticFitting, false);

  // After animation finishes, a genuine user zoom IS detected
  testMap.fire('zoomstart');
  assert.strictEqual(
    testManager.getSnapshot().hasUserAdjustedViewport,
    true,
    'Genuine user zoom after animation MUST be detected'
  );

  console.log('✓ Programmatic motion suppression and post-animation user interaction verified.');
}

// ============================================================================
// TEST 15: Journey Switching Sequence (A -> B -> A) under Default 'fresh_framing'
// ============================================================================
console.log('\n--- Test 15: Journey Switching Sequence (A -> B -> A) Under Default "fresh_framing" Policy ---');
{
  const switchMap = new MockLeafletMap();
  const switchManager = new MapViewportManager({ switchPolicy: 'fresh_framing' });
  switchManager.attachMap(switchMap);

  // 1. Load Journey A
  switchManager.onJourneyRender(journeyA.id, pointsJourneyA, switchMap, false);
  assert.strictEqual(switchMap.fitBoundsCalls.length, 1, 'Step 1: Fit Journey A');
  assert.strictEqual(switchManager.getSnapshot().hasUserAdjustedViewport, false);

  // 2. User manually zooms and pans on Journey A
  switchManager.onUserZoom(switchMap, 'in');
  switchManager.onUserRecenter(switchMap, 13.0, 77.5, 14);
  assert.strictEqual(switchManager.getSnapshot().hasUserAdjustedViewport, true, 'Step 2: User adjusted Journey A');

  // 3. User selects Journey B
  switchManager.onJourneyRender(journeyB.id, pointsJourneyB, switchMap, true);
  assert.strictEqual(switchMap.fitBoundsCalls.length, 2, 'Step 3: Fit Journey B');
  assert.strictEqual(switchManager.getSnapshot().lastFittedJourneyId, journeyB.id);
  assert.strictEqual(switchManager.getSnapshot().hasUserAdjustedViewport, false, 'User adjusted flag reset for Journey B');

  // 4. User returns to Journey A
  switchManager.onJourneyRender(journeyA.id, pointsJourneyA, switchMap, true);
  assert.strictEqual(switchMap.fitBoundsCalls.length, 3, 'Step 4: Intentionally refit Journey A bounds');
  assert.strictEqual(switchManager.getSnapshot().lastFittedJourneyId, journeyA.id);
  assert.strictEqual(switchManager.getSnapshot().hasUserAdjustedViewport, false, 'User adjusted flag reset for Journey A fresh framing');

  console.log('✓ Journey switching sequence (A -> B -> A) under default fresh_framing policy verified.');
}

// ============================================================================
// TEST 16: Journey Switching Sequence (A -> B -> A) under 'restore_saved' Policy
// ============================================================================
console.log('\n--- Test 16: Journey Switching Sequence (A -> B -> A) Under "restore_saved" Policy ---');
{
  const restoreMap = new MockLeafletMap();
  const restoreManager = new MapViewportManager({ switchPolicy: 'restore_saved' });
  restoreManager.attachMap(restoreMap);

  // 1. Load Journey A
  restoreManager.onJourneyRender(journeyA.id, pointsJourneyA, restoreMap, false);
  assert.strictEqual(restoreMap.fitBoundsCalls.length, 1, 'Step 1: Fit Journey A');

  // 2. User manually zooms to 14 and pans to [12.85, 77.65] on Journey A
  restoreMap.setView([12.85, 77.65], 14);
  restoreManager.setUserAdjusted(true);

  // 3. User selects Journey B
  restoreManager.onJourneyRender(journeyB.id, pointsJourneyB, restoreMap, true);
  assert.strictEqual(restoreMap.fitBoundsCalls.length, 2, 'Step 3: Fit Journey B');
  assert.strictEqual(restoreManager.getSnapshot().savedViewportsCount, 1, 'Journey A viewport must be saved in cache');

  // 4. User returns to Journey A -> should restore saved viewport, NOT fitBounds
  const prevFitCalls = restoreMap.fitBoundsCalls.length;
  restoreManager.onJourneyRender(journeyA.id, pointsJourneyA, restoreMap, false);

  assert.strictEqual(restoreMap.fitBoundsCalls.length, prevFitCalls, 'Step 4: fitBounds must NOT be called; saved viewport restored');
  assert.deepStrictEqual(restoreMap.getCenter(), [12.85, 77.65], 'Journey A custom center restored');
  assert.strictEqual(restoreMap.getZoom(), 14, 'Journey A custom zoom 14 restored');
  assert.strictEqual(restoreManager.getSnapshot().lastFittedJourneyId, journeyA.id);
  assert.strictEqual(restoreManager.getSnapshot().hasUserAdjustedViewport, true, 'hasUserAdjustedViewport remains true for restored custom view');

  console.log('✓ Journey switching sequence (A -> B -> A) under restore_saved policy verified.');
}

console.log('\n=================================================================');
console.log('ALL 16 MAP VIEWPORT PERSISTENCE INVARIANTS VERIFIED SUCCESSFULLY');
console.log('=================================================================');
