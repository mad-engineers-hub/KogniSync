import type { LocationGuidanceState, LocationGuidanceStatus } from '../../types/navigation';
import type { RouteCoordinate } from '../../types/route';

let activeWatchId: number | null = null;

/**
 * Starts foreground-only GPS tracking.
 * Requires explicit user initiation. Never executes in the background.
 */
export function startForegroundLocationTracking(
  onUpdate: (state: LocationGuidanceState) => void
): () => void {
  // If already watching, stop previous watch
  stopForegroundLocationTracking();

  if (typeof window === 'undefined' || !navigator || !navigator.geolocation) {
    onUpdate({
      status: 'unavailable',
      errorMessage: 'Geolocation is not supported by your browser.',
    });
    return () => {};
  }

  onUpdate({
    status: 'requesting',
  });

  try {
    activeWatchId = navigator.geolocation.watchPosition(
      (pos: GeolocationPosition) => {
        onUpdate({
          status: 'live_position',
          coords: {
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
          },
          accuracyMeters: Math.round(pos.coords.accuracy),
          heading: pos.coords.heading,
          speed: pos.coords.speed,
          lastUpdatedAt: new Date().toISOString(),
        });
      },
      (err: GeolocationPositionError) => {
        let status: LocationGuidanceStatus = 'error';
        let msg = 'Could not determine location.';

        if (err.code === err.PERMISSION_DENIED) {
          status = 'permission_denied';
          msg = 'Location permission was denied in browser settings.';
        } else if (err.code === err.POSITION_UNAVAILABLE) {
          status = 'unavailable';
          msg = 'Device position is currently unavailable.';
        } else if (err.code === err.TIMEOUT) {
          status = 'unavailable';
          msg = 'Location request timed out.';
        }

        onUpdate({
          status,
          errorMessage: msg,
        });
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 5000,
      }
    );
  } catch (exc) {
    onUpdate({
      status: 'error',
      errorMessage: `Could not initialize location watch: ${exc}`,
    });
  }

  // Return teardown function that stops tracking immediately
  return () => {
    stopForegroundLocationTracking();
  };
}

/**
 * Stops any active foreground GPS tracking immediately.
 */
export function stopForegroundLocationTracking(): void {
  if (activeWatchId !== null && typeof navigator !== 'undefined' && navigator.geolocation) {
    try {
      navigator.geolocation.clearWatch(activeWatchId);
    } catch {
      // Ignore teardown errors
    }
    activeWatchId = null;
  }
}

/**
 * Returns whether foreground tracking is currently active.
 */
export function isForegroundTrackingActive(): boolean {
  return activeWatchId !== null;
}

/**
 * Creates a clearly labeled simulated demo position for testing/walkthrough.
 * Never masquerades as a live GPS fix.
 */
export function createDemoPosition(
  coords: RouteCoordinate,
  accuracyMeters = 15
): LocationGuidanceState {
  return {
    status: 'demo_position',
    coords,
    accuracyMeters,
    heading: null,
    speed: null,
    lastUpdatedAt: new Date().toISOString(),
  };
}

