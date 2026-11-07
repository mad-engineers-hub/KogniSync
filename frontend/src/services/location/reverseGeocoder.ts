/**
 * frontend/src/services/location/reverseGeocoder.ts
 *
 * Reverse geocoding client for KogniSync (M3.4).
 * Calls the backend /api/v1/location/reverse-geocode endpoint, keeping secrets safe
 * and respecting attribution and rate limits.
 */
import { apiClient } from '../../api/client';
import { Coordinates, LocationError, LocationResult } from '../../types/location';

interface BackendReverseGeocodeResponse {
  formattedAddress: string;
  locality?: string;
  city: string;
  state?: string;
  country?: string;
  coordinates: {
    lat: number;
    lng: number;
  };
  provider: string;
  attribution?: string;
  isEstimate: boolean;
}

// Proximity fallback dictionary for key Indian transportation corridors
const REGIONAL_HUBS: Array<{ city: string; lat: number; lng: number }> = [
  { city: 'Bangalore', lat: 12.9716, lng: 77.5946 },
  { city: 'Chennai', lat: 13.0827, lng: 80.2707 },
  { city: 'Udupi', lat: 13.3409, lng: 74.7421 },
  { city: 'Mangalore', lat: 12.9141, lng: 74.856 },
  { city: 'Goa', lat: 15.2993, lng: 74.124 },
  { city: 'Mumbai', lat: 19.076, lng: 72.8777 },
  { city: 'Delhi', lat: 28.6139, lng: 77.209 },
  { city: 'Hyderabad', lat: 17.385, lng: 78.4867 },
  { city: 'Kochi', lat: 9.9312, lng: 76.2673 },
  { city: 'Jaipur', lat: 26.9124, lng: 75.7873 },
  { city: 'Ahmedabad', lat: 23.0225, lng: 72.5714 },
  { city: 'Mysore', lat: 12.2958, lng: 76.6394 },
];

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const r = 6371.0;
  const dLat = ((lat2 - lat1) * Math.PI) / 180.0;
  const dLon = ((lon2 - lon1) * Math.PI) / 180.0;
  const a =
    Math.sin(dLat / 2.0) ** 2 +
    Math.cos((lat1 * Math.PI) / 180.0) *
      Math.cos((lat2 * Math.PI) / 180.0) *
      Math.sin(dLon / 2.0) ** 2;
  return r * 2.0 * Math.atan2(Math.sqrt(a), Math.sqrt(1.0 - a));
}

export async function reverseGeocodeCoordinates(
  coordinates: Coordinates,
  accuracyMeters: number,
  timestamp: number
): Promise<LocationResult> {
  const { lat, lng } = coordinates;

  // 1. Primary path: query backend reverse geocoding API
  try {
    const data = await apiClient<BackendReverseGeocodeResponse>(
      `/api/v1/location/reverse-geocode?lat=${lat}&lng=${lng}`
    );

    return {
      coordinates: {
        lat: data.coordinates.lat,
        lng: data.coordinates.lng,
      },
      accuracyMeters,
      timestamp,
      formattedAddress: data.formattedAddress,
      locality: data.locality,
      city: data.city,
      state: data.state,
      country: data.country,
      provider: data.provider,
      attribution: data.attribution,
      isEstimate: Boolean(data.isEstimate),
    };
  } catch (err) {
    console.warn('[ReverseGeocoder] Backend reverse-geocode request failed; using client proximity matcher:', err);
  }

  // 2. Client-side spatial proximity fallback (if backend is offline or network fails)
  let nearestCity = 'Custom Location';
  let minDistance = Infinity;

  for (const hub of REGIONAL_HUBS) {
    const dist = haversineKm(lat, lng, hub.lat, hub.lng);
    if (dist < minDistance) {
      minDistance = dist;
      nearestCity = hub.city;
    }
  }

  const isNearby = minDistance <= 35.0;
  const displayAddress = isNearby
    ? `${nearestCity} Area`
    : `${nearestCity} Region (${Math.round(minDistance)} km)`;

  return {
    coordinates,
    accuracyMeters,
    timestamp,
    formattedAddress: displayAddress,
    locality: isNearby ? nearestCity : undefined,
    city: nearestCity,
    country: 'India',
    provider: 'client_proximity_fallback',
    attribution: 'KogniSync Client Geo-Engine',
    isEstimate: true,
  };
}

