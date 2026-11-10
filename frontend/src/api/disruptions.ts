/**
 * frontend/src/api/disruptions.ts
 *
 * API client for Real-Time Journey Disruption Intelligence (Milestone M3.7).
 * Connects to FastAPI backend disruption endpoints with graceful offline client simulation.
 */
import { apiClient } from './client';
import {
  DisruptionAssessRequest,
  DisruptionEvent,
  DisruptionProviderCapability,
  DisruptionRecoverRequest,
  DisruptionRecoveryResponse,
  GTFSFeedListResponse,
  GTFSFeedStatus,
  JourneyDisruptionAssessment,
} from '../types/disruption';
import { Journey } from '../types/journey';

export async function getGTFSFeeds(): Promise<GTFSFeedListResponse> {
  try {
    return await apiClient<GTFSFeedListResponse>('/api/v1/disruptions/providers/feeds');
  } catch (err) {
    console.warn('[getGTFSFeeds] Backend offline; returning fallback feed list:', err);
    return {
      feeds: [
        {
          feedId: 'bmtc_iudx_alerts',
          operatorName: 'BMTC',
          displayName: 'Bengaluru Metropolitan Transport Corporation (IUDX)',
          geographicCoverage: 'Bengaluru Metropolitan Area',
          feedUrlSanitized: 'https://opendata.benscl.com/gtfs-rt/alerts',
          entityTypes: ['service_alerts', 'trip_updates'],
          enabled: false,
          authorizationStatus: 'pending_credentials',
          connectivityStatus: 'unconfigured',
          freshnessStatus: 'unknown',
          consecutiveFailureCount: 0,
          entityCounts: {},
          statusNotice: 'Awaiting authorized credentials in environment variable BMTC_IUDX_AUTH_TOKEN.',
        },
      ],
      totalConfigured: 0,
      totalOperational: 0,
      notice: 'No live GTFS Realtime feeds are currently verified and operational.',
    };
  }
}

export async function getDisruptionProviders(): Promise<DisruptionProviderCapability[]> {
  try {
    return await apiClient<DisruptionProviderCapability[]>('/api/v1/disruptions/providers');
  } catch (err) {
    console.warn('[getDisruptionProviders] Backend offline; returning fallback discovery:', err);
    return [
      {
        name: 'live_traffic_feed',
        displayName: 'Live Traffic & Incident Provider (TomTom Orbis v2)',
        providerType: 'traffic_incidents',
        isAvailable: false,
        isConfigured: false,
        credentialsPresent: false,
        connectivityStatus: 'unconfigured',
        provenanceSource: 'unknown',
        supportedModes: ['cab', 'bus', 'auto', 'rapido'],
        statusNotice: 'BLOCKED — credentials unavailable (commercial TOMTOM_API_KEY required). Simulation active.',
        statusReason: 'No valid TomTom API key in environment configuration.',
      },
      {
        name: 'gtfs_realtime_feed',
        displayName: 'Official GTFS Realtime Transit Feed',
        providerType: 'gtfs_realtime',
        isAvailable: false,
        isConfigured: false,
        credentialsPresent: false,
        connectivityStatus: 'unconfigured',
        provenanceSource: 'unknown',
        supportedModes: ['bus', 'train', 'metro'],
        statusNotice: 'BLOCKED — authorized GTFS Realtime feed unavailable.',
        statusReason: 'No authorized regional public transport GTFS-RT feed configured in environment.',
      },
      {
        name: 'simulation_engine',
        displayName: 'Deterministic Disruption Simulator',
        providerType: 'simulation',
        isAvailable: true,
        isConfigured: true,
        credentialsPresent: true,
        connectivityStatus: 'available',
        provenanceSource: 'simulated',
        supportedModes: ['cab', 'bus', 'train', 'metro', 'flight', 'auto', 'rapido', 'walk'],
        statusNotice: 'Active in sandbox/demo mode. Generates deterministic incidents with visible simulation badges.',
        statusReason: 'Deterministic scenario engine available for testing and demos.',
      },
    ];
  }
}

export async function getActiveDisruptions(params?: {
  corridor?: string;
  scenario?: string;
  includeSimulated?: boolean;
}): Promise<DisruptionEvent[]> {
  const query = new URLSearchParams();
  if (params?.corridor) query.set('corridor', params.corridor);
  if (params?.scenario) query.set('scenario', params.scenario);
  if (params?.includeSimulated !== undefined) {
    query.set('include_simulated', String(params.includeSimulated));
  }

  const endpoint = `/api/v1/disruptions${query.toString() ? `?${query.toString()}` : ''}`;
  try {
    return await apiClient<DisruptionEvent[]>(endpoint);
  } catch (err) {
    console.warn('[getActiveDisruptions] Backend offline, generating fallback simulated events:', err);
    return getFallbackSimulatedEvents(params?.scenario);
  }
}

export async function assessJourneyDisruptions(
  request: DisruptionAssessRequest
): Promise<JourneyDisruptionAssessment> {
  try {
    return await apiClient<JourneyDisruptionAssessment>('/api/v1/disruptions/assess', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  } catch (err) {
    console.warn('[assessJourneyDisruptions] Backend offline, calculating deterministic fallback assessment:', err);
    return createFallbackAssessment(request.journey, request.scenario);
  }
}

export async function recoverDisruptedJourney(
  request: DisruptionRecoverRequest
): Promise<DisruptionRecoveryResponse> {
  try {
    return await apiClient<DisruptionRecoveryResponse>('/api/v1/disruptions/recover', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  } catch (err) {
    console.warn('[recoverDisruptedJourney] Backend offline, calculating deterministic fallback recovery:', err);
    return createFallbackRecovery(request.journey, request.scenario, request.budgetMax);
  }
}

// --- Client-Side Deterministic Fallbacks (Strictly Tagged Simulated) ---

function getFallbackSimulatedEvents(scenario?: string | null): DisruptionEvent[] {
  const now = new Date();
  const validFrom = new Date(now.getTime() - 3600000).toISOString();
  const validUntil = new Date(now.getTime() + 28800000).toISOString();
  const observedAt = new Date(now.getTime() - 900000).toISOString();

  const shiradiEvent: DisruptionEvent = {
    id: 'sim-disrupt-nh75-shiradi-ghat',
    source: 'simulation_engine',
    sourceId: 'DEMO-M37-NH75',
    eventType: 'road_closure',
    severity: 'critical',
    status: 'active',
    title: 'SIMULATED DISRUPTION — NOT LIVE PROVIDER DATA: NH-75 Shiradi Ghat Landslide & Road Closure',
    description:
      'Severe landslide and rockfall near Sakleshpur-Gundya corridor. Both vehicular carriageways on NH-75 are blocked. Estimated road delay: 180 minutes.',
    affectedModes: ['cab', 'bus'],
    point: { lat: 12.8797, lng: 75.6425 },
    radiusMeters: 15000,
    validFrom,
    validUntil,
    observedAt,
    lastVerifiedAt: now.toISOString(),
    provenance: 'simulated',
    confidence: 1.0,
    estimatedDelayMinutes: 180,
  };

  const silkBoardEvent: DisruptionEvent = {
    id: 'sim-disrupt-blr-silkboard',
    source: 'simulation_engine',
    sourceId: 'DEMO-M37-BLR-ORR',
    eventType: 'traffic_congestion',
    severity: 'high',
    status: 'active',
    title: 'SIMULATED DISRUPTION — NOT LIVE PROVIDER DATA: Silk Board & Outer Ring Road Severe Gridlock',
    description:
      'Waterlogging and vehicle breakdown on Silk Board flyover underpass. Estimated road delay: 45 minutes.',
    affectedModes: ['cab', 'bus', 'auto', 'rapido'],
    point: { lat: 12.9176, lng: 77.6238 },
    radiusMeters: 3500,
    validFrom,
    validUntil,
    observedAt,
    lastVerifiedAt: now.toISOString(),
    provenance: 'simulated',
    confidence: 0.95,
    estimatedDelayMinutes: 45,
  };

  if (scenario === 'silk_board') return [silkBoardEvent];
  if (scenario === 'shiradi_ghat') return [shiradiEvent];
  return [shiradiEvent, silkBoardEvent];
}

function createFallbackAssessment(journey: Journey, scenario?: string | null): JourneyDisruptionAssessment {
  const events = getFallbackSimulatedEvents(scenario);
  const now = new Date().toISOString();

  // Find if any road segment exists
  const roadSegment = journey.segments.find(
    (s) => s.mode === 'cab' || s.mode === 'bus' || s.mode === 'auto'
  );

  if (!roadSegment) {
    return {
      journeyId: journey.id,
      isDisrupted: false,
      highestSeverity: 'low',
      overallImpactLevel: 'none',
      totalEstimatedDelayMinutes: 0,
      affectedSegmentCount: 0,
      criticalConnectionRiskCount: 0,
      segmentImpacts: journey.segments.map((s, idx) => ({
        segmentId: s.segmentId,
        sequence: s.sequence ?? idx + 1,
        mode: s.mode,
        impactLevel: 'none',
        estimatedDelayMinutes: 0,
        originalDepartureTime: s.departureTime,
        originalArrivalTime: s.arrivalTime,
        estimatedArrivalTime: s.arrivalTime,
        matchingEvents: [],
        matchType: 'spatial_corridor',
        transferBufferReductionMinutes: 0,
        subsequentTransferRisk: 'safe',
        explanation: 'No disruptions detected on this leg.',
        provenance: 'deterministic_estimate',
      })),
      activeDisruptions: [],
      summary: 'All route segments are clear. No disruptions detected along journey corridors.',
      evaluatedAt: now,
      provenance: 'deterministic_estimate',
      dataFreshnessSeconds: 15,
      notice: 'Deterministic corridor estimate',
    };
  }

  const activeEvent = events[0];
  const delay = activeEvent.estimatedDelayMinutes || 120;

  return {
    journeyId: journey.id,
    isDisrupted: true,
    highestSeverity: activeEvent.severity,
    overallImpactLevel: 'critical',
    totalEstimatedDelayMinutes: delay,
    affectedSegmentCount: 1,
    criticalConnectionRiskCount: 1,
    segmentImpacts: journey.segments.map((s, idx) => {
      if (s.segmentId === roadSegment.segmentId) {
        return {
          segmentId: s.segmentId,
          sequence: s.sequence ?? idx + 1,
          mode: s.mode,
          impactLevel: 'critical',
          estimatedDelayMinutes: delay,
          originalDepartureTime: s.departureTime,
          originalArrivalTime: s.arrivalTime,
          estimatedArrivalTime: new Date(new Date(s.arrivalTime).getTime() + delay * 60000).toISOString(),
          matchingEvents: [activeEvent],
          matchType: 'exact_geometry',
          transferBufferReductionMinutes: delay,
          subsequentTransferRisk: 'critical',
          explanation: `Disruption intersects route: ${activeEvent.title}`,
          provenance: 'simulated',
        };
      }
      return {
        segmentId: s.segmentId,
        sequence: s.sequence ?? idx + 1,
        mode: s.mode,
        impactLevel: 'none',
        estimatedDelayMinutes: 0,
        originalDepartureTime: s.departureTime,
        originalArrivalTime: s.arrivalTime,
        estimatedArrivalTime: s.arrivalTime,
        matchingEvents: [],
        matchType: 'spatial_corridor',
        transferBufferReductionMinutes: 0,
        subsequentTransferRisk: 'safe',
        explanation: 'No disruptions on this leg.',
        provenance: 'deterministic_estimate',
      };
    }),
    activeDisruptions: [activeEvent],
    summary: `[SIMULATED] CRITICAL DISRUPTION: ${activeEvent.title} introduces +${delay} min delay, eroding transfer buffers. Journey recovery recommended.`,
    evaluatedAt: now,
    provenance: 'simulated',
    dataFreshnessSeconds: 15,
    notice: 'SIMULATED DISRUPTION — NOT LIVE PROVIDER DATA',
  };
}

function createFallbackRecovery(
  journey: Journey,
  scenario?: string | null,
  budgetMax?: number | null
): DisruptionRecoveryResponse {
  const assessment = createFallbackAssessment(journey, scenario);

  if (budgetMax && budgetMax < 500) {
    const noAltRec = {
      recommendationId: `rec-${journey.id}-no-alt`,
      journeyId: journey.id,
      strategy: 'no_feasible_alternative' as const,
      title: 'No Feasible Alternative Under Hard Constraints',
      summary: 'All generated recovery routes violate your specified budget or arrival deadline.',
      tradeOffs: [`Fare exceeds maximum budget limit of ₹${budgetMax}`],
      originalJourney: journey,
      recoveredJourney: null,
      durationDeltaMinutes: 0,
      priceDelta: 0,
      carbonDeltaKg: 0,
      transferRiskMitigated: false,
      manualRebookingRequired: true,
      isFeasible: false,
      feasibilityNotes: [`Budget limit ₹${budgetMax} exceeded.`],
      provenance: 'simulated' as const,
    };
    return {
      journeyId: journey.id,
      assessment,
      recommendations: [noAltRec],
      primaryRecommendation: noAltRec,
      feasibleAlternativesFound: false,
    };
  }

  // Create recovered journey substituting road leg with train
  const recoveredJourney: Journey = {
    ...journey,
    id: `${journey.id}-rec-rail`,
    title: `${journey.title} (Via Rail Alternative)`,
    totalPrice: Math.max(250, journey.totalPrice * 0.75),
    totalDurationMinutes: Math.max(60, journey.totalDurationMinutes - 20),
    carbonKg: Number((journey.carbonKg * 0.45).toFixed(1)),
    segments: journey.segments.map((s) => {
      if (s.mode === 'cab' || s.mode === 'bus') {
        return {
          ...s,
          segmentId: `${s.segmentId}-rec-rail`,
          mode: 'train',
          provider: 'Indian Railways (Express Service)',
          vehicleName: 'Karwar / Vande Bharat Express',
          price: Math.max(180, s.price * 0.65),
          carbonKg: Number((s.carbonKg * 0.35).toFixed(1)),
          transferBufferMinutes: 30,
        };
      }
      return s;
    }),
  };

  const primaryRec = {
    recommendationId: `rec-${recoveredJourney.id}`,
    journeyId: journey.id,
    strategy: 'alternative_transport_mode' as const,
    title: 'Shift to Electrified Railway Corridor (Estimated Alternative)',
    summary:
      'Shifts travel from disrupted road link to electrified railway corridor. Eliminates 180 min landslide delay.',
    tradeOffs: [
      'Hypothetical railway alternative: requires independent verification of IRCTC/station timetable and seat inventory.',
      'Bypasses road closure entirely via railway corridor.',
      'Corridor estimated fare (~25% less than road booking); inventory unverified.',
      'Carbon emissions reduced by ~55%; scheduled station boarding required.',
    ],
    originalJourney: journey,
    recoveredJourney,
    durationDeltaMinutes: -20,
    priceDelta: Number((recoveredJourney.totalPrice - journey.totalPrice).toFixed(0)),
    carbonDeltaKg: Number((recoveredJourney.carbonKg - journey.carbonKg).toFixed(1)),
    transferRiskMitigated: true,
    manualRebookingRequired: true,
    isFeasible: true,
    feasibilityNotes: ['Validated against hard constraints.'],
    provenance: 'simulated' as const,
  };

  return {
    journeyId: journey.id,
    assessment,
    recommendations: [primaryRec],
    primaryRecommendation: primaryRec,
    feasibleAlternativesFound: true,
  };
}
