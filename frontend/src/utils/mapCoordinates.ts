/**
 * Utility functions for Leaflet and GeoJSON coordinate normalization,
 * flexible polyline decoding, and map styling.
 */

export const DEFAULT_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
export const DEFAULT_TILE_SUBDOMAINS = '';
export const DEFAULT_TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors';

// Mode color palette
export const MODE_COLORS: Record<string, { stroke: string; glow: string; weight: number; dashArray?: string; label: string }> = {
  walk: { stroke: '#059669', glow: '#34d399', weight: 4, dashArray: '4, 8', label: 'Walk' },
  cab: { stroke: '#2563eb', glow: '#60a5fa', weight: 5, label: 'SyncCab' },
  auto: { stroke: '#2563eb', glow: '#60a5fa', weight: 5, label: 'Auto' },
  rapido: { stroke: '#7c3aed', glow: '#a78bfa', weight: 5, label: 'Rapido Bike' },
  bus: { stroke: '#d97706', glow: '#fbbf24', weight: 5, label: 'Bus' },
  train: { stroke: '#312e81', glow: '#6366f1', weight: 6, dashArray: '10, 5', label: 'Indian Railways' },
  flight: { stroke: '#4f46e5', glow: '#818cf8', weight: 4, dashArray: '6, 8', label: 'Flight' },
  metro: { stroke: '#0d9488', glow: '#2dd4bf', weight: 5, label: 'Metro Rail' },
  shuttle: { stroke: '#059669', glow: '#34d399', weight: 5, label: 'EV Feeder Shuttle' },
};

export function getModeStyle(mode: string) {
  return MODE_COLORS[mode] || { stroke: '#2563eb', glow: '#60a5fa', weight: 5, label: mode };
}

/**
 * Decodes Google/Valhalla encoded polyline string (precision 5 or 6) into [lat, lng] array.
 */
export function decodePolyline(str: string, precision = 5): [number, number][] {
  let index = 0;
  let lat = 0;
  let lng = 0;
  const coordinates: [number, number][] = [];
  const factor = Math.pow(10, precision);

  while (index < str.length) {
    let byte = null;
    let shift = 0;
    let result = 0;

    do {
      byte = str.charCodeAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);

    const deltaLat = (result & 1) !== 0 ? ~(result >> 1) : result >> 1;
    lat += deltaLat;

    shift = 0;
    result = 0;

    do {
      byte = str.charCodeAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);

    const deltaLng = (result & 1) !== 0 ? ~(result >> 1) : result >> 1;
    lng += deltaLng;

    coordinates.push([lat / factor, lng / factor]);
  }

  return coordinates;
}

/**
 * Normalizes coordinate pairs for Leaflet [latitude, longitude].
 * Safeguards against:
 * 1. GeoJSON [longitude, latitude] vs Leaflet [latitude, longitude] ordering.
 * 2. Swapped / inverted Indian subcontinent coordinates (lat ~6-38°N, lng ~68-98°E).
 * 3. NaN, undefined, null, or out-of-world coordinates.
 */
export function normalizeLeafletCoord(
  c: [number, number] | { lat: number; lng: number } | { latitude: number; longitude: number } | null | undefined,
  isGeoJsonOrder = false
): [number, number] | null {
  if (!c) return null;
  let lat: number;
  let lng: number;

  if (Array.isArray(c)) {
    if (c.length < 2) return null;
    if (isGeoJsonOrder) {
      // GeoJSON standard: [longitude, latitude]
      lng = Number(c[0]);
      lat = Number(c[1]);
    } else {
      // Leaflet default: [latitude, longitude]
      lat = Number(c[0]);
      lng = Number(c[1]);
    }
  } else if ('lat' in c && 'lng' in c) {
    lat = Number(c.lat);
    lng = Number(c.lng);
  } else if ('latitude' in c && 'longitude' in c) {
    lat = Number(c.latitude);
    lng = Number(c.longitude);
  } else {
    return null;
  }

  if (isNaN(lat) || isNaN(lng) || !isFinite(lat) || !isFinite(lng)) {
    return null;
  }

  // Mathematically impossible latitude (|lat| > 90) indicates an inverted [lng, lat] pair
  // when caller omitted isGeoJsonOrder, provided the longitude component is a valid latitude (|lng| <= 90).
  if (Math.abs(lat) > 90 && Math.abs(lat) <= 180 && Math.abs(lng) <= 90) {
    const temp = lat;
    lat = lng;
    lng = temp;
  }

  // Strict world bounds check (latitude [-90, 90], longitude [-180, 180])
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
    return null;
  }

  return [lat, lng];
}

