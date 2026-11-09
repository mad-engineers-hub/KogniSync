import React, { useState } from 'react';
import { useParams, useNavigate, useLocation, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getJourneyById } from '../api/journey';
import { assessJourneyDisruptions, recoverDisruptedJourney } from '../api/disruptions';
import { JourneyTimeline } from '../components/details/JourneyTimeline';
import { JourneyMap } from '../components/details/JourneyMap';
import { AIRecommendationExplanation } from '../components/details/AIRecommendationExplanation';
import { OptimizationBadge } from '../components/common/OptimizationBadge';
import { ProvenanceBadge } from '../components/common/ProvenanceBadge';
import { DisruptionBanner } from '../components/disruption/DisruptionBanner';
import { DisruptionRecoveryCard } from '../components/disruption/DisruptionRecoveryCard';
import { DemoDisruptionController } from '../components/disruption/DemoDisruptionController';
import { ProviderIntelligencePanel } from '../components/disruption/ProviderIntelligencePanel';
import { Journey } from '../types/journey';
import { formatCurrency, formatDuration } from '../lib/utils';
import { ArrowLeft, ArrowRight, ShieldCheck, AlertCircle, Compass, Eye, Sparkles, Navigation } from 'lucide-react';
import { getJourneyXRReferences } from '../utils/xrMatching';

export const DetailsPage: React.FC = () => {
  const { journeyId } = useParams<{ journeyId: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const searchParams = new URLSearchParams(location.search);
  const isGuidanceRequested = searchParams.get('guidance') === 'true';
  const [manualGuidanceOpen, setManualGuidanceOpen] = useState<boolean>(false);
  const guidanceActive = isGuidanceRequested || manualGuidanceOpen;

  const [disruptionScenario, setDisruptionScenario] = useState<string | null>(
    () => searchParams.get('scenario') || null
  );
  const [selectedRecovery, setSelectedRecovery] = useState<Journey | null>(null);
  const [isRecoveryOpen, setIsRecoveryOpen] = useState<boolean>(false);

  const {
    data: journey,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['journey', journeyId],
    queryFn: () => getJourneyById(journeyId || ''),
    enabled: !!journeyId,
  });

  const {
    data: disruptionAssessment,
    isLoading: isAssessmentLoading,
    refetch: refetchAssessment,
  } = useQuery({
    queryKey: ['disruptions-assess', journey?.id, disruptionScenario],
    queryFn: () =>
      journey
        ? assessJourneyDisruptions({
            journey,
            includeSimulated: true,
            scenario: disruptionScenario,
          })
        : null,
    enabled: !!journey,
  });

  const {
    data: recoveryResponse,
    isLoading: isRecoveryLoading,
  } = useQuery({
    queryKey: ['disruptions-recover', journey?.id, disruptionScenario],
    queryFn: () =>
      journey && disruptionAssessment?.isDisrupted
        ? recoverDisruptedJourney({
            journey,
            includeSimulated: true,
            scenario: disruptionScenario,
          })
        : null,
    enabled: !!journey && Boolean(disruptionAssessment?.isDisrupted),
  });

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-20 text-center flex flex-col items-center justify-center gap-3">
        <div className="w-10 h-10 rounded-full border-3 border-blue-600/20 border-t-blue-600 animate-spin" />
        <p className="text-sm font-semibold text-slate-700">
          Loading synchronized journey details...
        </p>
      </div>
    );
  }

  if (isError || !journey) {
    return (
      <div className="max-w-xl mx-auto px-4 py-20 text-center flex flex-col items-center gap-4">
        <AlertCircle className="w-12 h-12 text-rose-500" />
        <h2 className="text-xl font-bold text-slate-900">Journey Not Found</h2>
        <p className="text-xs text-slate-500">
          The requested multi-modal itinerary does not exist or has expired.
        </p>
        <Link
          to="/plan"
          className="px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700 transition-colors shadow-xs"
        >
          Back to Results
        </Link>
      </div>
    );
  }

  const xrReferences = getJourneyXRReferences(journey);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full flex flex-col gap-8">
      {/* Back button & Title summary */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="p-2.5 rounded-xl bg-white border border-slate-200 hover:bg-slate-100 text-slate-700 transition-colors shadow-2xs"
            title="Go back"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div className="flex flex-col">
            <div className="flex items-center gap-2 flex-wrap">
              <OptimizationBadge category={journey.recommendationCategory} size="sm" />
              <ProvenanceBadge
                sourceType={journey.provenance?.overallSourceType || 'deterministic_estimate'}
                isFullyConfirmed={journey.provenance?.isFullyConfirmed}
              />
              <h1 className="text-xl sm:text-2xl font-black text-slate-950 font-display">
                {journey.title}
              </h1>
            </div>
            <span className="text-xs text-slate-500 font-mono mt-0.5 font-medium">
              {journey.origin.name} → {journey.destination.name} ·{' '}
              {formatDuration(journey.totalDurationMinutes)} total duration ·{' '}
              {journey.segments.length} legs · {journey.totalTransfers} transfers
            </span>
          </div>
        </div>

        {/* Pricing & CTA */}
        <div className="flex items-center gap-4 self-end sm:self-auto">
          <div className="flex flex-col items-end">
            <span className="text-2xl sm:text-3xl font-black font-display text-slate-900">
              {formatCurrency(journey.totalPrice, journey.currency)}
            </span>
            <span className="text-[11px] text-slate-500 font-mono">
              {journey.aiExplanation.isFareEstimated === false ? 'Live Provider Quote' : 'Corridor Estimated Total'}
            </span>
          </div>

          <button
            onClick={() => {
              setManualGuidanceOpen(true);
              const el = document.getElementById('journey-map-section');
              if (el) el.scrollIntoView({ behavior: 'smooth' });
            }}
            className="px-4 py-3 rounded-2xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-800 font-bold text-sm shadow-xs flex items-center gap-2 transition-all cursor-pointer"
          >
            <Navigation className="w-4 h-4 text-blue-600" />
            <span>Guide Me</span>
          </button>

          <button
            onClick={() => navigate(`/booking/${journey.id}`)}
            className="px-6 py-3 rounded-2xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-sm shadow-md shadow-blue-600/20 flex items-center gap-2 transition-all active:scale-98 cursor-pointer"
          >
            <span>Select Journey</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Disruption Intelligence Banner (Milestone M3.7) */}
      <DisruptionBanner
        assessment={disruptionAssessment || null}
        isLoading={isAssessmentLoading}
        onRefresh={() => refetchAssessment()}
        onViewRecovery={() => setIsRecoveryOpen(!isRecoveryOpen)}
        isRecoveryOpen={isRecoveryOpen}
      />

      {/* Provider Intelligence & Operational Feeds Status (Milestone M3.8) */}
      <ProviderIntelligencePanel onRefresh={() => refetchAssessment()} />

      {/* Multimodal Journey Recovery Recommendations Panel */}
      {isRecoveryOpen && recoveryResponse && recoveryResponse.recommendations.length > 0 && (
        <div className="flex flex-col gap-4 p-5 sm:p-6 rounded-2xl border border-blue-200 bg-gradient-to-br from-blue-50/60 via-white to-slate-50 shadow-sm animate-fade-in">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-blue-950">
              <Sparkles className="w-5 h-5 text-blue-600" />
              <h2 className="text-base sm:text-lg font-black font-display">
                Pareto Recommended Recovery Alternatives
              </h2>
            </div>
            <span className="text-xs font-mono font-bold text-slate-500">
              {recoveryResponse.recommendations.length} Candidate Option{recoveryResponse.recommendations.length > 1 ? 's' : ''}
            </span>
          </div>

          <p className="text-xs text-slate-600 leading-relaxed font-medium">
            KogniSync re-evaluated multimodal corridors to eliminate disruption delays while satisfying travel safety.
            Inspect candidate recovery options below. Selecting an alternative previews its geometry and timeline.
          </p>

          <div className="flex flex-col gap-4">
            {recoveryResponse.recommendations.map((rec) => (
              <DisruptionRecoveryCard
                key={rec.recommendationId}
                recommendation={rec}
                isSelected={selectedRecovery?.id === rec.recoveredJourney?.id}
                onSelectRecovery={(recJourney) => {
                  setSelectedRecovery(selectedRecovery?.id === recJourney?.id ? null : recJourney);
                  const mapEl = document.getElementById('journey-map-section');
                  if (mapEl) mapEl.scrollIntoView({ behavior: 'smooth' });
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Main Grid: Left Timeline & AI explanation; Right Map & Telemetry */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left column (7 cols): AI Explanation & Timeline */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          {selectedRecovery && (
            <div className="p-4 rounded-xl border border-blue-300 bg-blue-50/80 flex items-center justify-between gap-3 text-xs text-blue-950 font-medium shadow-2xs">
              <div className="flex items-center gap-2 min-w-0">
                <span className="p-1 rounded-md bg-blue-600 text-white text-[10px] font-bold font-mono uppercase">
                  Previewing Recovery
                </span>
                <span className="truncate">Active view switched to: <strong>{selectedRecovery.title}</strong></span>
              </div>
              <button
                onClick={() => setSelectedRecovery(null)}
                className="px-2.5 py-1 rounded-lg bg-white border border-blue-200 text-blue-700 hover:bg-blue-100 font-bold shrink-0 cursor-pointer"
              >
                Reset to Original
              </button>
            </div>
          )}
          <AIRecommendationExplanation journey={selectedRecovery || journey} />
          <JourneyTimeline journey={selectedRecovery || journey} />
        </div>

        {/* Right column (5 cols): Map & Invariants metadata & XR Explorer */}
        <div id="journey-map-section" className="lg:col-span-5 flex flex-col gap-6 scroll-mt-20">
          <JourneyMap
            segments={(selectedRecovery || journey).segments}
            journey={selectedRecovery || journey}
            disruptionAssessment={disruptionAssessment}
            initialGuidanceOpen={guidanceActive}
          />

          {/* Disruption Simulation Demo Controller (M3.7 Evaluation Tool) */}
          <DemoDisruptionController
            activeScenario={disruptionScenario}
            onSelectScenario={(sc) => {
              setDisruptionScenario(sc);
              setSelectedRecovery(null);
            }}
            isLoading={isAssessmentLoading || isRecoveryLoading}
          />

          {/* XR Spatial Previews & AR Wayfinding Card */}
          {xrReferences.length > 0 && (
            <div className="p-5 rounded-2xl border border-blue-200 bg-gradient-to-br from-blue-50/80 via-white to-slate-50 shadow-xs flex flex-col gap-3.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-blue-900">
                  <div className="p-1.5 rounded-lg bg-blue-600 text-white shadow-xs">
                    <Compass className="w-4 h-4 animate-spin-slow" />
                  </div>
                  <h4 className="text-xs font-bold uppercase tracking-wider font-mono">
                    Explore This Journey in 360° & AR
                  </h4>
                </div>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 text-[10px] font-bold font-mono">
                  <Sparkles className="w-2.5 h-2.5 text-blue-600" />
                  {xrReferences.length} Locations
                </span>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed">
                Step inside the key transfer stations and destination hubs on this route. View 360° concourse walkthroughs and step-by-step AR wayfinding between platforms, feeder buses, and cab stands.
              </p>

              <div className="flex flex-col gap-2 pt-1">
                {xrReferences.map((ref) => (
                  <Link
                    key={ref.sceneId}
                    to={`/xr/${ref.sceneId}`}
                    className="flex items-center justify-between p-3 rounded-xl border border-blue-200/80 bg-white hover:border-blue-500 hover:shadow-sm transition-all group"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="p-2 rounded-lg bg-blue-50 text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-colors shrink-0">
                        <Eye className="w-4 h-4" />
                      </div>
                      <div className="flex flex-col min-w-0">
                        <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 font-bold">
                          {ref.context.replace('_', ' ')}
                        </span>
                        <span className="text-xs font-bold text-slate-900 group-hover:text-blue-600 truncate transition-colors">
                          {ref.title}
                        </span>
                      </div>
                    </div>

                    <span className="text-xs font-semibold text-blue-600 px-2.5 py-1 rounded-lg bg-blue-50 group-hover:bg-blue-100 transition-colors shrink-0">
                      Open 360°
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* Concurrency Invariant Card */}
          <div className="p-5 rounded-2xl border border-slate-200 bg-white flex flex-col gap-3 shadow-xs">
            <div className="flex items-center gap-2 text-emerald-700">
              <ShieldCheck className="w-5 h-5 text-emerald-600" />
              <h4 className="text-xs font-bold uppercase tracking-wider font-mono">
                {journey.provenance?.isFullyConfirmed
                  ? 'Live Inventory Hold Guarantee'
                  : 'Sandbox Hold Invariant (Simulation Mode)'}
              </h4>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              {journey.provenance?.isFullyConfirmed
                ? `When you proceed, KogniSync atomically reserves capacity across all ${journey.segments.length} carriers simultaneously. If any segment hold expires or rejects, the saga compensator rolls back previous holds without charging you.`
                : `Demonstrates multi-vendor saga compensation across all ${journey.segments.length} legs in the demonstration database. In sandbox mode, holds atomically lock local demo capacity without creating real-world airline or railway reservations.`}
            </p>
            <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500 font-mono">
              <span>Hold TTL: 600 seconds (10 mins)</span>
              <span>{journey.provenance?.isFullyConfirmed ? 'Live Carrier API' : 'Sandbox Demo Database'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
