import type { OptimizedJourneyOutput } from './optimizer';

export type TransportMode =
  | 'flight'
  | 'train'
  | 'bus'
  | 'cab'
  | 'rapido'
  | 'metro'
  | 'walk'
  | 'auto';

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
  provenance?: SegmentProvenance;
}

export type RecommendationCategory =
  | 'cheapest'
  | 'fastest'
  | 'best_value'
  | 'greenest'
  | 'comfortable'
  | 'all';

export interface Journey {
  id: string;
  title: string;
  origin: Location;
  destination: Location;
  departureTime: string;
  arrivalTime: string;
  totalDurationMinutes: number;
  travelDurationMinutes?: number;
  waitingDurationMinutes?: number;
  inVehicleDurationMinutes?: number;
  walkingDurationMinutes?: number;
  isConnectionFeasible?: boolean;
  connectionFeasibilityNotes?: string[];
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
