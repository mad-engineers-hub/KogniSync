/**
 * frontend/src/utils/mapCoordinates.ts
 *
 * Geographic coordinate validation and utilities.
 * Enforces strict boundaries and rejects synthetic Null Island (0,0) fallback coordinates,
 * while preserving valid individual zero values on the Equator or Prime Meridian.
 */

export function isValidCoordinate(
  latOrCoords?:
    | number
    | {
        lat?: number | null;
        lng?: number | null;
        latitude?: number | null;
        longitude?: number | null;
      }
    | null,
  maybeLng?: number | null
): boolean {
  let lat: number | undefined | null;
  let lng: number | undefined | null;

  if (typeof latOrCoords === 'object' && latOrCoords !== null) {
    lat = latOrCoords.lat !== undefined ? latOrCoords.lat : latOrCoords.latitude;
    lng = latOrCoords.lng !== undefined ? latOrCoords.lng : latOrCoords.longitude;
  } else {
    lat = latOrCoords as number | undefined | null;
    lng = maybeLng;
  }

  if (lat === undefined || lat === null || lng === undefined || lng === null) {
    return false;
  }
  if (typeof lat !== 'number' || typeof lng !== 'number') {
    return false;
  }
  if (isNaN(lat) || isNaN(lng) || !isFinite(lat) || !isFinite(lng)) {
    return false;
  }
  // Latitude must be [-90, 90], Longitude must be [-180, 180]
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
    return false;
  }
  // Reject synthetic Null Island fallback pair (0, 0)
  // Individual zeros (e.g. lat: 0, lng: 77.5 on Equator or lat: 51.5, lng: 0 on Prime Meridian) are valid
  if (Math.abs(lat) < 1e-6 && Math.abs(lng) < 1e-6) {
    return false;
  }
  return true;
}
