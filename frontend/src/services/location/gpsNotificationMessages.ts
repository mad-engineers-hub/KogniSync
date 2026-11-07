/**
 * frontend/src/services/location/gpsNotificationMessages.ts
 *
 * Canonical notification strings for GPS-based location detection (Milestone M3.4.1).
 * Standardized across web and responsive mobile platforms.
 */

export const GPS_NOTIFICATION_MESSAGES = {
  SUCCESS: 'Your current location has been detected and added as your starting point.',
  OS_LOCATION_DISABLED: 'Device location is turned off. Enable Location services in Windows Settings.',
  BROWSER_PERMISSION_DENIED: 'Location access is blocked. Allow location permission in your browser settings.',
  TIMEOUT: 'Location detection timed out. Please try again.',
  POSITION_UNAVAILABLE: 'Your device could not provide a location. Check your location settings and retry.',
  INSECURE_CONTEXT: 'Location detection requires a secure connection (HTTPS or localhost).',
  REVERSE_GEOCODING_FAILURE: 'Coordinates received, but the place name could not be resolved. You can enter your starting point manually.',
  POOR_ACCURACY: 'Location detected, but accuracy is limited. Please verify your starting point.',
} as const;

export type GPSNotificationKey = keyof typeof GPS_NOTIFICATION_MESSAGES;
