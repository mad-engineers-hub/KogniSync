/**
 * frontend/src/components/disruption/DisruptionBanner.tsx
 *
 * Real-Time Disruption Summary Banner (Milestone M3.7).
 * Visualizes active disruptions, severity, affected legs, delay slip,
 * and transparent provenance notice (SIMULATED vs LIVE).
 */
import React from 'react';
import {
  AlertTriangle,
  AlertOctagon,
  ArrowRight,
  CheckCircle2,
  RefreshCw,
} from 'lucide-react';
import { DisruptionEvent, JourneyDisruptionAssessment } from '../../types/disruption';

function deriveLiveProviderLabel(assessment: JourneyDisruptionAssessment): string {
  const liveEvents = (assessment.activeDisruptions || []).filter(
    (e) => e.provenance === 'provider_live'
  );
  const sources = new Set(liveEvents.map((e) => e.source));
  const hasGtfs = sources.has('gtfs_realtime');
  const hasTomTom = sources.has('tomtom_orbis') || sources.has('tomtom');
  if (hasGtfs && hasTomTom) {
    return 'LIVE PROVIDER DATA — TomTom Orbis v2 + GTFS-RT / IUDX';
  }
  if (hasGtfs) {
    return 'LIVE PROVIDER DATA — Authorized Transit Feed (GTFS-RT / IUDX)';
  }
  if (hasTomTom) {
    return 'LIVE PROVIDER DATA — TomTom Orbis v2';
  }
  return 'LIVE PROVIDER DATA';
}

function formatEventTimestamp(iso?: string | null): string {
  if (!iso) return 'Unknown timestamp';
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

interface DisruptionBannerProps {
  assessment: JourneyDisruptionAssessment | null;
  isLoading?: boolean;
  onRefresh?: () => void;
  onViewRecovery?: () => void;
  isRecoveryOpen?: boolean;
}

export const DisruptionBanner: React.FC<DisruptionBannerProps> = ({
  assessment,
  isLoading = false,
  onRefresh,
  onViewRecovery,
  isRecoveryOpen = false,
}) => {
  if (!assessment) return null;

  if (!assessment.isDisrupted || assessment.overallImpactLevel === 'none') {
    return (
      <div
        role="region"
        aria-label="Disruption Status"
        className="w-full p-4 rounded-2xl border border-emerald-200 bg-emerald-50/70 text-emerald-950 flex items-center justify-between gap-4 shadow-2xs"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="p-2 rounded-xl bg-emerald-600 text-white shrink-0 shadow-2xs">
            <CheckCircle2 className="w-4 h-4" />
          </div>
          <div className="flex flex-col min-w-0">
            <span className="text-xs font-bold font-mono tracking-wider text-emerald-800 uppercase">
              All Corridors Clear
            </span>
            <span className="text-xs text-emerald-700 truncate font-medium">
              No active road or transit disruptions detected along this journey.
            </span>
          </div>
        </div>

        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="p-2 rounded-xl border border-emerald-300 bg-white hover:bg-emerald-100 text-emerald-800 transition-colors shadow-2xs cursor-pointer shrink-0"
            title="Refresh disruption telemetry"
            aria-label="Refresh disruption telemetry"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        )}
      </div>
    );
  }

  const isCritical =
    assessment.overallImpactLevel === 'critical' || assessment.highestSeverity === 'critical';
  const isHigh = assessment.overallImpactLevel === 'high' || assessment.highestSeverity === 'high';

  const badgeBg = isCritical
    ? 'bg-rose-50 border-rose-300 text-rose-950'
    : isHigh
    ? 'bg-amber-50 border-amber-300 text-amber-950'
    : 'bg-yellow-50 border-yellow-300 text-yellow-950';

  const iconBg = isCritical ? 'bg-rose-600' : isHigh ? 'bg-amber-600' : 'bg-yellow-600';

  const isSimulated = assessment.provenance === 'simulated';

  return (
    <div
      role="region"
      aria-label="Disruption Warning Banner"
      className={`w-full p-4 sm:p-5 rounded-2xl border ${badgeBg} shadow-xs flex flex-col gap-3.5 transition-all`}
    >
      {/* Header row: Icon, Title, and Action button */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-start sm:items-center gap-3 min-w-0">
          <div className={`p-2 rounded-xl ${iconBg} text-white shrink-0 shadow-2xs mt-0.5 sm:mt-0`}>
            {isCritical ? (
              <AlertOctagon className="w-5 h-5 animate-pulse" />
            ) : (
              <AlertTriangle className="w-5 h-5" />
            )}
          </div>
          <div className="flex flex-col min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={`px-2 py-0.5 rounded-full text-[10px] font-black uppercase font-mono tracking-wider ${
                  isCritical
                    ? 'bg-rose-600 text-white'
                    : isHigh
                    ? 'bg-amber-600 text-white'
                    : 'bg-yellow-600 text-white'
                }`}
              >
                {assessment.overallImpactLevel.toUpperCase()} DISRUPTION
              </span>

              {isSimulated ? (
                <span className="px-2 py-0.5 rounded-full bg-slate-900 text-amber-300 text-[10px] font-bold font-mono tracking-wider">
                  SIMULATED DISRUPTION — NOT LIVE PROVIDER DATA
                </span>
              ) : assessment.notice?.includes('STALE') ? (
                <span className="px-2 py-0.5 rounded-full bg-amber-800 text-amber-100 text-[10px] font-bold font-mono">
                  STALE PROVIDER OBSERVATION — VERIFY BEFORE TRAVEL
                </span>
              ) : assessment.notice?.includes('AGING') ? (
                <span className="px-2 py-0.5 rounded-full bg-amber-600 text-white text-[10px] font-bold font-mono">
                  AGING PROVIDER OBSERVATION — VERIFY BEFORE TRAVEL
                </span>
              ) : assessment.provenance === 'provider_live' ? (
                <span className="px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 text-[10px] font-bold font-mono">
                  {deriveLiveProviderLabel(assessment)}
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-full bg-slate-200 text-slate-800 text-[10px] font-bold font-mono">
                  ESTIMATED IMPACT — BASED ON PROVIDER INCIDENT
                </span>
              )}
            </div>

            <h3 className="text-sm sm:text-base font-black text-slate-950 mt-1">
              {assessment.affectedSegmentCount} Journey Leg{assessment.affectedSegmentCount > 1 ? 's' : ''}{' '}
              Disrupted · +{assessment.totalEstimatedDelayMinutes}m Estimated Delay
            </h3>
          </div>
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isLoading}
              className="p-2.5 rounded-xl border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 transition-colors shadow-2xs cursor-pointer"
              title="Refresh disruption telemetry"
              aria-label="Refresh disruption status"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          )}

          {onViewRecovery && (
            <button
              onClick={onViewRecovery}
              className={`px-4 py-2.5 rounded-xl font-bold text-xs shadow-xs flex items-center gap-2 transition-all cursor-pointer ${
                isRecoveryOpen
                  ? 'bg-slate-900 text-white hover:bg-slate-800'
                  : 'bg-rose-600 text-white hover:bg-rose-700 shadow-rose-600/20'
              }`}
            >
              <span>{isRecoveryOpen ? 'Hide Recovery Plan' : 'View Recovery Plan'}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Description & Impact Summary */}
      <p className="text-xs sm:text-sm text-slate-800 leading-relaxed font-medium">
        {assessment.summary}
      </p>

      {/* Active Event Attribution (Source, Timestamp, Freshness) */}
      {assessment.activeDisruptions && assessment.activeDisruptions.length > 0 && (
        <div className="pt-2 border-t border-slate-200/70 space-y-1.5">
          <div className="flex items-center justify-between text-[10px] font-mono font-bold text-slate-600 uppercase">
            <span>Verified Disruption Events ({assessment.activeDisruptions.length})</span>
            {assessment.criticalConnectionRiskCount > 0 && (
              <span className="text-rose-700">
                {assessment.criticalConnectionRiskCount} Critical Transfer Risk
                {assessment.criticalConnectionRiskCount > 1 ? 's' : ''}
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {assessment.activeDisruptions.slice(0, 4).map((ev: DisruptionEvent) => (
              <div
                key={ev.id}
                className="px-2.5 py-1.5 rounded-lg bg-white/90 border border-slate-200 text-[11px] flex flex-col gap-0.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-slate-900 truncate">{ev.title}</span>
                  <span
                    className={`px-1.5 py-0.2 rounded text-[9px] font-mono font-bold uppercase shrink-0 ${
                      ev.provenance === 'provider_live'
                        ? 'bg-blue-100 text-blue-800'
                        : ev.provenance === 'simulated'
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-slate-100 text-slate-700'
                    }`}
                  >
                    {ev.provenance === 'provider_live' ? ev.source : ev.provenance}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[10px] font-mono text-slate-500">
                  <span>Obs: {formatEventTimestamp(ev.observedAt)}</span>
                  <span>Freshness: {ev.dataFreshnessStatus || 'unknown'}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Disrupted legs breakdown badges */}
      {assessment.segmentImpacts && assessment.segmentImpacts.length > 0 && (
        <div className="pt-2 border-t border-slate-200/80 flex flex-wrap items-center gap-2 text-xs">
          <span className="font-mono text-[11px] font-bold text-slate-600 uppercase">
            Affected Legs:
          </span>
          {assessment.segmentImpacts
            .filter((imp) => imp.impactLevel !== 'none')
            .map((imp) => (
              <span
                key={imp.segmentId}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white border border-slate-200 font-mono text-[11px] font-semibold text-slate-800 shadow-2xs"
              >
                <span className="capitalize">{imp.mode}</span> (Leg {imp.sequence}): +{imp.estimatedDelayMinutes}m
                {imp.subsequentTransferRisk === 'critical' && (
                  <span className="text-rose-600 font-bold">⚠️ Connection Missed</span>
                )}
                {imp.subsequentTransferRisk === 'at_risk' && (
                  <span className="text-amber-600 font-bold">⚠️ Tight Transfer</span>
                )}
              </span>
            ))}
        </div>
      )}
    </div>
  );
};

