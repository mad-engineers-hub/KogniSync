import { apiClient } from './client';
import { Journey, JourneySegment } from '../types/journey';
import { EnrichedJourneyRoute, MapsHealthResponse, SegmentRouteGeometry, RouteCoordinate } from '../types/route';

/**
 * Generates client-side interpolated coordinates between two points for offline / fallback resilience.
 */
function generateClientFallbackCoords(
  p1: { lat: number; lng: number },
  p2: { lat: number; lng: number },
  mode: string
): RouteCoordinate[] {
  const steps = mode === 'flight' ? 16 : 8;
  const coords: RouteCoordinate[] = [{ latitude: p1.lat, longitude: p1.lng }];

  const dx = p2.lng - p1.lng;
  const dy = p2.lat - p1.lat;
  const dist = Math.hypot(dx, dy);

  if (dist < 1e-6) {
    coords.push({ latitude: p2.lat, longitude: p2.lng });
    return coords;
  }

  const perpX = -dy / dist;
  const perpY = dx / dist;
  const curvature = mode === 'flight' ? 0.12 : 0.03;

  for (let i = 1; i < steps; i++) {
    const t = i / steps;
    const arc = 4.0 * t * (1.0 - t);
    const offset = dist * curvature * arc;
    coords.push({
      latitude: Number((p1.lat + t * dy + offset * perpY).toFixed(5)),
      longitude: Number((p1.lng + t * dx + offset * perpX).toFixed(5)),
    });
  }

  coords.push({ latitude: p2.lat, longitude: p2.lng });
  return coords;
}

/**
 * Builds a deterministic local EnrichedJourneyRoute when backend is unavailable.
 */
export function buildClientFallbackRoute(journey: Journey): EnrichedJourneyRoute {
  let totalDistanceMeters = 0;
  let totalDurationSeconds = 0;

  const segments: SegmentRouteGeometry[] = journey.segments.map((seg: JourneySegment) => {
    const distMeters = Math.round((seg.distanceKm || 10) * 1000);
    const durSeconds = Math.round((seg.durationMinutes || 30) * 60);
    totalDistanceMeters += distMeters;
    totalDurationSeconds += durSeconds;

    const coords = generateClientFallbackCoords(
      seg.origin.coordinates,
      seg.destination.coordinates,
      seg.mode
    );

    return {
      segment_id: seg.segmentId,
      mode: seg.mode,
      origin_title: seg.origin.name,
      origin_city: seg.origin.city,
      destination_title: seg.destination.name,
      destination_city: seg.destination.city,
      origin_coords: {
        latitude: seg.origin.coordinates.lat,
        longitude: seg.origin.coordinates.lng,
      },
      destination_coords: {
        latitude: seg.destination.coordinates.lat,
        longitude: seg.destination.coordinates.lng,
      },
      coordinates: coords,
      distance_meters: distMeters,
      duration_seconds: durSeconds,
      source: 'client_fallback',
      warnings: [],
    };
  });

  return {
    journey_id: journey.id,
    total_distance_meters: totalDistanceMeters,
    total_duration_seconds: totalDurationSeconds,
    segments,
    source: 'client_fallback',
    provider_status: 'ok',
  };
}

/**
 * Enriches a journey with precise spatial route geometry via the backend Google Routes / Geo engine.
 */
export async function enrichJourneyRoute(journey: Journey): Promise<EnrichedJourneyRoute> {
  const payload = {
    journey_id: journey.id,
    segments: journey.segments.map((s) => ({
      segment_id: s.segmentId,
      mode: s.mode,
      origin_name: s.origin.name,
      origin_city: s.origin.city,
      origin_lat: s.origin.coordinates.lat,
      origin_lng: s.origin.coordinates.lng,
      destination_name: s.destination.name,
      destination_city: s.destination.city,
      destination_lat: s.destination.coordinates.lat,
      destination_lng: s.destination.coordinates.lng,
      duration_minutes: s.durationMinutes,
      distance_km: s.distanceKm,
      vehicle_name: s.vehicleName || s.provider,
    })),
  };

  try {
    const enriched = await apiClient<EnrichedJourneyRoute>('/api/v1/maps/enrich', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    return enriched;
  } catch (err) {
    // Graceful offline fallback
    return buildClientFallbackRoute(journey);
  }
}

/**
 * Checks backend maps provider health status.
 */
export async function fetchRoutesHealth(): Promise<MapsHealthResponse> {
  try {
    return await apiClient<MapsHealthResponse>('/api/v1/maps/health');
  } catch {
    return {
      enabled: false,
      active_provider: 'offline_client',
      api_key_configured: false,
      service: 'Google Routes & Multimodal Geo Engine',
    };
  }
}
