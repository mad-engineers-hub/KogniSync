/**
 * frontend/src/utils/corridorMetrics.ts
 *
 * Adaptive viewport sizing and corridor metric calculations (Finding A).
 * Computes geographic bounds, latitude/longitude spans, corridor length,
 * and classifies routes (long-distance North-South corridors vs short local feeders)
 * to determine responsive map viewport heights.
 */

import { isValidCoordinate } from './mapCoordinates';
import type { JourneySegment } from '../types/journey';

export interface CorridorMetrics {
  latSpan: number;
  lngSpan: number;
  totalDistKm: number;
  isLongCorridor: boolean;
  isShortLocal: boolean;
}

/**
 * Computes geographic span and corridor distance across journey segments.
 */
export function computeCorridorMetrics(segments: JourneySegment[]): CorridorMetrics {
  let minLat = Infinity;
  let maxLat = -Infinity;
  let minLng = Infinity;
  let maxLng = -Infinity;
  let totalDistKm = 0;

  segments.forEach((seg) => {
    totalDistKm += seg.distanceKm || 0;
    if (isValidCoordinate(seg.origin?.coordinates)) {
      minLat = Math.min(minLat, seg.origin.coordinates.lat);
      maxLat = Math.max(maxLat, seg.origin.coordinates.lat);
      minLng = Math.min(minLng, seg.origin.coordinates.lng);
      maxLng = Math.max(maxLng, seg.origin.coordinates.lng);
    }
    if (isValidCoordinate(seg.destination?.coordinates)) {
      minLat = Math.min(minLat, seg.destination.coordinates.lat);
      maxLat = Math.max(maxLat, seg.destination.coordinates.lat);
      minLng = Math.min(minLng, seg.destination.coordinates.lng);
      maxLng = Math.max(maxLng, seg.destination.coordinates.lng);
    }
  });

  const hasValidPoints = isFinite(minLat) && isFinite(maxLat);
  const latSpan = hasValidPoints ? maxLat - minLat : 0;
  const lngSpan = isFinite(minLng) && isFinite(maxLng) ? maxLng - minLng : 0;

  // Long-distance / North-South corridor criteria:
  // - latSpan >= 2.0 degrees (~220+ km) OR
  // - totalDistKm >= 200 km OR
  // - latSpan >= 1.2 with totalDistKm >= 100 km
  const isLongCorridor = latSpan >= 2.0 || totalDistKm >= 200 || (latSpan >= 1.2 && totalDistKm >= 100);
  // Short local journey: intra-city or short feeder (< 45 km, latSpan < 0.4 deg) with known valid coordinates
  const isShortLocal = hasValidPoints && totalDistKm < 45 && latSpan < 0.4;

  return {
    latSpan,
    lngSpan,
    totalDistKm,
    isLongCorridor,
    isShortLocal,
  };
}

/**
 * Returns responsive Tailwind viewport height class based on corridor characteristics.
 * - Long corridor: Mobile >= 384px, Tablet >= 460px, Desktop >= 520px (lg:h-[540px])
 * - Short local: Compact height (h-72 sm:h-80 md:h-96)
 * - Standard regional: Intermediate responsive height
 */
export function getViewportHeightClass(metrics: CorridorMetrics): string {
  if (metrics.isLongCorridor) {
    // Long-distance / North-South corridor: expansive canvas prevents endpoint clipping
    return 'h-[384px] sm:h-[460px] md:h-[500px] lg:h-[540px]';
  }
  if (metrics.isShortLocal) {
    // Short local journey: compact height avoids unnecessary enlargement
    return 'h-72 sm:h-80 md:h-96';
  }
  // Standard regional route
  return 'h-[384px] sm:h-[420px] md:h-[460px] lg:h-[500px]';
}
