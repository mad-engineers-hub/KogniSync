import type { JourneySegment, TransportMode } from '../../types/journey';
import type { SegmentRouteGeometry, RouteCoordinate } from '../../types/route';
import type {
  NavigationManeuverAction,
  NormalizedManeuver,
  SegmentGuidance,
} from '../../types/navigation';

/**
 * Valhalla maneuver type code mapping to standardized navigation action.
 * Standard Valhalla maneuver types:
 * 1: kStart, 2: kStartRight, 3: kStartLeft
 * 4: kDestination, 5: kDestinationRight, 6: kDestinationLeft
 * 7: kContinue, 8: kSlightRight, 9: kRight, 10: kSharpRight, 11: kUturnRight, 12: kUturnLeft,
 * 13: kSharpLeft, 14: kLeft, 15: kSlightLeft, 16: kRampStraight, 17: kRampRight, 18: kRampLeft,
 * 19: kExitRight, 20: kExitLeft, 21: kStayStraight, 22: kStayRight, 23: kStayLeft,
 * 24: kMerge, 25: kRoundaboutEnter, 26: kRoundaboutExit, 27: kFerryEnter, 28: kFerryExit
 */
export function mapValhallaManeuverTypeToAction(type?: number): NavigationManeuverAction {
  if (type === undefined || type === null) return 'generic';

  switch (type) {
    case 1:
    case 2:
    case 3:
      return 'depart';
    case 4:
    case 5:
    case 6:
      return 'arrive';
    case 7:
    case 21:
      return 'continue';
    case 8:
    case 22:
      return 'slight_right';
    case 9:
      return 'right';
    case 10:
      return 'sharp_right';
    case 11:
    case 12:
      return 'u_turn';
    case 13:
      return 'sharp_left';
    case 14:
      return 'left';
    case 15:
    case 23:
      return 'slight_left';
    case 16:
    case 17:
    case 18:
    case 19:
    case 20:
      return 'ramp';
    case 24:
      return 'merge';
    case 25:
    case 26:
      return 'roundabout';
    case 27:
    case 28:
      return 'ferry';
    default:
      return 'generic';
  }
}

/**
 * Formats distance in meters to a clean human-readable string.
 */
export function formatDistanceMeters(meters: number): string {
  if (isNaN(meters) || meters < 0) return '0 m';
  if (meters < 1000) {
    return `${Math.round(meters)} m`;
  }
  const km = meters / 1000;
  return km < 10 ? `${km.toFixed(1)} km` : `${Math.round(km)} km`;
}

/**
 * Formats duration in seconds to a human-readable string.
 */
export function formatDurationSeconds(seconds: number): string {
  if (isNaN(seconds) || seconds <= 0) return '0 min';
  const mins = Math.round(seconds / 60);
  if (mins < 60) {
    return `${Math.max(1, mins)} min`;
  }
  const hrs = Math.floor(mins / 60);
  const remainingMins = mins % 60;
  return remainingMins > 0 ? `${hrs}h ${remainingMins}m` : `${hrs}h`;
}

/**
 * Normalizes raw Valhalla maneuver responses into typed frontend navigation maneuvers.
 */
export function normalizeManeuvers(
  rawManeuvers?: Array<{
    instruction: string;
    distance_meters?: number;
    time_seconds?: number;
    type?: number;
    street_names?: string[];
    begin_shape_index?: number;
    end_shape_index?: number;
    location?: RouteCoordinate;
  }>,
  completedIndices: number[] = [],
  segmentCoordinates: RouteCoordinate[] = []
): NormalizedManeuver[] {
  if (!rawManeuvers || !Array.isArray(rawManeuvers) || rawManeuvers.length === 0) {
    return [];
  }

  const completedSet = new Set(completedIndices);

  return rawManeuvers.map((m, index) => {
    const distanceMeters = Math.max(0, m.distance_meters || 0);
    const durationSeconds = Math.max(0, m.time_seconds || 0);
    const action = mapValhallaManeuverTypeToAction(m.type);

    let location = m.location;
    if (!location && m.begin_shape_index !== undefined && segmentCoordinates.length > m.begin_shape_index) {
      location = segmentCoordinates[m.begin_shape_index];
    }

    return {
      id: `maneuver-${index}`,
      instruction: m.instruction || 'Continue on route',
      action,
      distanceMeters,
      durationSeconds,
      formattedDistance: formatDistanceMeters(distanceMeters),
      formattedDuration: formatDurationSeconds(durationSeconds),
      rawType: m.type,
      streetNames: Array.isArray(m.street_names) ? m.street_names : [],
      location,
      beginShapeIndex: m.begin_shape_index,
      endShapeIndex: m.end_shape_index,
      isCompleted: completedSet.has(index),
    };
  });
}

/**
 * Constructs truthful, multimodal segment guidance.
 * Preserves strict provenance and never fabricates turn-by-turn guidance for non-road modes.
 */
export function getSegmentGuidance(
  segment: JourneySegment,
  sequence: number,
  geometry?: SegmentRouteGeometry,
  completedManeuverIndices: number[] = []
): SegmentGuidance {
  const mode = segment.mode;
  const isRoadMode = ['walk', 'cab', 'auto', 'rapido', 'bus', 'car', 'taxi'].includes(mode);
  const isLiveGeometry = Boolean(geometry?.is_live_geometry || segment.isLiveGeometry);

  const rawManeuvers = geometry?.maneuvers || [];
  const coords = geometry?.coordinates || [];

  // Live maneuvers are verified ONLY for road modes with real Valhalla geometry
  const isLiveManeuvers = isRoadMode && isLiveGeometry && rawManeuvers.length > 0;
  const normalizedManeuvers = isLiveManeuvers
    ? normalizeManeuvers(rawManeuvers, completedManeuverIndices, coords)
    : [];

  let actionTitle = '';
  let actionDetail = '';
  let independentVerificationRequired = false;
  let independentVerificationNotice: string | undefined = undefined;
  let provenanceBadge = 'Deterministic Estimate';

  if (isLiveManeuvers) {
    provenanceBadge = 'Valhalla OSM Live';
    if (mode === 'walk') {
      actionTitle = `Walk to ${segment.destination.name}`;
      actionDetail = 'Follow the verified pedestrian walkway route to your connection.';
    } else if (mode === 'rapido') {
      actionTitle = `Two-Wheeler Route to ${segment.destination.name}`;
      actionDetail = 'Follow two-wheeler road corridor to drop-off point.';
    } else if (mode === 'bus') {
      actionTitle = `Bus Road Corridor to ${segment.destination.name}`;
      actionDetail = 'Physical road routing along vehicular corridor. Departure schedules must be checked at the terminal.';
      independentVerificationRequired = true;
      independentVerificationNotice = 'Live bus timetable/tracking is not available; check terminal departure bay.';
    } else {
      actionTitle = `Drive to ${segment.destination.name}`;
      actionDetail = `Follow verified turn-by-turn road navigation via ${segment.provider || 'Cab'}.`;
    }
  } else {
    // Non-road or fallback segments
    switch (mode) {
      case 'train':
        actionTitle = `Proceed to ${segment.origin.name} for Train ${segment.vehicleNumber || segment.vehicleName || ''}`.trim();
        actionDetail = `Board ${segment.vehicleName || 'scheduled train'} towards ${segment.destination.name}. Verify platform assignments at the station.`;
        independentVerificationRequired = true;
        independentVerificationNotice = 'Platform, track assignment, and coach positions must be verified independently on station indicator boards.';
        provenanceBadge = 'Scheduled Railway Corridor';
        break;
      case 'flight':
        actionTitle = `Depart from ${segment.origin.name} (${segment.origin.code || 'Airport'})`;
        actionDetail = `Flight ${segment.vehicleNumber || ''} to ${segment.destination.name}. Complete security check-in at departure terminal.`;
        independentVerificationRequired = true;
        independentVerificationNotice = 'Terminal, gate assignment, and boarding status must be verified directly with the airline.';
        provenanceBadge = 'Scheduled Air Corridor';
        break;
      case 'metro':
        actionTitle = `Take Metro from ${segment.origin.name} to ${segment.destination.name}`;
        actionDetail = 'Proceed through station gates towards departure platform. Follow station signage for train line.';
        independentVerificationRequired = true;
        independentVerificationNotice = 'Follow directional station concourse signage for platform and train headway.';
        provenanceBadge = 'Metro Line Estimate';
        break;
      case 'walk':
        actionTitle = `Walk to ${segment.destination.name}`;
        actionDetail = 'Proceed along pedestrian walkway towards destination waypoint.';
        provenanceBadge = 'Pedestrian Corridor Estimate';
        break;
      default:
        actionTitle = `Travel to ${segment.destination.name}`;
        actionDetail = `Proceed via ${segment.provider || segment.mode} along designated route.`;
        provenanceBadge = 'Deterministic Route Estimate';
    }
  }

  let transferNotice: string | undefined;
  if (segment.transferBufferMinutes && segment.transferBufferMinutes > 0) {
    transferNotice = `${segment.transferBufferMinutes} min connection buffer at ${segment.destination.name}`;
  }

  return {
    segmentId: segment.segmentId,
    sequence,
    mode,
    provider: segment.provider || 'KogniSync Transport',
    vehicleName: segment.vehicleName,
    vehicleNumber: segment.vehicleNumber,
    originTitle: segment.origin.name,
    originCity: segment.origin.city,
    destinationTitle: segment.destination.name,
    destinationCity: segment.destination.city,
    actionTitle,
    actionDetail,
    scheduledDeparture: segment.departureTime,
    scheduledArrival: segment.arrivalTime,
    durationMinutes: segment.durationMinutes,
    isLiveManeuvers,
    hasManeuvers: normalizedManeuvers.length > 0,
    maneuvers: normalizedManeuvers,
    transferNotice,
    provenanceBadge,
    independentVerificationRequired,
    independentVerificationNotice,
  };
}

