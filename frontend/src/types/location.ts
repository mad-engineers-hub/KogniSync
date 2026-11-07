/**
 * frontend/src/types/location.ts
 *
 * Typed contracts for GPS-based location detection, reverse geocoding,
 * and error handling (Milestone M3.4).
 */

export interface Coordinates {
  lat: number;
  lng: number;
}

export interface GeolocationPositionData {
  coordinates: Coordinates;
  accuracyMeters: number;
  altitudeMeters?: number | null;
  headingDegrees?: number | null;
  speedMps?: number | null;
  timestamp: number;
}

export type LocationErrorCode =
  | 'PERMISSION_DENIED'
  | 'OS_PERMISSION_DENIED'
  | 'POSITION_UNAVAILABLE'
  | 'TIMEOUT'
  | 'INSECURE_CONTEXT'
  | 'UNSUPPORTED_PLATFORM'
  | 'POOR_ACCURACY'
  | 'REVERSE_GEOCODING_FAILED'
  | 'NETWORK_ERROR';

export class LocationError extends Error {
  code: LocationErrorCode;
  userFriendlyMessage: string;

  constructor(code: LocationErrorCode, message: string, userFriendlyMessage?: string) {
    super(message);
    this.name = 'LocationError';
    this.code = code;
    this.userFriendlyMessage = userFriendlyMessage || message;
  }
}

export interface LocationResult {
  coordinates: Coordinates;
  accuracyMeters: number;
  timestamp: number;
  formattedAddress: string;
  locality?: string;
  city: string;
  state?: string;
  country?: string;
  provider: string;
  attribution?: string;
  isEstimate: boolean;
}

export interface PlatformLocationProvider {
  readonly id: string;
  readonly name: string;
  isSupported(): boolean;
  getCurrentPosition(options?: PositionOptions): Promise<GeolocationPositionData>;
}

