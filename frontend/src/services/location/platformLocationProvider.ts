/**
 * frontend/src/services/location/platformLocationProvider.ts
 *
 * Platform location adapters for web and native mobile environments (M3.4).
 * Enhanced with:
 * - Secure context validation (window.isSecureContext)
 * - Differentiated OS vs Browser permission denial detection
 * - Automatic low-accuracy network fallback if high-accuracy GPS times out or fails on desktop PCs
 * - Structured development-only diagnostic logging
 */
import {
  Coordinates,
  GeolocationPositionData,
  LocationError,
  LocationErrorCode,
  PlatformLocationProvider,
} from '../../types/location';

export class BrowserLocationProvider implements PlatformLocationProvider {
  readonly id = 'browser_geolocation';
  readonly name = 'Browser Geolocation API';

  isSupported(): boolean {
    return typeof navigator !== 'undefined' && 'geolocation' in navigator;
  }

  isSecureContext(): boolean {
    if (typeof window !== 'undefined' && 'isSecureContext' in window) {
      return Boolean(window.isSecureContext);
    }
    return true; // Fallback for headless/SSR test harnesses
  }

  async checkPermissionStatus(): Promise<PermissionState | 'unsupported'> {
    if (
      typeof navigator !== 'undefined' &&
      'permissions' in navigator &&
      typeof navigator.permissions.query === 'function'
    ) {
      try {
        const status = await navigator.permissions.query({ name: 'geolocation' as PermissionName });
        return status.state;
      } catch {
        return 'unsupported';
      }
    }
    return 'unsupported';
  }

  async getCurrentPosition(options?: PositionOptions): Promise<GeolocationPositionData> {
    if (!this.isSupported()) {
      if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) {
        console.warn('[GPS-DIAGNOSTIC] navigator.geolocation is not available on this platform.');
      }
      throw new LocationError(
        'UNSUPPORTED_PLATFORM',
        'Browser geolocation is not supported in this environment.',
        'Geolocation is not supported by your browser. Please enter your location manually.'
      );
    }

    if (!this.isSecureContext()) {
      if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) {
        console.warn('[GPS-DIAGNOSTIC] Insecure context: window.isSecureContext is false.');
      }
      throw new LocationError(
        'INSECURE_CONTEXT',
        'Geolocation requires a secure context (HTTPS or localhost).',
        'Location detection requires a secure connection (HTTPS or localhost). Please enter your location manually.'
      );
    }

    const initialPermission = await this.checkPermissionStatus();
    if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) {
      console.log(`[GPS-DIAGNOSTIC] Initial navigator permission state: ${initialPermission}`);
    }

    // Attempt 1: High accuracy (hardware GPS / fine Wi-Fi)
    try {
      if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) {
        console.log('[GPS-DIAGNOSTIC] Attempt 1: Requesting high-accuracy GPS position (timeout: 12000ms)...');
      }
      return await this._queryPosition({
        enableHighAccuracy: true,
        timeout: 12000,
        maximumAge: 30000,
        ...options,
      });
    } catch (err: any) {
      // If user explicitly denied browser permission, do not retry
      if (err instanceof LocationError && (err.code === 'PERMISSION_DENIED' || err.code === 'OS_PERMISSION_DENIED')) {
        throw err;
      }

      if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) {
        console.warn('[GPS-DIAGNOSTIC] High-accuracy attempt failed/timed out; falling back to standard network triangulation:', err.message);
      }

      // Attempt 2: Standard/Low accuracy fallback (Wi-Fi BSSID / cellular / IP triangulation)
      try {
        if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) {
          console.log('[GPS-DIAGNOSTIC] Attempt 2: Requesting standard/network position (timeout: 15000ms, maxAge: 5min)...');
        }
        return await this._queryPosition({
          enableHighAccuracy: false,
          timeout: 15000,
          maximumAge: 300000, // Up to 5 minutes cached position
        });
      } catch (fallbackErr: any) {
        if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) {
          console.error('[GPS-DIAGNOSTIC] Standard network fallback also failed:', fallbackErr);
        }
        throw fallbackErr;
      }
    }
  }

  private _queryPosition(options: PositionOptions): Promise<GeolocationPositionData> {
    return new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) {
            console.log(
              `[GPS-DIAGNOSTIC] Success callback: lat=${pos.coords.latitude.toFixed(4)}, lng=${pos.coords.longitude.toFixed(4)}, accuracy=±${Math.round(pos.coords.accuracy)}m, timestamp=${pos.timestamp}`
            );
          }
          const coords: Coordinates = {
            lat: pos.coords.latitude,
            lng: pos.coords.longitude,
          };
          resolve({
            coordinates: coords,
            accuracyMeters: pos.coords.accuracy,
            altitudeMeters: pos.coords.altitude,
            headingDegrees: pos.coords.heading,
            speedMps: pos.coords.speed,
            timestamp: pos.timestamp,
          });
        },
        async (err) => {
          if (typeof import.meta !== 'undefined' && import.meta.env?.DEV) {
            console.warn(`[GPS-DIAGNOSTIC] Geolocation error callback: code=${err.code}, message="${err.message}"`);
          }

          let code: LocationErrorCode = 'POSITION_UNAVAILABLE';
          let userMessage = 'Unable to determine your current location. Please enter it manually.';

          if (err.code === 1) {
            // Check if site permission is granted in browser
            const perm = await this.checkPermissionStatus();
            if (perm === 'granted') {
              code = 'OS_PERMISSION_DENIED';
              userMessage =
                'Browser permission is allowed, but device/Windows location is disabled. Please turn on Location in Windows settings, or enter your starting point manually.';
            } else {
              code = 'PERMISSION_DENIED';
              userMessage =
                'Location access was denied in your browser. Please allow location permissions in your browser bar, or enter your starting point manually.';
            }
          } else if (err.code === 2) {
            code = 'POSITION_UNAVAILABLE';
            userMessage = 'GPS signal is currently unavailable. Please enter your location manually.';
          } else if (err.code === 3) {
            code = 'TIMEOUT';
            userMessage = 'Location detection timed out. Please try again or type your starting city.';
          }

          reject(new LocationError(code, err.message, userMessage));
        },
        options
      );
    });
  }
}

/**
 * Extensible bridge contract for future native mobile wrappers (e.g. Capacitor / React Native).
 * When running in a standard responsive browser, isSupported() returns false cleanly
 * without simulating or faking native device access.
 */
export class NativeLocationBridge implements PlatformLocationProvider {
  readonly id = 'native_bridge';
  readonly name = 'Native Mobile Location Bridge';

  private getNativeBridge(): any {
    if (typeof window !== 'undefined') {
      return (window as any).__KOGNISYNC_NATIVE_BRIDGE__;
    }
    return undefined;
  }

  isSupported(): boolean {
    const bridge = this.getNativeBridge();
    return Boolean(bridge && typeof bridge.getCurrentPosition === 'function');
  }

  async getCurrentPosition(options?: PositionOptions): Promise<GeolocationPositionData> {
    const bridge = this.getNativeBridge();
    if (!bridge || typeof bridge.getCurrentPosition !== 'function') {
      throw new LocationError(
        'UNSUPPORTED_PLATFORM',
        'Native location bridge is not available.',
        'Native location provider is not initialized on this device.'
      );
    }
    return await bridge.getCurrentPosition(options);
  }
}
