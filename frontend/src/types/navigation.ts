import type { TransportMode } from './journey';
import type { RouteCoordinate } from './route';

export type NavigationManeuverAction =
  | 'depart'
  | 'arrive'
  | 'continue'
  | 'slight_right'
  | 'right'
  | 'sharp_right'
  | 'u_turn'
  | 'sharp_left'
  | 'left'
  | 'slight_left'
  | 'merge'
  | 'roundabout'
  | 'ramp'
  | 'ferry'
  | 'generic';

export interface NormalizedManeuver {
  id: string;
  instruction: string;
  action: NavigationManeuverAction;
  distanceMeters: number;
  durationSeconds: number;
  formattedDistance: string;
  formattedDuration: string;
  rawType?: number;
  streetNames: string[];
  location?: RouteCoordinate;
  beginShapeIndex?: number;
  endShapeIndex?: number;
  isCompleted: boolean;
}

export interface SegmentGuidance {
  segmentId: string;
  sequence: number;
  mode: TransportMode;
  provider: string;
  vehicleName?: string;
  vehicleNumber?: string;
  originTitle: string;
  originCity: string;
  destinationTitle: string;
  destinationCity: string;
  actionTitle: string;
  actionDetail: string;
  scheduledDeparture: string;
  scheduledArrival: string;
  durationMinutes: number;
  isLiveManeuvers: boolean;
  hasManeuvers: boolean;
  maneuvers: NormalizedManeuver[];
  transferNotice?: string;
  provenanceBadge: string;
  independentVerificationRequired: boolean;
  independentVerificationNotice?: string;
}

export type TransferReadinessState =
  | 'upcoming'
  | 'prepare'
  | 'tight_connection'
  | 'missed_estimated'
  | 'in_progress'
  | 'completed'
  | 'unknown';

export interface TransferReadiness {
  state: TransferReadinessState;
  hubName: string;
  incomingSegmentId: string;
  outgoingSegmentId: string;
  incomingMode: TransportMode;
  outgoingMode: TransportMode;
  scheduledArrival: string;
  scheduledDeparture: string;
  requiredBufferMinutes: number;
  availableBufferMinutes: number;
  minutesUntilTransfer: number;
  stateTitle: string;
  stateDescription: string;
  badgeColor: 'emerald' | 'amber' | 'blue' | 'rose' | 'slate';
  isTimeEstimated: boolean;
}

export interface JourneyProgressState {
  journeyId: string;
  activeSegmentIndex: number;
  completedSegmentIds: string[];
  completedManeuverIndices: Record<string, number[]>;
  lastUpdatedISO: string;
  isDeviceLocal: boolean;
}

export type LocationGuidanceStatus =
  | 'idle'
  | 'requesting'
  | 'live_position'
  | 'last_known_position'
  | 'demo_position'
  | 'unavailable'
  | 'permission_denied'
  | 'error';

export interface LocationGuidanceState {
  status: LocationGuidanceStatus;
  coords?: RouteCoordinate;
  accuracyMeters?: number;
  heading?: number | null;
  speed?: number | null;
  lastUpdatedAt?: string;
  errorMessage?: string;
}

