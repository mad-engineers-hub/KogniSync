import type { OptimizedJourneyOutput } from './optimizer';

export type TransportMode =
  | 'flight'
  | 'train'
  | 'bus'
  | 'cab'
  | 'rapido'
  | 'metro'
  | 'walk'
  | 'auto'
  | 'shuttle';

export interface Location {
  id: string;
  name: string;
  city: string;
  code?: string;
  type: 'airport' | 'railway_station' | 'bus_terminal' | 'metro_station' | 'landmark' | 'address';
  coordinates: {
    lat: number;
    lng: number;
  };
  airportGatewayCity?: string;
  airportCity?: string;
}

export interface Money {
  amount: number;
  currency: string;
}

export interface OptimizationWeights {
  cost: number;        // e.g. 0.40
  duration: number;    // e.g. 0.30
  comfort: number;     // e.g. 0.20
  carbon: number;      // e.g. 0.10
}

export type ProvenanceSourceType =
  | 'provider_live'
  | 'deterministic_estimate'
  | 'simulated'
  | 'unknown';

export interface AttributeProvenance {
  sourceType: ProvenanceSourceType;
  providerName?: string;
  isEstimate: boolean;
  notes?: string;
  lastUpdatedAt?: string;
}

export interface SegmentProvenance {
  sourceType: ProvenanceSourceType;
  providerName: string;
  isEstimate: boolean;
  hasLiveProvider: boolean;
  lastUpdatedAt?: string;
  attributes: Record<string, AttributeProvenance>;
}

export interface JourneyProvenance {
  overallSourceType: 'provider_live' | 'deterministic_estimate' | 'simulated' | 'mixed' | 'unknown';
  isFullyConfirmed: boolean;
  hasLiveAttributes: boolean;
  hasSimulatedAttributes: boolean;
  summary: string;
}

export interface JourneySegment {
  segmentId: string;
  sequence?: number;
  mode: TransportMode;
  provider: string;
  vehicleName?: string;
  vehicleNumber?: string;
  tripId?: string | null;
  routeId?: string | null;
  agencyId?: string | null;
  routeType?: number | null;
  directionId?: number | null;
  origin: Location;
  destination: Location;
  departureTime: string; // ISO string
  arrivalTime: string;   // ISO string
  durationMinutes: number;
  price: number;
  currency: string;
  availability: {
    status: 'available' | 'limited' | 'waitlist' | 'sold_out';
    remainingUnits?: number;
    inventoryId?: string;
    isRealInventory?: boolean;
  };
  distanceKm: number;
  carbonKg: number;
  comfortScore: number; // 1-10 scale
  seatClass?: string;
  notes?: string;
  transferBufferMinutes?: number;
  scheduleState?: SegmentScheduleState;
  provenance?: SegmentProvenance;
  encodedPolyline?: string;
  geojsonGeometry?: {
    type: string;
    coordinates: [number, number][];
  };
  isLiveGeometry?: boolean;
}

export type RecommendationCategory =
  | 'cheapest'
  | 'fastest'
  | 'best_value'
  | 'greenest'
  | 'comfortable'
  | 'all';

export interface PlannedOperationalRegulation {
  eventId: string;
  trainNumber: string;
  trainName: string;
  departureDate: string; // 'YYYY-MM-DD' (e.g. '2026-11-15')
  affectedSection: string; // 'Daund - Manmad section'
  regulationMinutes: number; // 130 (2h 10m)
  reason: string;
  sourceAuthority: string; // 'South Western Railway (SWR) & Northern Railway (NR)'
  sourceUrls: {
    swr: string;
    nr: string;
  };
  noticePublicationDate: string; // '2026-11-10'
  retrievalTimestamp: string; // '2026-11-14T08:30:00+05:30'
  impactType: 'en_route_regulation';
  terminalDelayGuaranteed: false;
}

export interface TimeWindowIST {
  earliestIST: string;        // 'HH:mm'
  latestIST: string;          // 'HH:mm'
  earliestInstantUTC?: string;// ISO string
  latestInstantUTC?: string;  // ISO string
  earliestDurationMin?: number;
  latestDurationMin?: number;
  dateStr?: string;           // 'YYYY-MM-DD'
}

export interface SegmentScheduleState {
  scheduledDeparture: string; // e.g. "19:20 IST" or "09:15 – 10:50 IST (Estimated)"
  scheduledArrival: string;   // e.g. "10:30 IST (Day 3)" or "09:21 – 10:56 IST (Estimated)"
  departureWindow?: TimeWindowIST;
  arrivalWindow?: TimeWindowIST;
  connectionType?: 'scheduled' | 'frequency_based_estimate' | 'feeder_shuttle';
  connectionStatus?: 'feasible' | 'infeasible' | 'uncertain';
  connectionNotes?: string;
  transferBufferMinutes?: number;
  passengerReadinessWindowIST?: string; // e.g. "09:15 – 10:45 IST"
  waitingMinutesRange?: { min: number; max: number }; // e.g. { min: 0, max: 5 }
  waitingTimeNotes?: string; // e.g. "Estimated platform wait: 0–5m (based on ~3–5m headway)"
  rideDurationMinutes?: number; // e.g. 6 (pure travel time after boarding)
  plannedRegulation?: PlannedOperationalRegulation;
  estimatedArrival?: string;
  liveRunningStatus: 'unavailable' | 'on_time' | 'delayed' | 'diverted';
  liveRunningStatusMessage?: string;
}

export interface OperationalNotice {
  headline: string;
  details: string;
  plannedRegulation?: PlannedOperationalRegulation;
  sourceAuthority: string;
  sourceUrl: string;
  secondarySourceUrl?: string;
  publishedAt: string;
}

export interface Journey {
  id: string;
  title: string;
  origin: Location;
  destination: Location;
  departureTime: string;
  arrivalTime: string;
  departureWindow?: TimeWindowIST;
  arrivalWindow?: TimeWindowIST;
  isArrivalUncertain?: boolean;
  arrivalWindowIST?: string;
  waitingMinutesRange?: { min: number; max: number };
  totalDurationMinutes: number;
  travelDurationMinutes?: number;
  waitingDurationMinutes?: number;
  inVehicleDurationMinutes?: number;
  walkingDurationMinutes?: number;
  isConnectionFeasible?: boolean;
  connectionFeasibilityNotes?: string[];
  operationalNotice?: OperationalNotice;
  isExpiredDeparture?: boolean;
  totalPrice: number;
  currency: string;
  totalTransfers: number;
  modes: TransportMode[];
  segments: JourneySegment[];
  carbonKg: number;
  comfortScore: number; // 1-10
  recommendationCategory: RecommendationCategory;
  isParetoOptimal?: boolean;
  optimization?: OptimizedJourneyOutput;
  aiExplanation: {
    summary: string;
    tradeOffs: string[];
    rankReason: string;
    score: number; // 0-100 composite score
    costVsFastestSaving?: number;
    durationDiffMinutes?: number;
    dataCredibilityNotice?: string;
    isFareEstimated?: boolean;
    isDurationEstimated?: boolean;
    isAvailabilityVerified?: boolean;
  };
  bookingFeasibility: {
    holdSupported: boolean;
    concurrencySafe: boolean;
    holdTtlSeconds: number;
  };
  provenance?: JourneyProvenance;
}

export interface JourneyRecommendation {
  journeyId: string;
  rank: number;
  category: RecommendationCategory;
  score: number;
  explanation: string;
  weights: OptimizationWeights;
}

export interface TravelRequest {
  naturalLanguageQuery?: string;
  origin: string;
  destination: string;
  departureDate: string;
  preferredArrivalBefore?: string;
  preferredDepartureAfter?: string;
  budgetMax?: number;
  passengersCount: number;
  weights: OptimizationWeights;
  originCoordinates?: { lat: number; lng: number };
  destinationCoordinates?: { lat: number; lng: number };
  referenceNowInstant?: string; // Optional frozen reference time for deterministic testing
  allowHistoricalFixtures?: boolean; // When true, historical past departures are not excluded
}

export interface JourneySearchResponse {
  journeys: Journey[];
  recommendedJourneyId?: string;
  totalCandidates: number;
  eligibleCandidates: number;
  paretoFrontierCount: number;
  source: string;
  providerStatus: Record<string, string>;
}
