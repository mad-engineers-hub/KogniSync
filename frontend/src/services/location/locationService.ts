/**
 * frontend/src/services/location/locationService.ts
 *
 * Centralized Location Service for KogniSync (Milestone M3.4).
 * Coordinates platform detection, browser Geolocation API calls,
 * reverse geocoding, and normalized error handling.
 */
import {
  Coordinates,
  LocationError,
  LocationResult,
  PlatformLocationProvider,
} from '../../types/location';
import { BrowserLocationProvider, NativeLocationBridge } from './platformLocationProvider';
import { reverseGeocodeCoordinates } from './reverseGeocoder';

export class LocationService {
  private browserProvider: BrowserLocationProvider;
  private nativeBridge: NativeLocationBridge;

  constructor() {
    this.browserProvider = new BrowserLocationProvider();
    this.nativeBridge = new NativeLocationBridge();
  }

  /**
   * Resolves the active location provider for the current runtime.
   * Prefers native mobile bridge if available, otherwise browser Geolocation API.
   */
  getProvider(): PlatformLocationProvider {
    if (this.nativeBridge.isSupported()) {
      return this.nativeBridge;
    }
    return this.browserProvider;
  }

  /**
   * Checks current permission state without triggering the browser prompt.
   * Returns 'granted' | 'prompt' | 'denied' | 'unsupported'.
   */
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

  /**
   * Obtains current GPS coordinates on explicit user action and reverse-geocodes them.
   * Privacy guarantee: Never runs on page load, never starts background tracking.
   */
  async getCurrentLocation(options?: {
    onProgress?: (message: string) => void;
  }): Promise<LocationResult> {
    const provider = this.getProvider();

    if (!provider.isSupported()) {
      throw new LocationError(
        'UNSUPPORTED_PLATFORM',
        'Geolocation is not supported in this environment.',
        'Location detection is not supported on this device. Please enter your location manually.'
      );
    }

    options?.onProgress?.('Detecting your GPS location...');

    // Single-shot position acquisition
    const position = await provider.getCurrentPosition({
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 60000,
    });

    options?.onProgress?.('Resolving location name...');

    // Reverse geocode acquired coordinates
    const result = await reverseGeocodeCoordinates(
      position.coordinates,
      position.accuracyMeters,
      position.timestamp
    );

    return result;
  }
}

// Global singleton instance
export const locationService = new LocationService();

