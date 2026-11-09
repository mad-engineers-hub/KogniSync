/**
 * frontend/src/types/disruption.ts
 *
 * TypeScript domain models for Real-Time Journey Disruption Intelligence (Milestone M3.7).
 * Strictly mirrors backend Pydantic schemas with camelCase JSON attributes.
 */
import { Journey, TransportMode, ProvenanceSourceType, Location } from './journey';

export interface Coordinates {
  lat: number;
  lng: number;
}

export type DisruptionEventType =
  | 'road_closure'
  | 'traffic_congestion'
  | 'accident'
  | 'road_construction'
  | 'weather'
  | 'transport_delay'
  | 'service_cancellation'
  | 'station_disruption'
  | 'airport_disruption'
  | 'connection_risk'
  | 'unknown';

export type DisruptionSeverity = 'low' | 'moderate' | 'high' | 'critical' | 'unknown';

export type DisruptionStatus = 'active' | 'resolved' | 'scheduled' | 'unknown';

export type DisruptionImpactLevel = 'none' | 'low' | 'moderate' | 'high' | 'critical' | 'unknown';

export type DisruptionRecoveryStrategy =
  | 'reroute_same_mode'
  | 'alternative_transport_mode'
  | 'earlier_departure'
  | 'later_departure'
  | 'alternative_transfer_hub'
  | 'no_feasible_alternative'
  | 'manual_action_required';

export type ConnectionRiskLevel = 'safe' | 'at_risk' | 'critical' | 'missed_estimated' | 'unknown';

export interface DisruptionEvent {
  id: string;
  source: string;
  sourceId?: string | null;
  eventType: DisruptionEventType;
  severity: DisruptionSeverity;
  status: DisruptionStatus;
  title: string;
  description: string;
  affectedModes: TransportMode[];
  affectedLocations?: Location[];
  affectedRouteGeometry?: any;
  point?: Coordinates;
  radiusMeters?: number;
  validFrom: string;
  validUntil?: string | null;
  observedAt: string;
  lastVerifiedAt: string;
  provenance: ProvenanceSourceType;
  confidence: number;
  estimatedDelayMinutes?: number;
}

export interface DisruptedSegmentImpact {
  segmentId: string;
  sequence: number;
  mode: TransportMode;
  impactLevel: DisruptionImpactLevel;
  estimatedDelayMinutes: number;
  originalDepartureTime: string;
  originalArrivalTime: string;
  estimatedArrivalTime: string;
  matchingEvents: DisruptionEvent[];
  matchType: 'exact_geometry' | 'spatial_corridor' | 'hub_approximate';
  transferBufferReductionMinutes: number;
  subsequentTransferRisk: ConnectionRiskLevel;
  explanation: string;
  provenance: ProvenanceSourceType;
}

export interface JourneyDisruptionAssessment {
  journeyId: string;
  isDisrupted: boolean;
  highestSeverity: DisruptionSeverity;
  overallImpactLevel: DisruptionImpactLevel;
  totalEstimatedDelayMinutes: number;
  affectedSegmentCount: number;
  criticalConnectionRiskCount: number;
  segmentImpacts: DisruptedSegmentImpact[];
  activeDisruptions: DisruptionEvent[];
  summary: string;
  evaluatedAt: string;
  provenance: ProvenanceSourceType;
  dataFreshnessSeconds: number;
  notice?: string | null;
}

export interface RecoveryRecommendation {
  recommendationId: string;
  journeyId: string;
  strategy: DisruptionRecoveryStrategy;
  title: string;
  summary: string;
  tradeOffs: string[];
  originalJourney: Journey;
  recoveredJourney?: Journey | null;
  durationDeltaMinutes: number;
  priceDelta: number;
  carbonDeltaKg: number;
  transferRiskMitigated: boolean;
  manualRebookingRequired: boolean;
  isFeasible: boolean;
  feasibilityNotes: string[];
  provenance: ProvenanceSourceType;
}

export interface DisruptionRecoveryResponse {
  journeyId: string;
  assessment: JourneyDisruptionAssessment;
  recommendations: RecoveryRecommendation[];
  primaryRecommendation?: RecoveryRecommendation | null;
  feasibleAlternativesFound: boolean;
}

export interface DisruptionProviderCapability {
  name: string;
  displayName: string;
  isAvailable: boolean;
  provenanceSource: ProvenanceSourceType;
  supportedModes: TransportMode[];
  statusNotice: string;
}

export interface DisruptionAssessRequest {
  journey: Journey;
  includeSimulated?: boolean;
  scenario?: string | null;
}

export interface DisruptionRecoverRequest {
  journey: Journey;
  budgetMax?: number | null;
  preferredArrivalBefore?: string | null;
  includeSimulated?: boolean;
  scenario?: string | null;
}
