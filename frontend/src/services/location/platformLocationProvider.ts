/**
 * frontend/src/services/location/platformLocationProvider.ts
 *
 * Platform location adapters for web and native mobile environments (M3.4).
 */
import {
  Coordinates,
  GeolocationPositionData,
  LocationError,
  PlatformLocationProvider,
} from '../../types/location';

export class BrowserLocationProvider implements PlatformLocationProvider {
  readonly id = 'browser_geolocation';
  readonly name = 'Browser Geolocation API';

  isSupported(): boolean {
    return typeof navigator !== 'undefined' && 'geolocation' in navigator;
  }

  getCurrentPosition(options?: PositionOptions): Promise<GeolocationPositionData> {
    return new Promise((resolve, reject) => {
      if (!this.isSupported()) {
        return reject(
          new LocationError(
            'UNSUPPORTED_PLATFORM',
            'Browser geolocation is not supported in this environment.',
            'Geolocation is not supported by your browser. Please enter your location manually.'
          )
        );
      }

      const defaultOptions: PositionOptions = {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 60000,
        ...options,
      };

      navigator.geolocation.getCurrentPosition(
        (pos) => {
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
        (err) => {
          let code: 'PERMISSION_DENIED' | 'POSITION_UNAVAILABLE' | 'TIMEOUT' = 'POSITION_UNAVAILABLE';
          let userMessage = 'Unable to determine your current location. Please enter it manually.';

          if (err.code === 1) {
            code = 'PERMISSION_DENIED';
            userMessage =
              'Location permission was denied. Please allow location access in your browser or enter your starting point manually.';
          } else if (err.code === 2) {
            code = 'POSITION_UNAVAILABLE';
            userMessage = 'GPS signal is currently unavailable. Please enter your location manually.';
          } else if (err.code === 3) {
            code = 'TIMEOUT';
            userMessage = 'Location detection timed out. Please try again or type your starting city.';
          }

          reject(new LocationError(code, err.message, userMessage));
        },
        defaultOptions
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

